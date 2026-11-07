import json
import logging
import re
from typing import Optional
from datetime import date
from sqlalchemy.orm import Session

from app.agents.job_hunter import hunt_jobs
from app.agents.routine_manager import briefing, add_task
from app.database import Job, Task, HabitLog
from app.services.llm import generate, LLMError

logger = logging.getLogger(__name__)


def _extract_action(user_message: str) -> dict:
    """Fast local intent recognition (0ms) without wasting an LLM roundtrip."""
    msg = user_message.strip()
    msg_lower = msg.lower()

    # 1. Job search intents
    if any(kw in msg_lower for kw in ["find job", "search job", "hunt job", "looking for job", "new job", "get jobs"]):
        # Extract query if user said "find python jobs" or "find jobs for MERN"
        query = re.sub(r"^(?:please\s+)?(?:find|search|hunt|look for|get)\s+(?:me\s+)?(?:some\s+)?(?:jobs?\s+(?:for|in)?|new\s+jobs?\s*)?", "", msg, flags=re.I).strip()
        return {"action": "hunt_jobs", "query": query}

    # 2. View saved jobs
    if any(kw in msg_lower for kw in ["show job", "my job", "saved job", "list job", "view job", "matched jobs"]):
        return {"action": "list_jobs"}

    # 3. Daily briefing
    if any(kw in msg_lower for kw in ["briefing", "daily plan", "morning plan", "today's plan", "my plan"]):
        return {"action": "daily_briefing"}

    # 4. Add task / todo
    if any(msg_lower.startswith(prefix) for prefix in ["add task", "add todo", "create task", "create todo", "new task", "new todo"]):
        title = re.sub(r"^(?:add task|add todo|create task|create todo|new task|new todo)[:\s]+", "", msg, flags=re.I).strip()
        return {"action": "add_task", "title": title}

    # 5. List tasks / todos
    if any(kw in msg_lower for kw in ["my tasks", "list tasks", "show tasks", "my todos", "list todos", "show todos", "what are my tasks"]):
        return {"action": "list_tasks"}

    # 6. List habits
    if any(kw in msg_lower for kw in ["my habits", "list habits", "show habits", "routine", "habit progress"]):
        return {"action": "list_habits"}

    # Default to direct chat
    return {"action": "chat"}


def _handle_hunt_jobs(db: Session, query: str) -> str:
    """Execute job hunt with optional search query."""
    try:
        result = hunt_jobs(db, search_query=query if query else None)
        parts = [f"✅ Job search completed! Added **{result['added']}** new matching jobs."]

        if result.get("skipped_no_match", 0) > 0:
            parts.append(f"ℹ️ Skipped {result['skipped_no_match']} jobs below your match threshold.")

        if result.get("errors"):
            parts.append("⚠️ Errors: " + "; ".join(result["errors"]))

        if result.get("jobs"):
            parts.append("\n**Top Matches for Your Resume:**")
            for job in result["jobs"][:5]:
                parts.append(f"• **{job.title}** at {job.company} — `{job.score}% match`\n  <{job.url}>")

        return "\n".join(parts)
    except Exception as e:
        logger.error(f"Job hunt failed: {e}")
        return f"Job search failed: {str(e)}"


def _handle_list_jobs(db: Session) -> str:
    """Show saved jobs."""
    jobs = db.query(Job).order_by(Job.score.desc()).limit(8).all()
    if not jobs:
        return "No saved jobs yet! Ask me to 'Find jobs' or upload a resume to get started."

    lines = ["📋 **Your Top Matched Opportunities:**\n"]
    for i, job in enumerate(jobs, 1):
        lines.append(f"{i}. **{job.title}** at {job.company} (`{job.score}% match`)")
        lines.append(f"   Status: `{job.status}` | Location: {job.location}")
        lines.append(f"   Link: {job.url}\n")

    return "\n".join(lines)


def _handle_daily_briefing(db: Session) -> str:
    """Generate daily briefing."""
    jobs = db.query(Job).filter_by(status="New").order_by(Job.score.desc()).limit(5).all()
    return briefing(db, jobs)


def _handle_add_task(db: Session, title: str) -> str:
    """Fast inline task creation."""
    if not title:
        return "Please specify what task you'd like to add. Example: 'Add task: review resume'"
    task = add_task(db, title)
    return f"✅ Added to your Todo list: **{task.title}**"


def _handle_list_tasks(db: Session) -> str:
    """List today's tasks."""
    tasks = db.query(Task).filter_by(day=date.today()).order_by(Task.id.desc()).all()
    if not tasks:
        return "No tasks on your list today! Say 'Add task: [your task]' to create one."

    lines = ["📝 **Your Tasks for Today:**\n"]
    for task in tasks:
        status = "✅" if task.completed else "⬜"
        lines.append(f"{status} {task.title}")

    return "\n".join(lines)


def _handle_list_habits(db: Session) -> str:
    """List today's habits."""
    from app.agents.routine_manager import list_habits
    habits = list_habits(db)
    if not habits:
        return "No habits configured for today."

    completed = sum(1 for h in habits if h.completed)
    lines = [f"⚡ **Habit Progress: {completed}/{len(habits)} completed**\n"]
    for habit in habits:
        status = "✅" if habit.completed else "⬜"
        lines.append(f"{status} {habit.habit}")

    return "\n".join(lines)


def _handle_chat(db: Session, message: str) -> str:
    """Fast, single-call conversational handler."""
    today = date.today()
    pending_tasks = db.query(Task).filter_by(day=today, completed=False).count()
    new_jobs = db.query(Job).filter_by(status="New").count()

    system_prompt = (
        f"You are Scout-AI, a sharp, ultra-fast personal assistant. "
        f"Keep responses concise, clear, and direct (max 2-3 short paragraphs). "
        f"Context: {pending_tasks} pending tasks today, {new_jobs} new jobs available."
    )

    try:
        return generate(message, system=system_prompt, temperature=0.3)
    except Exception as e:
        return f"I ran into an issue connecting to the AI model: {e}"


def handle_message(message: str, db: Session) -> str:
    """Main routing entrypoint with zero-overhead intent dispatcher."""
    try:
        plan = _extract_action(message)
        action = plan.get("action", "chat")

        if action == "hunt_jobs":
            return _handle_hunt_jobs(db, plan.get("query", ""))
        elif action == "list_jobs":
            return _handle_list_jobs(db)
        elif action == "daily_briefing":
            return _handle_daily_briefing(db)
        elif action == "add_task":
            return _handle_add_task(db, plan.get("title", ""))
        elif action == "list_tasks":
            return _handle_list_tasks(db)
        elif action == "list_habits":
            return _handle_list_habits(db)
        else:
            return _handle_chat(db, message)

    except Exception as e:
        logger.error(f"Error handling message: {e}", exc_info=True)
        return f"Error: {str(e)}"
