import json
import logging
import re
import time
import imaplib
from email.message import EmailMessage
from datetime import datetime
from pathlib import Path
from typing import Dict, Any

from app.config import ROOT, settings
from app.services.llm import generate
from app.services.resume import extract_resume_text

logger = logging.getLogger(__name__)

DRAFT_DIR = ROOT / "data" / "drafts"
DRAFT_DIR.mkdir(parents=True, exist_ok=True)


def extract_candidate_name(resume_text: str) -> str:
    """Extract candidate name from first lines of resume, with safe default."""
    lines = [l.strip() for l in resume_text.splitlines() if l.strip()]
    if lines:
        first = lines[0]
        if len(first.split()) <= 4 and not any(c in first.lower() for c in ["@", "http", "www", ":", "|", "curriculum", "resume", "page"]):
            return first.title()
    return "Durgesh"


def generate_template_draft(job: dict, resume_text: str = "") -> Dict[str, str]:
    """
    Deterministic, high-converting cold email template fallback.
    Guarantees that drafting never fails even during LLM API outages or rate limits.
    """
    candidate_name = extract_candidate_name(resume_text)
    job_title = job.get("title", "Software Engineer").strip()
    company = job.get("company", "the team").strip()

    tech_catalog = [
        "React", "Node.js", "Python", "FastAPI", "JavaScript", "TypeScript",
        "SQL", "PostgreSQL", "MongoDB", "Express", "Docker", "Git", "REST APIs"
    ]
    matched = [s for s in tech_catalog if s.lower() in (resume_text or "").lower()]
    if not matched:
        matched = ["React", "Node.js", "Python", "REST APIs"]
    top_skills = ", ".join(matched[:3])

    subject = f"Application / Inquiry: {job_title} - {candidate_name}"
    body = (
        f"Hi {company} Hiring Team,\n\n"
        f"I came across the {job_title} role at {company} and was immediately drawn to the work your engineering team is shipping.\n\n"
        f"As a developer with hands-on experience across {top_skills}, I focus on building responsive web applications and reliable, performant backend REST APIs. "
        f"I have delivered production-ready features, maintained clean version control workflows, and designed scalable data interfaces.\n\n"
        f"I would welcome the opportunity to connect for a quick 10-minute sync to discuss how my skill set and enthusiasm can support {company}'s current technical roadmap.\n\n"
        f"Best regards,\n"
        f"{candidate_name}\n"
        f"Full Stack Developer"
    )
    return {"subject": subject, "body": body}


def generate_draft(job: dict, resume_path: str) -> Dict[str, str]:
    """
    Generate a concise, highly personalized cold outreach email.
    Uses LLM when available, seamlessly falling back to a structured template
    so drafting never fails.
    """
    resume = ""
    if resume_path and Path(resume_path).exists():
        try:
            resume = extract_resume_text(resume_path)
        except Exception as e:
            logger.warning(f"Error reading resume at {resume_path}: {e}")

    if not resume:
        for alt in [
            ROOT / "app" / "Resume" / "CV-Durgesh.pdf",
            ROOT / "data" / "resume.pdf",
            Path(settings.resume_path)
        ]:
            if alt.exists():
                try:
                    resume = extract_resume_text(str(alt))
                    break
                except Exception:
                    pass

    if not resume:
        resume = (
            "Durgesh - Full Stack Developer\n"
            "Skills: Python, FastAPI, JavaScript, React, Node.js, Express, MongoDB, PostgreSQL, SQL, Docker, Git, REST APIs, HTML/CSS.\n"
            "Experience: Full Stack Projects, API design, frontend interfaces, microservices, and modern web application development."
        )

    job_title = job.get("title", "Software Engineer")
    company = job.get("company", "the team")
    description = job.get("description", "")[:4000]

    system_instruction = (
        "You are an expert tech career coach and executive copywriter. "
        "Write concise, high-converting cold outreach emails to tech recruiters or engineering leaders. "
        "Never invent experience or fake metrics. Reference only facts from the resume. "
        "Keep the pitch crisp, under 130 words."
    )

    prompt = f"""
Write a personalized cold email pitch to a recruiter or hiring manager.

Guidelines:
1. Max 130 words.
2. Subject line should be relevant and specific (e.g., Application / Inquiry: [Role] - [Candidate Name]).
3. Identify 2 core skills or stack components from the resume that directly match the job requirements.
4. Conclude with a low-friction call to action (e.g., a brief 10-minute sync or reviewing the GitHub/portfolio).
5. Output MUST be ONLY valid JSON with keys: "subject" and "body".

CANDIDATE RESUME:
{resume[:6000]}

TARGET JOB:
Role: {job_title}
Company: {company}
Description:
{description}
"""

    try:
        raw = generate(prompt, system=system_instruction, temperature=0.2)
        raw_cleaned = re.sub(r"```json\s*", "", raw)
        raw_cleaned = re.sub(r"```\s*", "", raw_cleaned).strip()

        match = re.search(r"\{.*\}", raw_cleaned, re.DOTALL)
        if match:
            data = json.loads(match.group())
            subject = str(data.get("subject", f"Inquiry regarding {job_title} at {company}")).strip()
            body = str(data.get("body", "")).strip()
            if subject and body:
                return {
                    "subject": subject,
                    "body": body
                }
    except Exception as exc:
        logger.warning(f"AI draft generation failed ({exc}). Falling back to template draft.")

    return generate_template_draft(job, resume)


def save_local_draft(job: dict, draft: dict, recipient: str = "") -> str:
    """Save the draft email locally in text format for manual inspection."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_company = re.sub(r"[^a-zA-Z0-9_-]+", "_", job.get("company", "Company"))[:30]
    safe_title = re.sub(r"[^a-zA-Z0-9_-]+", "_", job.get("title", "Role"))[:30]
    filename = f"{timestamp}_{safe_company}_{safe_title}.txt"

    file_path = DRAFT_DIR / filename
    content = (
        f"To: {recipient or 'recruiter@company.com'}\n"
        f"Subject: {draft['subject']}\n"
        f"Job Title: {job.get('title', '')}\n"
        f"Company: {job.get('company', '')}\n"
        f"Job URL: {job.get('url', '')}\n"
        f"Created At: {datetime.now().isoformat()}\n"
        f"---------------------------------------------------\n\n"
        f"{draft['body']}\n"
    )

    file_path.write_text(content, encoding="utf-8")
    logger.info(f"Saved local draft to {file_path}")
    return str(file_path.relative_to(ROOT))


def create_gmail_draft(draft: dict, recipient: str = "", job_url: str = "") -> Dict[str, Any]:
    """
    Create a draft directly in the user's Gmail Drafts folder using IMAP SSL.
    Uses 100% free Google App Passwords without requiring paid Workspace or OAuth servers.
    """
    user = settings.gmail_user
    password = settings.gmail_app_password

    if not user or not password:
        logger.info("Gmail credentials not configured. Skipping Gmail IMAP draft creation.")
        return {"created": False, "reason": "GMAIL_USER or GMAIL_APP_PASSWORD not set"}

    try:
        # Build standard RFC 822 Email Message
        msg = EmailMessage()
        msg["From"] = user
        msg["To"] = recipient or ""
        msg["Subject"] = draft.get("subject", "Job Application")

        body_text = draft.get("body", "")
        if job_url:
            body_text += f"\n\n---\nTarget Job Reference: {job_url}"

        msg.set_content(body_text)

        # Connect to Gmail IMAP via SSL
        imap_server = "imap.gmail.com"
        imap = imaplib.IMAP4_SSL(imap_server, 993)
        imap.login(user, password)

        # Append draft into the standard Gmail drafts folder
        # Gmail localized or standard folder is '[Gmail]/Drafts'
        folder = '"[Gmail]/Drafts"'
        flags = r"\Draft"
        date_time = imaplib.Time2Internaldate(time.time())

        status, _ = imap.append(folder, flags, date_time, msg.as_bytes())
        imap.logout()

        if status == "OK":
            logger.info("Successfully pushed draft directly into Gmail Drafts folder.")
            return {"created": True, "folder": "[Gmail]/Drafts"}
        else:
            return {"created": False, "reason": f"IMAP append returned status: {status}"}

    except Exception as e:
        logger.error(f"Failed to create Gmail draft via IMAP: {e}")
        return {"created": False, "reason": str(e)}


# Backward compatibility
save_draft = save_local_draft
