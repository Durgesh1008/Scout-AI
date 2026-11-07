import re
import time
import logging
from pathlib import Path
import requests
from sqlalchemy.orm import Session

from app.config import ROOT, settings
from app.database import SessionLocal, Job
from app.services.resume import extract_resume_text
from app.agents.job_hunter import (
    hunt_jobs,
    parse_resume_profile,
    rescore_all_jobs,
    get_location_category
)
from app.agents.routine_manager import generate_morning_briefing
from app.agents.orchestrator import handle_message
from app.scheduler import run_morning_pipeline

logger = logging.getLogger(__name__)

RESUMES_DIR = ROOT / "data" / "resumes"
RESUMES_DIR.mkdir(parents=True, exist_ok=True)


def download_telegram_file(base_url: str, token: str, file_id: str, original_filename: str) -> Path:
    """Download an attached document from Telegram servers and persist locally."""
    # 1. Get file path from Telegram
    get_file_url = f"{base_url}/getFile?file_id={file_id}"
    res = requests.get(get_file_url, timeout=20)
    res.raise_for_status()
    file_info = res.json().get("result", {})
    file_path = file_info.get("file_path")

    if not file_path:
        raise ValueError("Could not retrieve file path from Telegram API.")

    # 2. Download raw file content
    download_url = f"https://api.telegram.org/file/bot{token}/{file_path}"
    file_res = requests.get(download_url, timeout=60)
    file_res.raise_for_status()

    # 3. Clean filename and save to data/resumes/
    safe_name = re.sub(r"[^a-zA-Z0-9_.-]+", "_", original_filename or "resume.pdf")
    if not safe_name.lower().endswith((".pdf", ".docx", ".txt")):
        safe_name += ".pdf"

    dest = RESUMES_DIR / safe_name
    dest.write_bytes(file_res.content)
    logger.info(f"Downloaded Telegram resume attachment to {dest}")
    return dest


def handle_document_upload(document: dict, chat_id: str, base_url: str, token: str) -> str:
    """Handle resume file sent directly via Telegram chat."""
    file_name = document.get("file_name", "resume.pdf")
    file_id = document.get("file_id")
    suffix = Path(file_name).suffix.lower()

    if suffix not in {".pdf", ".docx", ".txt"}:
        return (
            "⚠️ *Unsupported File Format*\n\n"
            f"You sent `{file_name}`. Please upload a `.pdf`, `.docx`, or `.txt` resume file."
        )

    send_reply(base_url, chat_id, f"📥 *Downloading and analyzing* `{file_name}`...")

    db: Session = SessionLocal()
    try:
        # Download and persist
        dest_path = download_telegram_file(base_url, token, file_id, file_name)

        # Update active resume path
        settings.resume_path = str(dest_path)

        # Update .env
        env_path = ROOT / ".env"
        if env_path.exists():
            lines = env_path.read_text(encoding="utf-8").splitlines()
            updated = False
            for idx, line in enumerate(lines):
                if line.startswith("RESUME_PATH="):
                    lines[idx] = f"RESUME_PATH={dest_path}"
                    updated = True
            if not updated:
                lines.append(f"RESUME_PATH={dest_path}")
            env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

        # Automatically re-score all jobs for this new resume
        rescore_res = rescore_all_jobs(db, str(dest_path))
        skills = rescore_res.get("skills", [])
        exp = rescore_res.get("experience_level", "Entry / Fresher")
        rescored_count = rescore_res.get("jobs_rescored", 0)

        skills_bullets = "\n".join(f"• `{s}`" for s in skills[:12]) if skills else "• None automatically extracted"

        return (
            f"✅ *Resume Successfully Activated!*\n\n"
            f"📄 *File:* `{file_name}`\n"
            f"🎯 *Level:* *{exp}*\n"
            f"💡 *Extracted Skills ({len(skills)} total):*\n{skills_bullets}\n\n"
            f"📊 *Re-scored {rescored_count} opportunities in your database!*\n\n"
            f"👉 Send `/jobs` to see your top matched jobs for this resume\n"
            f"👉 Send `/hunt` to fetch fresh matching jobs now\n"
            f"👉 Send `/run` to trigger the full morning pipeline"
        )
    except Exception as e:
        logger.error(f"Failed to process Telegram resume upload: {e}")
        return f"⚠️ *Failed to process resume:* {e}"
    finally:
        db.close()


def handle_command(text: str, chat_id: str) -> str:
    """Handle text commands and queries from Telegram."""
    db: Session = SessionLocal()
    try:
        cmd = text.lower().strip()

        if cmd in {"/start", "/help"}:
            return (
                "🤖 *Welcome to Scout-AI Mobile Controller!*\n\n"
                "You can control your agent and manage resumes right here:\n\n"
                "• 📎 *Upload Resume:* Simply attach & send any PDF or DOCX file!\n"
                "• `/resume` - View your active resume & extracted skills\n"
                "• `/jobs` - View top matched jobs for active resume\n"
                "• `/hunt` - Hunt 50-70+ new jobs across web sources\n"
                "• `/run` - Run full pipeline (hunt + Gmail drafts + briefing)\n"
                "• `/briefing` - Today's priorities & schedule\n"
                "• `/tasks` - View today's todo list\n"
                "• Or ask any question to chat with Scout-AI!"
            )

        elif cmd == "/resume":
            p = Path(settings.resume_path)
            if not p.exists():
                return "📄 *No active resume found.* Simply attach and send any PDF/DOCX file here to set your resume!"
            try:
                prof = parse_resume_profile(extract_resume_text(str(p)))
                skills = prof.get("skills", set())
                skills_str = ", ".join(sorted(list(skills))[:12]) if skills else "None detected"
                return (
                    f"📄 *Current Active Resume:* `{p.name}`\n"
                    f"🎯 *Experience Level:* *{prof.get('experience_level', 'Unknown')}*\n"
                    f"💡 *Key Skills:* {skills_str}\n\n"
                    f"📥 *Want to update?* Attach and send a new PDF/DOCX file anytime!"
                )
            except Exception as e:
                return f"📄 *Active Resume:* `{p.name}` (Error reading details: {e})"

        elif cmd == "/run":
            res = run_morning_pipeline()
            return (
                f"✅ *Morning Pipeline Completed!*\n\n"
                f"• Jobs Added: {res.get('jobs_added', 0)}\n"
                f"• Cold Outreach Drafts Created in Gmail: {res.get('drafts_created', 0)}\n"
                f"Check your Gmail Drafts and Discord channel!"
            )

        elif cmd == "/hunt":
            result = hunt_jobs(db)
            jobs = result.get("jobs", [])
            if not jobs:
                return "No new jobs found exceeding match threshold right now."

            # Sort with India on top, then Remote, then others
            def job_rank(j):
                cat = get_location_category(j.location)
                prio = 0 if cat == "india" else (1 if cat == "remote" else 2)
                return (prio, -j.score)

            sorted_jobs = sorted(jobs, key=job_rank)
            india_remote = [j for j in sorted_jobs if get_location_category(j.location) in {"india", "remote"}]
            out_of_india = [j for j in sorted_jobs if get_location_category(j.location) == "out_of_india"]

            lines = [f"🎯 *Found {len(jobs)} New Matching Jobs (India & Remote on top):*"]
            for j in india_remote[:5]:
                cat = get_location_category(j.location)
                loc_icon = "🇮🇳 India" if cat == "india" else "🌐 Remote"
                lines.append(f"• *{j.title}* at {j.company}\n  📍 [{loc_icon}] {j.location} | 🎯 `{j.score}% match`\n  🔗 {j.url}")

            if out_of_india:
                lines.append("\n🌍 *Out of India Roles (Secondary Filter):*")
                for j in out_of_india[:2]:
                    lines.append(f"• *{j.title}* at {j.company} (`{j.score}% match`)\n  📍 🌍 {j.location}\n  🔗 {j.url}")

            return "\n\n".join(lines)

        elif cmd == "/briefing":
            return generate_morning_briefing(db)

        elif cmd == "/jobs":
            all_jobs = db.query(Job).all()
            if not all_jobs:
                return "No jobs in database yet. Send `/hunt` to fetch jobs!"

            # Sort with India on top, then Remote, then others
            def job_rank(j):
                cat = get_location_category(j.location)
                prio = 0 if cat == "india" else (1 if cat == "remote" else 2)
                return (prio, -j.score)

            sorted_jobs = sorted(all_jobs, key=job_rank)
            india_remote = [j for j in sorted_jobs if get_location_category(j.location) in {"india", "remote"}]
            out_of_india = [j for j in sorted_jobs if get_location_category(j.location) == "out_of_india"]

            lines = ["📋 *Top Matched Jobs (🇮🇳 India & 🌐 Remote on top):*"]
            for j in india_remote[:6]:
                cat = get_location_category(j.location)
                loc_badge = "🇮🇳 India" if cat == "india" else "🌐 Remote"
                lines.append(f"• *{j.title}* at {j.company}\n  📍 [{loc_badge}] {j.location} | 🎯 `{j.score}% match`\n  📊 Status: `{j.status}`\n  🔗 {j.url}")

            if out_of_india:
                lines.append("\n🌍 *Out of India Roles (Secondary Filter):*")
                for j in out_of_india[:2]:
                    lines.append(f"• *{j.title}* at {j.company} (`{j.score}% match`)\n  📍 🌍 {j.location}\n  🔗 {j.url}")

            return "\n\n".join(lines)

        elif cmd in {"/tasks", "/todos"}:
            from datetime import date
            from app.database import Task
            tasks = db.query(Task).filter_by(day=date.today()).all()
            if not tasks:
                return "No tasks on your list today! Say 'Add task: [your task]' to create one."
            lines = ["📝 *Your Todo List Today:*"]
            for t in tasks:
                lines.append(f"{'✅' if t.completed else '⬜'} {t.title}")
            return "\n\n".join(lines)

        else:
            return handle_message(text, db=db)

    except Exception as e:
        return f"⚠️ Error executing command: {e}"
    finally:
        db.close()


def send_reply(base_url: str, chat_id: str, text: str):
    """Deliver reply message to Telegram."""
    try:
        requests.post(
            f"{base_url}/sendMessage",
            json={"chat_id": chat_id, "text": text[:4000], "parse_mode": "Markdown", "disable_web_page_preview": True},
            timeout=15
        )
    except Exception:
        try:
            requests.post(
                f"{base_url}/sendMessage",
                json={"chat_id": chat_id, "text": text[:4000], "disable_web_page_preview": True},
                timeout=15
            )
        except Exception as e:
            logger.error(f"Failed to send Telegram reply: {e}")


def run_bot():
    token = settings.telegram_bot_token
    if not token:
        print("\n[!] TELEGRAM_BOT_TOKEN is not configured.")
        return

    base_url = f"https://api.telegram.org/bot{token}"
    print(f"\n[*] Scout-AI Mobile Telegram Bot is ACTIVE on @sccoout_bot!")
    print(f"[*] Send messages, commands, or ATTACH RESUMES (.pdf/.docx) from your phone.\n")

    last_update_id = 0

    while True:
        try:
            url = f"{base_url}/getUpdates?offset={last_update_id + 1}&timeout=30"
            res = requests.get(url, timeout=35)
            if res.status_code != 200:
                time.sleep(3)
                continue

            data = res.json()
            for update in data.get("result", []):
                last_update_id = update["update_id"]
                message = update.get("message", {})
                chat_id = str(message.get("chat", {}).get("id", ""))

                if not chat_id:
                    continue

                # Auto-capture chat_id if not configured
                if not settings.telegram_chat_id:
                    settings.telegram_chat_id = chat_id
                    env_path = ROOT / ".env"
                    if env_path.exists():
                        lines = env_path.read_text(encoding="utf-8").splitlines()
                        has_chat = False
                        for idx, line in enumerate(lines):
                            if line.startswith("TELEGRAM_CHAT_ID="):
                                lines[idx] = f"TELEGRAM_CHAT_ID={chat_id}"
                                has_chat = True
                        if not has_chat:
                            lines.append(f"TELEGRAM_CHAT_ID={chat_id}")
                        env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

                # Check if message contains a document (e.g. resume upload)
                document = message.get("document")
                if document:
                    print(f"[Mobile Resume Upload] Received {document.get('file_name')} from chat {chat_id}")
                    reply = handle_document_upload(document, chat_id, base_url, token)
                    send_reply(base_url, chat_id, reply)
                    continue

                # Otherwise handle text command
                text = str(message.get("text", "")).strip()
                if not text:
                    continue

                print(f"[Mobile Command] Received from chat {chat_id}: {text}")
                reply = handle_command(text, chat_id)
                send_reply(base_url, chat_id, reply)

        except Exception as e:
            logger.error(f"Telegram polling error: {e}")
            time.sleep(3)


if __name__ == "__main__":
    run_bot()
