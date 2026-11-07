import re
import shutil
from pathlib import Path
from datetime import date
from fastapi import FastAPI, Request, Depends, UploadFile, File, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.config import ROOT, settings
from app.database import init_db, get_db, Job, AgentRun, Task
from app.services.llm import generate, LLMError, check_connection
from app.services.resume import extract_resume_text
from app.agents.job_hunter import (
    hunt_jobs,
    parse_resume_profile,
    rescore_all_jobs,
    get_location_category,
    classify_role,
    get_job_roles,
    ROLE_LABELS,
    cleanup_expired_jobs,
    calculate_job_expiry
)
from app.agents.email_drafter import generate_draft, save_draft, create_gmail_draft
from app.agents.routine_manager import list_habits, set_habit, add_task, complete_task, briefing
from app.agents.contact_finder import find_public_contacts
from app.agents.orchestrator import handle_message
from app.scheduler import start_scheduler, run_morning_pipeline
from app.plugins.plugin_manager import list_plugins, run_plugin
from app.telegram_bot import run_bot

app = FastAPI(title=settings.app_name)
app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")
templates = Jinja2Templates(directory=ROOT / "templates")

# Ensure resumes directory exists
RESUMES_DIR = ROOT / "data" / "resumes"
RESUMES_DIR.mkdir(parents=True, exist_ok=True)


def get_available_resumes():
    """List all detected resume files across data/resumes, data/, and app/Resume/."""
    resumes = []
    seen = set()
    dirs = [RESUMES_DIR, ROOT / "app" / "Resume", ROOT / "data"]

    for d in dirs:
        if d.exists():
            for f in d.iterdir():
                if f.is_file() and f.suffix.lower() in {".pdf", ".docx", ".txt"}:
                    if f.name.lower() not in seen:
                        seen.add(f.name.lower())
                        try:
                            is_active = (
                                Path(settings.resume_path).resolve() == f.resolve()
                            )
                        except Exception:
                            is_active = False

                        resumes.append({
                            "name": f.name,
                            "path": str(f.resolve()),
                            "size_kb": round(f.stat().st_size / 1024, 1),
                            "active": is_active
                        })
    return resumes


def get_active_resume_profile():
    """Get profile and parsed skills for the currently active resume."""
    p = Path(settings.resume_path)
    if not p.exists():
        # Fallback to resume in data/ or data/resumes/ if available
        candidates = [ROOT / "data" / "resume.pdf"]
        if RESUMES_DIR.exists():
            candidates.extend([f for f in RESUMES_DIR.iterdir() if f.is_file() and f.suffix.lower() in {".pdf", ".docx", ".txt"}])
        resume_folder = ROOT / "app" / "Resume"
        if resume_folder.exists():
            candidates.extend([f for f in resume_folder.iterdir() if f.is_file() and f.suffix.lower() in {".pdf", ".docx", ".txt"}])

        for candidate in candidates:
            if candidate.exists() and candidate.is_file():
                settings.resume_path = str(candidate)
                p = candidate
                break

    if p.exists():
        try:
            text = extract_resume_text(str(p))
            prof = parse_resume_profile(text)
            return {
                "name": p.name,
                "path": str(p),
                "skills": sorted(list(prof.get("skills", set()))),
                "experience_level": prof.get("experience_level", "Unknown")
            }
        except Exception:
            return {"name": p.name, "path": str(p), "skills": [], "experience_level": "Unknown"}

    return {"name": "No Resume", "path": "", "skills": [], "experience_level": "None"}


@app.on_event("startup")
def startup():
    init_db()
    start_scheduler()
    if settings.telegram_bot_token:
        import threading
        threading.Thread(target=run_bot, daemon=True).start()


@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request, db: Session = Depends(get_db)):
    # Auto-cleanup expired unreviewed jobs (>18h IST)
    cleanup_expired_jobs(db, max_age_hours=settings.job_expiry_hours)
    all_jobs = db.query(Job).all()

    # Prioritize India (0) & Global Remote (1) over foreign-only locations (2), then sort by score descending
    def job_sort_key(j):
        cat = get_location_category(j.location)
        prio = 0 if cat == "india" else (1 if cat == "remote" else 2)
        return (prio, -j.score)

    source_counts = {}
    for j in all_jobs:
        s = (j.source or "").lower()
        source_counts[s] = source_counts.get(s, 0) + 1

    sorted_jobs = sorted(all_jobs, key=job_sort_key)[:150]
    for j in sorted_jobs:
        j.location_category = get_location_category(j.location)
        j.role_category = classify_role(j.title, j.description)
        j.roles_str = " ".join(get_job_roles(j.title, j.description))
        j.role_label = ROLE_LABELS.get(j.role_category, "💻 Software Eng")
        time_meta = calculate_job_expiry(j.date_found, max_age_hours=settings.job_expiry_hours)
        j.ist_time = time_meta["ist_str"]
        j.expires_in = time_meta["expires_in_str"]
        j.is_expiring_soon = time_meta["is_expiring_soon"]

    habits = list_habits(db)
    tasks = db.query(Task).filter_by(day=date.today()).order_by(Task.id.desc()).all()
    runs = db.query(AgentRun).order_by(AgentRun.created_at.desc()).limit(6).all()
    total_jobs = db.query(Job).count()
    new_jobs = db.query(Job).filter_by(status="New").count()

    active_resume = get_active_resume_profile()
    available_resumes = get_available_resumes()

    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "jobs": sorted_jobs,
            "source_counts": source_counts,
            "habits": habits,
            "tasks": tasks,
            "runs": runs,
            "total_jobs": total_jobs,
            "new_jobs": new_jobs,
            "plugins": list_plugins(),
            "model": settings.gemini_model if settings.llm_provider == "gemini" else settings.groq_model,
            "active_resume": active_resume,
            "available_resumes": available_resumes
        }
    )


# -------------------------------------------------------------
# RESUME MANAGEMENT ENDPOINTS
# -------------------------------------------------------------

@app.get("/api/resume/info")
def resume_info():
    """Get active resume details and skills."""
    return get_active_resume_profile()


@app.get("/api/resumes")
def list_resumes():
    """List all uploaded resumes."""
    return {"resumes": get_available_resumes()}


@app.post("/api/resume")
async def upload_resume(file: UploadFile = File(...), db: Session = Depends(get_db)):
    """Upload any candidate's resume, parse skills, and automatically re-score jobs."""
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in {".pdf", ".docx", ".txt"}:
        raise HTTPException(400, "Please upload a valid PDF, DOCX, or TXT resume file.")

    safe_name = re.sub(r"[^a-zA-Z0-9_.-]+", "_", file.filename or f"resume{suffix}")
    dest = RESUMES_DIR / safe_name

    content = await file.read()
    if len(content) > 15 * 1024 * 1024:
        raise HTTPException(413, "Resume must be smaller than 15 MB.")

    dest.write_bytes(content)

    # Set as active resume
    settings.resume_path = str(dest)

    # Update .env if present
    env_path = ROOT / ".env"
    if env_path.exists():
        lines = env_path.read_text(encoding="utf-8").splitlines()
        updated = False
        for idx, line in enumerate(lines):
            if line.startswith("RESUME_PATH="):
                lines[idx] = f"RESUME_PATH={dest}"
                updated = True
        if not updated:
            lines.append(f"RESUME_PATH={dest}")
        env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    # Automatically re-score existing jobs for this new resume
    rescore_result = rescore_all_jobs(db, str(dest))

    return {
        "message": f"Resume '{safe_name}' uploaded successfully!",
        "filename": safe_name,
        "path": str(dest),
        "skills": rescore_result.get("skills", []),
        "experience_level": rescore_result.get("experience_level", "Entry / Fresher"),
        "jobs_rescored": rescore_result.get("jobs_rescored", 0)
    }


@app.post("/api/resume/select")
def select_active_resume(path: str = Form(...), db: Session = Depends(get_db)):
    """Switch active resume to any existing file and re-score matching jobs."""
    file_path = Path(path)
    if not file_path.exists():
        raise HTTPException(404, "Resume file not found.")

    settings.resume_path = str(file_path)
    rescore_result = rescore_all_jobs(db, str(file_path))

    return {
        "ok": True,
        "active_resume": file_path.name,
        "skills": rescore_result.get("skills", []),
        "jobs_rescored": rescore_result.get("jobs_rescored", 0)
    }


@app.post("/api/jobs/rescore")
def trigger_rescore(db: Session = Depends(get_db)):
    """Re-score all jobs against the current active resume."""
    result = rescore_all_jobs(db)
    return result


# -------------------------------------------------------------
# TODO / TASK MANAGEMENT ENDPOINTS
# -------------------------------------------------------------

@app.get("/api/tasks")
def get_tasks(db: Session = Depends(get_db)):
    """List all tasks for today."""
    tasks = db.query(Task).filter_by(day=date.today()).order_by(Task.id.desc()).all()
    return {
        "tasks": [
            {
                "id": t.id,
                "title": t.title,
                "completed": t.completed,
                "created_at": t.created_at.strftime("%H:%M") if t.created_at else ""
            }
            for t in tasks
        ]
    }


@app.post("/api/tasks")
def task_create(title: str = Form(...), db: Session = Depends(get_db)):
    """Create a new task."""
    clean_title = title.strip()
    if not clean_title:
        raise HTTPException(400, "Task title is required.")
    task = add_task(db, clean_title)
    return {"id": task.id, "title": task.title, "completed": task.completed}


@app.post("/api/tasks/{task_id}/toggle")
def task_toggle(task_id: int, completed: bool = Form(...), db: Session = Depends(get_db)):
    """Toggle a task between active and completed."""
    task = db.get(Task, task_id)
    if not task:
        raise HTTPException(404, "Task not found.")
    task.completed = completed
    db.commit()
    return {"id": task.id, "completed": task.completed}


@app.post("/api/tasks/{task_id}/complete")
def task_done(task_id: int, db: Session = Depends(get_db)):
    """Mark a task completed."""
    if not complete_task(db, task_id):
        raise HTTPException(404, "Task not found.")
    return {"ok": True}


@app.delete("/api/tasks/{task_id}")
def task_delete(task_id: int, db: Session = Depends(get_db)):
    """Permanently delete a task from the database."""
    task = db.get(Task, task_id)
    if not task:
        raise HTTPException(404, "Task not found.")
    db.delete(task)
    db.commit()
    return {"ok": True}


@app.post("/api/tasks/clear-completed")
def task_clear_completed(db: Session = Depends(get_db)):
    """Clear all completed tasks for today."""
    deleted = db.query(Task).filter_by(day=date.today(), completed=True).delete(synchronize_session=False)
    db.commit()
    return {"ok": True, "deleted": deleted}


# -------------------------------------------------------------
# JOB HUNTING & OUTREACH ENDPOINTS
# -------------------------------------------------------------

@app.post("/api/jobs/hunt")
def hunt(db: Session = Depends(get_db), query: str = Form("")):
    try:
        result = hunt_jobs(db, search_query=query if query else None)
        db.add(AgentRun(agent="job_hunter", status="success", summary=f"Added {result['added']} jobs."))
        db.commit()
        return {"added": result["added"], "errors": result["errors"], "skipped": result.get("skipped_no_match", 0)}
    except Exception as exc:
        db.add(AgentRun(agent="job_hunter", status="error", summary=str(exc)[:2000]))
        db.commit()
        raise HTTPException(400, str(exc))


@app.post("/api/jobs/{job_id}/status")
def update_job_status(job_id: int, status: str = Form(...), db: Session = Depends(get_db)):
    allowed = {"New", "Interested", "Applied", "Interview", "Rejected", "Archived"}
    if status not in allowed:
        raise HTTPException(400, "Invalid status")
    job = db.get(Job, job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    job.status = status
    db.commit()
    return {"ok": True}


@app.post("/api/jobs/{job_id}/draft")
def draft_email(job_id: int, db: Session = Depends(get_db)):
    job = db.get(Job, job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    try:
        draft = generate_draft(
            {"title": job.title, "company": job.company, "description": job.description, "url": job.url},
            settings.resume_path
        )
        path = save_draft({"title": job.title, "company": job.company, "url": job.url}, draft, job.recruiter_email)
        gmail_status = create_gmail_draft(draft, job.recruiter_email, job.url)
        return {"subject": draft["subject"], "body": draft["body"], "path": path, "gmail": gmail_status}
    except Exception as exc:
        raise HTTPException(400, str(exc))


@app.post("/api/morning/run")
def trigger_morning_pipeline():
    try:
        result = run_morning_pipeline()
        return result
    except Exception as exc:
        raise HTTPException(500, str(exc))


@app.post("/api/jobs/{job_id}/contacts")
def discover_contacts(job_id: int, db: Session = Depends(get_db)):
    job = db.get(Job, job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    contacts = find_public_contacts(job.company, job.url, job.description)
    if contacts:
        job.recruiter_email = contacts[0]["email"]
        job.contact_source = contacts[0]["source"]
        db.commit()
    return {"contacts": contacts, "note": "Contacts derived from publicly listed addresses and corporate domain patterns."}


# -------------------------------------------------------------
# HABITS & BRIEFINGS
# -------------------------------------------------------------

@app.post("/api/habits/{habit_id}")
def habit_toggle(habit_id: int, completed: bool = Form(...), db: Session = Depends(get_db)):
    if not set_habit(db, habit_id, completed):
        raise HTTPException(404, "Habit not found")
    return {"ok": True}


@app.post("/api/briefing")
def create_briefing(db: Session = Depends(get_db)):
    jobs = db.query(Job).filter_by(status="New").order_by(Job.score.desc()).limit(5).all()
    try:
        return {"briefing": briefing(db, jobs)}
    except Exception as exc:
        raise HTTPException(503, str(exc))


# -------------------------------------------------------------
# FAST CHAT ENDPOINT
# -------------------------------------------------------------

@app.post("/api/chat")
async def chat(request: Request, db: Session = Depends(get_db)):
    body = await request.json()
    message = str(body.get("message", "")).strip()
    if not message:
        raise HTTPException(400, "Message is required")
    if len(message) > 6000:
        raise HTTPException(413, "Message is too long")
    try:
        answer = handle_message(message, db=db)
        return {"reply": answer}
    except Exception as exc:
        raise HTTPException(400, str(exc))


# -------------------------------------------------------------
# PLUGINS & HEALTH
# -------------------------------------------------------------

@app.get("/api/plugins")
def plugins():
    return {"plugins": list_plugins()}


@app.post("/api/plugins/{name}/run")
async def plugin_run(name: str, request: Request):
    kwargs = await request.json()
    try:
        return {"result": run_plugin(name, **kwargs)}
    except Exception as exc:
        raise HTTPException(400, str(exc))


@app.get("/api/health")
def health_check():
    connected = check_connection()
    return {
        "connected": connected,
        "model": settings.gemini_model if settings.llm_provider == "gemini" else settings.groq_model
    }
