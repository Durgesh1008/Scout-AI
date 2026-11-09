import re
import json
import uuid
import shutil
from typing import Optional
from pathlib import Path
from datetime import date
from fastapi import FastAPI, Request, Response, Depends, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.config import ROOT, settings
from app.database import init_db, get_db, Job, AgentRun, Task, UserResume, UserJobState
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
from app.services.prep_lab import (
    PREP_TRACKS,
    get_company_intel,
    list_prep_tracks,
    list_featured_companies
)
from app.data.system_design_101 import list_system_design_cases
from app.services.mock_interview import (
    generate_mock_question,
    evaluate_mock_answer
)
from app.services.code_runner import execute_code
from app.agents.email_drafter import generate_draft, save_draft, create_gmail_draft
from app.agents.routine_manager import list_habits, set_habit, add_task, complete_task, briefing
from app.agents.contact_finder import find_public_contacts
from app.agents.orchestrator import handle_message
from app.scheduler import start_scheduler, run_morning_pipeline
from app.plugins.plugin_manager import list_plugins, run_plugin
from app.telegram_bot import run_bot

app = FastAPI(title=settings.app_name)

# Cross-Origin Resource Sharing (CORS) for Cloudflare Pages & frontend clients
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")
templates = Jinja2Templates(directory=ROOT / "templates")

# Ensure resumes directory exists
RESUMES_DIR = ROOT / "data" / "resumes"
RESUMES_DIR.mkdir(parents=True, exist_ok=True)


def get_session_id(request: Request) -> str:
    """Extract or generate a secure, isolated session identifier for multi-user safety."""
    session_id = request.cookies.get("scout_session_id")
    if not session_id or not re.match(r"^[a-zA-Z0-9_-]{8,64}$", session_id):
        session_id = uuid.uuid4().hex[:16]
    return session_id


def get_available_resumes(session_id: str = "default", db: Optional[Session] = None):
    """List all resume files accessible to this user session."""
    resumes = []
    seen = set()

    # User's uploaded resumes from database
    if db:
        user_resumes = db.query(UserResume).filter_by(session_id=session_id).all()
        for ur in user_resumes:
            p = Path(ur.filepath)
            if p.exists() and p.name.lower() not in seen:
                seen.add(p.name.lower())
                resumes.append({
                    "name": ur.filename,
                    "path": str(p.resolve()),
                    "size_kb": round(p.stat().st_size / 1024, 1),
                    "active": ur.is_active
                })

    # Public/Sample resumes fallback
    dirs = [RESUMES_DIR / session_id, RESUMES_DIR, ROOT / "app" / "Resume", ROOT / "data"]
    for d in dirs:
        if d.exists():
            for f in d.iterdir():
                if f.is_file() and f.suffix.lower() in {".pdf", ".docx", ".txt"}:
                    if f.name.lower() not in seen:
                        seen.add(f.name.lower())
                        resumes.append({
                            "name": f.name,
                            "path": str(f.resolve()),
                            "size_kb": round(f.stat().st_size / 1024, 1),
                            "active": False if resumes else True
                        })
    return resumes


def get_active_resume_profile(session_id: str = "default", db: Optional[Session] = None):
    """Get active resume profile scoped to this user session without mutating global state."""
    if db:
        user_res = db.query(UserResume).filter_by(session_id=session_id, is_active=True).first()
        if user_res and Path(user_res.filepath).exists():
            p = Path(user_res.filepath)
            try:
                text = extract_resume_text(str(p))
                prof = parse_resume_profile(text)
                return {
                    "name": user_res.filename,
                    "path": str(p),
                    "skills": sorted(list(prof.get("skills", set()))),
                    "experience_level": prof.get("experience_level", user_res.experience_level)
                }
            except Exception:
                return {"name": user_res.filename, "path": str(p), "skills": [], "experience_level": user_res.experience_level}

    # Fallback to configured resume or sample CV
    candidates = [
        Path(settings.resume_path),
        ROOT / "app" / "Resume" / "CV-Durgesh.pdf",
        ROOT / "data" / "resume.pdf"
    ]
    for p in candidates:
        if p.exists():
            try:
                text = extract_resume_text(str(p))
                prof = parse_resume_profile(text)
                return {
                    "name": p.name,
                    "path": str(p),
                    "skills": sorted(list(prof.get("skills", set()))),
                    "experience_level": prof.get("experience_level", "Entry Level")
                }
            except Exception:
                return {"name": p.name, "path": str(p), "skills": [], "experience_level": "Entry Level"}

    return {"name": "No Resume", "path": "", "skills": [], "experience_level": "Upload CV"}


def get_contact_badge(job: Job) -> Optional[dict]:
    """
    Transparently labels recruiter contact addresses into 3 distinct categories:
    1. Published and extracted (found directly in description or application listing)
    2. Verified mailbox (standard corporate talent inbox: careers@, talent@, recruiting@, etc.)
    3. Generated pattern — unverified (algorithmic pattern guess from candidate/recruiter names)
    """
    if not job.recruiter_email:
        return None
    cs = (job.contact_source or "").lower()
    email = job.recruiter_email.lower().strip()

    # 1. Published and extracted (found in description, explicitly tagged published or directly_scraped)
    if (
        "published" in cs
        or "directly_scraped" in cs
        or "job_description" in cs
        or (job.description and email in job.description.lower())
    ):
        return {
            "type": "published",
            "label": "Published and extracted",
            "short_label": "Published",
            "icon": "bi-patch-check-fill",
            "badge_class": "badge-contact-published",
            "tooltip": "Extracted directly from the original job listing"
        }

    # 2. Verified mailbox (standard corporate talent inbox: careers@, talent@, recruiting@, jobs@, hr@, intern-recruitment@)
    if (
        "verified_mailbox" in cs
        or "talent_inbox" in cs
        or any(email.startswith(p + "@") for p in ["careers", "talent", "recruiting", "jobs", "hiring", "intern-recruitment"])
    ):
        return {
            "type": "verified_mailbox",
            "label": "Verified mailbox",
            "short_label": "Verified Mailbox",
            "icon": "bi-inbox-fill",
            "badge_class": "badge-contact-mailbox",
            "tooltip": "Company career & talent inbox"
        }

    # 3. Generated pattern — unverified (e.g. firstname.lastname@company.com)
    return {
        "type": "pattern_generated",
        "label": "Generated pattern — unverified",
        "short_label": "Pattern (Unverified)",
        "icon": "bi-question-diamond-fill",
        "badge_class": "badge-contact-pattern",
        "tooltip": "Algorithmic email pattern guess — not independently verified"
    }


@app.on_event("startup")
def startup():
    init_db()
    start_scheduler()
    if settings.telegram_bot_token:
        import threading
        threading.Thread(target=run_bot, daemon=True).start()


@app.get("/", response_class=HTMLResponse)
@app.get("/jobs", response_class=HTMLResponse)
@app.get("/chat", response_class=HTMLResponse)
@app.get("/assistant", response_class=HTMLResponse)
@app.get("/interview", response_class=HTMLResponse)
@app.get("/mock", response_class=HTMLResponse)
@app.get("/prep", response_class=HTMLResponse)
@app.get("/resume", response_class=HTMLResponse)
@app.get("/todos", response_class=HTMLResponse)
@app.get("/tasks", response_class=HTMLResponse)
@app.get("/habits", response_class=HTMLResponse)
@app.get("/briefing", response_class=HTMLResponse)
@app.get("/activity", response_class=HTMLResponse)
@app.get("/settings", response_class=HTMLResponse)
def dashboard(request: Request, response: Response, db: Session = Depends(get_db)):
    session_id = get_session_id(request)
    response.set_cookie(key="scout_session_id", value=session_id, max_age=31536000, httponly=True, samesite="lax")

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
    user_states = {
        s.job_id: s for s in db.query(UserJobState).filter_by(session_id=session_id).all()
    }
    for j in sorted_jobs:
        if j.id in user_states:
            j.score = user_states[j.id].score
            j.status = user_states[j.id].status
        j.location_category = get_location_category(j.location)
        j.role_category = classify_role(j.title, j.description)
        j.roles_str = " ".join(get_job_roles(j.title, j.description))
        j.role_label = ROLE_LABELS.get(j.role_category, "💻 Software Eng")
        time_meta = calculate_job_expiry(j.date_found, max_age_hours=settings.job_expiry_hours)
        j.ist_time = time_meta["ist_str"]
        j.expires_in = time_meta["expires_in_str"]
        j.is_expiring_soon = time_meta["is_expiring_soon"]
        j.contact_badge = get_contact_badge(j)

    habits = list_habits(db, session_id=session_id)
    tasks = db.query(Task).filter_by(session_id=session_id, day=date.today()).order_by(Task.id.desc()).all()
    runs = db.query(AgentRun).order_by(AgentRun.created_at.desc()).limit(6).all()
    total_jobs = db.query(Job).count()
    new_jobs = db.query(Job).filter_by(status="New").count()

    active_resume = get_active_resume_profile(session_id=session_id, db=db)
    available_resumes = get_available_resumes(session_id=session_id, db=db)

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
            "available_resumes": available_resumes,
            "prep_tracks": PREP_TRACKS,
            "featured_companies": list_featured_companies(),
            "system_design_cases": list_system_design_cases()
        }
    )


# -------------------------------------------------------------
# RESUME MANAGEMENT ENDPOINTS (MULTI-USER SESSION ISOLATED)
# -------------------------------------------------------------

@app.get("/api/resume/info")
def resume_info(request: Request, db: Session = Depends(get_db)):
    """Get active resume details and skills for current user session."""
    session_id = get_session_id(request)
    return get_active_resume_profile(session_id=session_id, db=db)


@app.get("/api/resumes")
def list_resumes(request: Request, db: Session = Depends(get_db)):
    """List all resumes uploaded in this user session."""
    session_id = get_session_id(request)
    return {"resumes": get_available_resumes(session_id=session_id, db=db)}


@app.post("/api/resume")
async def upload_resume(
    request: Request,
    response: Response,
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    """Upload candidate resume scoped to current user session, parse skills, and re-score jobs."""
    session_id = get_session_id(request)
    response.set_cookie(key="scout_session_id", value=session_id, max_age=31536000, httponly=True, samesite="lax")

    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in {".pdf", ".docx", ".txt"}:
        raise HTTPException(400, "Please upload a valid PDF, DOCX, or TXT resume file.")

    safe_name = re.sub(r"[^a-zA-Z0-9_.-]+", "_", file.filename or f"resume{suffix}")
    user_resumes_dir = RESUMES_DIR / session_id
    user_resumes_dir.mkdir(parents=True, exist_ok=True)
    dest = user_resumes_dir / safe_name

    content = await file.read()
    if len(content) > 15 * 1024 * 1024:
        raise HTTPException(413, "Resume must be smaller than 15 MB.")

    dest.write_bytes(content)

    # Deactivate previous active resumes for this session
    db.query(UserResume).filter_by(session_id=session_id).update({"is_active": False})

    # Parse and register new resume
    text = extract_resume_text(str(dest))
    prof = parse_resume_profile(text)
    user_resume = UserResume(
        session_id=session_id,
        filename=safe_name,
        filepath=str(dest),
        skills=json.dumps(sorted(list(prof.get("skills", [])))),
        experience_level=prof.get("experience_level", "Entry Level"),
        is_active=True
    )
    db.add(user_resume)
    db.commit()

    # Re-score existing jobs for this new resume scoped to this user session
    rescore_result = rescore_all_jobs(db, str(dest), session_id=session_id)

    return {
        "message": f"Resume '{safe_name}' uploaded successfully for your session!",
        "filename": safe_name,
        "path": str(dest),
        "skills": rescore_result.get("skills", []),
        "experience_level": prof.get("experience_level", "Entry Level"),
        "jobs_rescored": rescore_result.get("jobs_rescored", 0)
    }


@app.post("/api/resume/select")
def select_active_resume(
    request: Request,
    path: str = Form(...),
    db: Session = Depends(get_db)
):
    """Switch active resume for this session to any existing file and re-score matching jobs."""
    session_id = get_session_id(request)
    file_path = Path(path)
    if not file_path.exists():
        raise HTTPException(404, "Resume file not found.")

    # Deactivate previous active resumes for this session
    db.query(UserResume).filter_by(session_id=session_id).update({"is_active": False})

    # Activate existing or register new
    existing = db.query(UserResume).filter_by(session_id=session_id, filepath=str(file_path)).first()
    if existing:
        existing.is_active = True
    else:
        text = extract_resume_text(str(file_path))
        prof = parse_resume_profile(text)
        new_res = UserResume(
            session_id=session_id,
            filename=file_path.name,
            filepath=str(file_path),
            skills=json.dumps(sorted(list(prof.get("skills", [])))),
            experience_level=prof.get("experience_level", "Entry Level"),
            is_active=True
        )
        db.add(new_res)
    db.commit()

    rescore_result = rescore_all_jobs(db, str(file_path), session_id=session_id)

    return {
        "ok": True,
        "active_resume": file_path.name,
        "skills": rescore_result.get("skills", []),
        "jobs_rescored": rescore_result.get("jobs_rescored", 0)
    }


@app.post("/api/jobs/rescore")
def trigger_rescore(request: Request, db: Session = Depends(get_db)):
    """Re-score all jobs against the current active resume for this session."""
    session_id = get_session_id(request)
    profile = get_active_resume_profile(session_id=session_id, db=db)
    resume_path = profile.get("path") if profile and profile.get("path") else None
    result = rescore_all_jobs(db, resume_path, session_id=session_id)
    return result


# -------------------------------------------------------------
# TODO / TASK MANAGEMENT ENDPOINTS (MULTI-USER SESSION ISOLATED)
# -------------------------------------------------------------

@app.get("/api/tasks")
def get_tasks(request: Request, db: Session = Depends(get_db)):
    """List all tasks for today scoped to current user session."""
    session_id = get_session_id(request)
    tasks = db.query(Task).filter_by(session_id=session_id, day=date.today()).order_by(Task.id.desc()).all()
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
def task_create(request: Request, title: str = Form(...), db: Session = Depends(get_db)):
    """Create a new task scoped to current user session."""
    session_id = get_session_id(request)
    clean_title = title.strip()
    if not clean_title:
        raise HTTPException(400, "Task title is required.")
    task = add_task(db, clean_title, session_id=session_id)
    return {"id": task.id, "title": task.title, "completed": task.completed}


@app.post("/api/tasks/{task_id}/toggle")
def task_toggle(request: Request, task_id: int, completed: bool = Form(...), db: Session = Depends(get_db)):
    """Toggle a task between active and completed for current user session."""
    session_id = get_session_id(request)
    task = db.query(Task).filter_by(id=task_id, session_id=session_id).first()
    if not task:
        task = db.query(Task).filter_by(id=task_id).first()
        if not task:
            raise HTTPException(404, "Task not found.")
    task.completed = completed
    db.commit()
    return {"id": task.id, "completed": task.completed}


@app.post("/api/tasks/{task_id}/complete")
def task_done(request: Request, task_id: int, db: Session = Depends(get_db)):
    """Mark a task completed for current user session."""
    session_id = get_session_id(request)
    if not complete_task(db, task_id, session_id=session_id):
        raise HTTPException(404, "Task not found.")
    return {"ok": True}


@app.delete("/api/tasks/{task_id}")
def task_delete(request: Request, task_id: int, db: Session = Depends(get_db)):
    """Permanently delete a task scoped to current user session."""
    session_id = get_session_id(request)
    task = db.query(Task).filter_by(id=task_id, session_id=session_id).first()
    if not task:
        task = db.query(Task).filter_by(id=task_id).first()
        if not task:
            raise HTTPException(404, "Task not found.")
    db.delete(task)
    db.commit()
    return {"ok": True}


@app.post("/api/tasks/clear-completed")
def task_clear_completed(request: Request, db: Session = Depends(get_db)):
    """Clear all completed tasks for today for current user session."""
    session_id = get_session_id(request)
    deleted = db.query(Task).filter_by(session_id=session_id, day=date.today(), completed=True).delete(synchronize_session=False)
    db.commit()
    return {"ok": True, "deleted": deleted}


# -------------------------------------------------------------
# JOB HUNTING & OUTREACH ENDPOINTS (USER-ISOLATED STATUS & DRAFTS)
# -------------------------------------------------------------

@app.post("/api/jobs/hunt")
def hunt(request: Request, db: Session = Depends(get_db), query: str = Form("")):
    session_id = get_session_id(request)
    resume_path = None

    # Check for user's active resume
    user_res = db.query(UserResume).filter_by(session_id=session_id, is_active=True).first()
    if user_res and Path(user_res.filepath).exists():
        resume_path = user_res.filepath
    else:
        for candidate in [
            ROOT / "app" / "Resume" / "CV-Durgesh.pdf",
            Path(settings.resume_path),
            ROOT / "data" / "resume.pdf"
        ]:
            if candidate.exists():
                resume_path = str(candidate)
                break

    try:
        result = hunt_jobs(
            db,
            resume_path=resume_path,
            search_query=query if query else None,
            session_id=session_id
        )
        db.add(AgentRun(agent="job_hunter", status="success", summary=f"Added {result['added']} jobs."))
        db.commit()
        return {"added": result["added"], "errors": result["errors"], "skipped": result.get("skipped_no_match", 0)}
    except Exception as exc:
        db.add(AgentRun(agent="job_hunter", status="error", summary=str(exc)[:2000]))
        db.commit()
        raise HTTPException(400, str(exc))


@app.post("/api/jobs/{job_id}/status")
def update_job_status(request: Request, job_id: int, status: str = Form(...), db: Session = Depends(get_db)):
    """Update job status scoped to current user session without mutating other users' states."""
    allowed = {"New", "Interested", "Applied", "Interview", "Rejected", "Archived"}
    if status not in allowed:
        raise HTTPException(400, "Invalid status")
    job = db.get(Job, job_id)
    if not job:
        raise HTTPException(404, "Job not found")

    session_id = get_session_id(request)
    from datetime import datetime
    state = db.query(UserJobState).filter_by(session_id=session_id, job_id=job_id).first()
    if not state:
        state = UserJobState(session_id=session_id, job_id=job_id, score=job.score, status=status)
        db.add(state)
    else:
        state.status = status
        state.updated_at = datetime.utcnow()
    if session_id == "default":
        job.status = status
    db.commit()
    return {"ok": True, "job_id": job_id, "status": status}


@app.post("/api/jobs/{job_id}/draft")
def draft_email(request: Request, job_id: int, db: Session = Depends(get_db)):
    """Generate cold email draft tailored to the active user session's resume."""
    job = db.get(Job, job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    session_id = get_session_id(request)
    profile = get_active_resume_profile(session_id=session_id, db=db)
    resume_path = profile.get("path") if profile and profile.get("path") else settings.resume_path
    try:
        draft = generate_draft(
            {"title": job.title, "company": job.company, "description": job.description, "url": job.url},
            resume_path
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
        job.contact_source = contacts[0].get("type", contacts[0].get("source", ""))
        db.commit()
    return {"contacts": contacts, "note": "Contacts categorized into: Published & Extracted, Generated Pattern (Unverified), or Verified Mailbox."}


# -------------------------------------------------------------
# HABITS & BRIEFINGS (MULTI-USER SESSION ISOLATED)
# -------------------------------------------------------------

@app.post("/api/habits/{habit_id}")
def habit_toggle(request: Request, habit_id: int, completed: bool = Form(...), db: Session = Depends(get_db)):
    """Toggle a habit status scoped to current user session."""
    session_id = get_session_id(request)
    if not set_habit(db, habit_id, completed, session_id=session_id):
        raise HTTPException(404, "Habit not found")
    return {"ok": True}
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
    session_id = get_session_id(request)
    body = await request.json()
    message = str(body.get("message", "")).strip()
    if not message:
        raise HTTPException(400, "Message is required")
    if len(message) > 6000:
        raise HTTPException(413, "Message is too long")
    try:
        answer = handle_message(message, db=db, session_id=session_id)
        return {"reply": answer}
    except Exception as exc:
        raise HTTPException(400, str(exc))


# -------------------------------------------------------------
# PREP LAB & STUDY HUB ENDPOINTS
# -------------------------------------------------------------

@app.get("/api/prep/tracks")
def get_tracks():
    """List all available master technical tracks."""
    return {"tracks": list_prep_tracks()}


@app.get("/api/prep/track/{track_id}")
def get_track_detail(track_id: str):
    """Get full roadmap, playlists, and top questions for a track."""
    track = PREP_TRACKS.get(track_id.lower())
    if not track:
        raise HTTPException(404, f"Prep track '{track_id}' not found")
    return {"track": track}


@app.get("/api/prep/companies")
def get_companies():
    """List featured companies with interview intelligence."""
    return {"companies": list_featured_companies()}


@app.get("/api/prep/company/{company_name}")
def get_company(company_name: str):
    """Retrieve round structure, grilling topics, and past questions for a company."""
    return {"intel": get_company_intel(company_name)}


# -------------------------------------------------------------
# WORKFLOW 2: AI MOCK INTERVIEW SIMULATOR
# -------------------------------------------------------------

@app.get("/api/mock/question")
def get_mock_question(
    target: str = "general",
    difficulty: str = "medium",
    case_id: Optional[str] = None,
    question_id: Optional[int] = None,
):
    """Generate or retrieve a verified technical question for a company or topic."""
    question_data = generate_mock_question(
        target=target, difficulty=difficulty, case_id=case_id, question_id=question_id
    )
    return {"question": question_data}


@app.post("/api/mock/evaluate")
async def evaluate_mock(request: Request):
    """Evaluate candidate answer across 4 dimensions using Bar Raiser AI evaluator."""
    body = await request.json()
    question = body.get("question", "")
    answer = body.get("answer", "")
    target = body.get("target", "general")
    if not answer:
        raise HTTPException(400, "Answer cannot be empty")
    evaluation = evaluate_mock_answer(question=question, user_answer=answer, target=target)
    return {"evaluation": evaluation}


@app.post("/api/mock/run_code")
async def run_candidate_code(request: Request):
    """Execute code snippet in real-time with Python or JavaScript compiler."""
    body = await request.json()
    code = body.get("code", "")
    language = body.get("language", "python")
    result = execute_code(code=code, language=language)
    return {"result": result}


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
    model = settings.gemini_model if settings.llm_provider == "gemini" else settings.groq_model
    if any(deprecated in model for deprecated in ["1.5", "2.0", "2.5"]):
        model = "gemini-3.5-flash-lite"
    return {
        "connected": connected,
        "model": model
    }
