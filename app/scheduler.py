import sys
import logging
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal, Job, AgentRun
from app.agents.job_hunter import hunt_jobs
from app.agents.email_drafter import generate_draft, save_local_draft, create_gmail_draft
from app.agents.routine_manager import ensure_habits, generate_morning_briefing
from app.services.notifications import notify

logger = logging.getLogger(__name__)

scheduler = BackgroundScheduler(timezone=settings.timezone)


def run_morning_pipeline() -> dict:
    """
    Complete end-to-end autonomous morning execution pipeline:
    1. Initialize habits & routines
    2. Hunt, score, deduplicate jobs & export leads to CSV
    3. Auto-draft outreach emails for top 3 matched jobs into Gmail Drafts & local storage
    4. Generate executive daily morning briefing (Top 5 tasks, job targets, habits)
    5. Dispatch alerts via Telegram, Discord, and Windows Desktop Notification
    """
    logger.info("--- Starting Autonomous Morning Pipeline ---")
    db: Session = SessionLocal()
    pipeline_result = {
        "timestamp": datetime.now().isoformat(),
        "jobs_added": 0,
        "drafts_created": 0,
        "notification_status": {},
        "status": "pending"
    }

    try:
        # Step 1: Ensure daily habit checklist
        ensure_habits(db)

        # Step 2: Autonomous Job Hunting & CSV Tracking
        hunt_result = hunt_jobs(db)
        pipeline_result["jobs_added"] = hunt_result.get("added", 0)

        # Step 3: Fetch top new matches for today
        top_jobs = (
            db.query(Job)
            .filter_by(status="New")
            .order_by(Job.score.desc())
            .limit(3)
            .all()
        )

        # Step 4: Auto-generate cold outreach drafts for top jobs
        drafts_count = 0
        for job in top_jobs:
            try:
                job_dict = {
                    "title": job.title,
                    "company": job.company,
                    "description": job.description,
                    "url": job.url
                }
                draft = generate_draft(job_dict, settings.resume_path)
                save_local_draft(job_dict, draft, job.recruiter_email)

                # Push to Gmail Drafts folder if configured
                create_gmail_draft(draft, job.recruiter_email, job.url)
                drafts_count += 1
            except Exception as draft_err:
                logger.warning(f"Failed to draft email for job {job.id} ({job.company}): {draft_err}")

        pipeline_result["drafts_created"] = drafts_count

        # Step 5: Generate Morning Briefing
        briefing_text = generate_morning_briefing(db, top_jobs=top_jobs)

        # Step 6: Dispatch Notifications (Telegram, Discord, Desktop)
        notify_status = notify(
            message=briefing_text,
            title=f"🌅 Scout-AI: {pipeline_result['jobs_added']} New Jobs & Daily Plan"
        )
        pipeline_result["notification_status"] = notify_status

        # Step 7: Record Run Audit in SQLite
        summary_msg = (
            f"Morning run completed. Added {pipeline_result['jobs_added']} jobs. "
            f"Generated {drafts_count} outreach drafts."
        )
        db.add(AgentRun(agent="morning_pipeline", status="success", summary=summary_msg))
        db.commit()

        pipeline_result["status"] = "success"
        logger.info(summary_msg)

    except Exception as exc:
        db.rollback()
        err_msg = f"Morning pipeline failed: {exc}"
        logger.error(err_msg)
        db.add(AgentRun(agent="morning_pipeline", status="error", summary=str(exc)[:2000]))
        db.commit()
        pipeline_result["status"] = "error"
        pipeline_result["error"] = str(exc)

    finally:
        db.close()

    return pipeline_result


def run_hourly_cleanup():
    """Auto-deletes unreviewed jobs older than 18 hours based on Indian Standard Time."""
    db: Session = SessionLocal()
    try:
        from app.agents.job_hunter import cleanup_expired_jobs
        deleted = cleanup_expired_jobs(db, max_age_hours=settings.job_expiry_hours)
        if deleted > 0:
            logger.info(f"Hourly auto-cleanup: Removed {deleted} expired jobs.")
    except Exception as e:
        logger.warning(f"Hourly cleanup error: {e}")
    finally:
        db.close()


def start_scheduler():
    """Start background scheduler on the configured morning time and hourly cleanup."""
    if scheduler.running:
        return

    try:
        hour, minute = map(int, settings.morning_time.split(":"))
        scheduler.add_job(
            run_morning_pipeline,
            CronTrigger(hour=hour, minute=minute, timezone=settings.timezone),
            id="daily_morning_pipeline",
            replace_existing=True,
            max_instances=1,
            coalesce=True
        )
        # Periodic 18-hour auto-clean check
        scheduler.add_job(
            run_hourly_cleanup,
            "interval",
            hours=1,
            id="hourly_job_cleanup",
            replace_existing=True
        )
        scheduler.start()
        logger.info(f"Morning scheduler active: triggers daily at {settings.morning_time} ({settings.timezone}) with hourly 18h cleanup")
    except Exception as e:
        logger.error(f"Failed to start scheduler: {e}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    if "--now" in sys.argv:
        print("Executing Autonomous Morning Pipeline immediately...")
        res = run_morning_pipeline()
        print(f"Pipeline Result: {res}")
    else:
        print(f"Starting scheduler daemon (will run daily at {settings.morning_time} {settings.timezone}). Press Ctrl+C to exit.")
        start_scheduler()
        try:
            import time
            while True:
                time.sleep(1)
        except (KeyboardInterrupt, SystemExit):
            scheduler.shutdown()
