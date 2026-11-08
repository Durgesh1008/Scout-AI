import logging
from datetime import date, datetime
from typing import List, Optional
from sqlalchemy.orm import Session

from app.database import HabitLog, Task, Job
from app.services.llm import generate

logger = logging.getLogger(__name__)

DEFAULT_HABITS = [
    "DSA & LeetCode (2 problems)",
    "Core Full-Stack Dev (Project work)",
    "System Design / Reading",
    "Physical Exercise (30m)",
    "Networking / 3 Job Applications"
]


def ensure_habits(db: Session, session_id: str = "default"):
    """Ensure standard habit tracker rows exist for today for this specific user session."""
    today = date.today()
    for name in DEFAULT_HABITS:
        if not db.query(HabitLog).filter_by(session_id=session_id, habit=name, day=today).first():
            db.add(HabitLog(session_id=session_id, habit=name, day=today, completed=False))
    db.commit()


def list_habits(db: Session, session_id: str = "default") -> List[HabitLog]:
    """Retrieve habits for today scoped to the user session."""
    ensure_habits(db, session_id=session_id)
    return db.query(HabitLog).filter_by(session_id=session_id, day=date.today()).order_by(HabitLog.id).all()


def set_habit(db: Session, habit_id: int, completed: bool, session_id: str = "default") -> bool:
    """Toggle a habit status for the user session."""
    item = db.query(HabitLog).filter_by(id=habit_id, session_id=session_id, day=date.today()).first()
    if not item:
        # Fallback by id if session_id wasn't set on legacy row
        item = db.query(HabitLog).filter_by(id=habit_id, day=date.today()).first()
        if not item:
            return False
    item.completed = completed
    db.commit()
    return True


def add_task(db: Session, title: str, session_id: str = "default") -> Task:
    """Add a new task for today scoped to the user session."""
    task = Task(session_id=session_id, title=title.strip(), day=date.today())
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def complete_task(db: Session, task_id: int, session_id: str = "default") -> bool:
    """Mark a task as completed for this user session."""
    query = db.query(Task).filter_by(id=task_id, day=date.today())
    if session_id:
        query = query.filter_by(session_id=session_id)
    task = query.first()
    if not task:
        return False
    task.completed = True
    db.commit()
    return True


def get_top_5_priorities(db: Session, session_id: str = "default") -> List[str]:
    """
    Retrieve or synthesize the top 5 priority tasks for today for this user session.
    Combines user's pending tasks and system high-impact objectives.
    """
    tasks = db.query(Task).filter_by(session_id=session_id, day=date.today(), completed=False).all()
    priorities = [t.title for t in tasks]

    # Defaults if user has fewer than 5 tasks
    standard_fillers = [
        "Review & submit top cold outreach drafts for matched jobs",
        "Push clean commit to active GitHub project",
        "Solve 1 Medium Tree/Graph DSA problem",
        "Read 1 tech architecture/engineering blog post",
        "Update personal portfolio / LinkedIn showcase"
    ]

    for filler in standard_fillers:
        if len(priorities) >= 5:
            break
        if filler not in priorities:
            priorities.append(filler)

    return priorities[:5]


def generate_morning_briefing(db: Session, top_jobs: Optional[List[Job]] = None) -> str:
    """
    Generate an executive Daily Morning Briefing covering:
    1. Top 5 priority tasks
    2. Target job applications for the day
    3. Daily schedule & habit tracker
    4. Energizing tactical focus
    """
    habits = list_habits(db)
    priorities = get_top_5_priorities(db)

    # If top_jobs not provided, query the highest scoring new jobs
    if top_jobs is None:
        top_jobs = (
            db.query(Job)
            .filter_by(status="New")
            .order_by(Job.score.desc())
            .limit(5)
            .all()
        )

    job_text = "\n".join(
        f"- {j.title} at {j.company} (Match: {j.score}%) [URL: {j.url}]"
        for j in top_jobs
    ) or "No new jobs found today. Backlog is clear!"

    priority_text = "\n".join(f"{idx+1}. {p}" for idx, p in enumerate(priorities))

    habit_text = "\n".join(
        f"[{'X' if h.completed else ' '}] {h.habit}"
        for h in habits
    )

    prompt = f"""
Act as an elite personal executive chief of staff and software mentor.
Generate an inspiring, structured Daily Morning Briefing for today ({date.today().strftime('%A, %B %d, %Y')}).

Structure the briefing with these exact sections:
🌅 1. DAILY FOCUS & TOP 5 PRIORITIES
{priority_text}

🎯 2. HIGH-MATCH JOB TARGETS FOR TODAY
{job_text}

⚡ 3. HABIT & ROUTINE PROTOCOL
{habit_text}

💡 4. ARCHITECTURAL / MINDSET INSIGHT
Provide a sharp, 1-2 sentence engineering/mindset tip for high performance.

Keep the total message punchy, professional, and directly actionable.
"""

    return generate(
        prompt,
        system="You are Scout-AI, an executive personal career and productivity assistant.",
        temperature=0.3
    )


def generate_eod_feedback(db: Session) -> str:
    """
    End-of-day habit and task completion review.
    """
    habits = list_habits(db)
    completed_habits = sum(1 for h in habits if h.completed)
    total_habits = len(habits)

    tasks = db.query(Task).filter_by(day=date.today()).all()
    completed_tasks = sum(1 for t in tasks if t.completed)
    total_tasks = len(tasks)

    prompt = f"""
Provide an end-of-day productivity review:
Date: {date.today()}
Habits Completed: {completed_habits} / {total_habits}
Tasks Completed: {completed_tasks} / {total_tasks}

Give an honest, encouraging, and constructive 3-paragraph evaluation with actionable advice for tomorrow.
"""
    return generate(
        prompt,
        system="You are an empathetic, disciplined performance coach.",
        temperature=0.4
    )


# Backward compatibility
briefing = generate_morning_briefing
