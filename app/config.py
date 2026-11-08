from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    app_name: str = "Scout-AI"
    host: str = "127.0.0.1"
    port: int = 8000

    # LLM Provider Configuration ("gemini", "groq", or "ollama")
    llm_provider: str = "gemini"

    # 1. Google Gemini (100% Free: 15 RPM / 1M TPM via Google AI Studio)
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"

    # 2. Groq Cloud (100% Free: 30 RPM via console.groq.com)
    groq_api_key: str = ""
    groq_model: str = "llama-3.3-70b-versatile"

    # 3. Local Ollama (100% Free & Local)
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.2"

    # Storage & Resume
    database_url: str = "sqlite:///./data/assistant.db"
    resume_path: str = "./data/resume.pdf"
    csv_tracker_path: str = "./data/job_tracker.csv"

    # Job Hunting Preferences
    match_threshold: int = 35
    daily_job_limit: int = 70
    target_roles: str = "MERN Stack Developer,Backend Developer,Full Stack Developer,Software Engineer,SDE,Java Developer,Python Developer,Node.js Developer,Frontend Developer,React Developer,Angular Developer,Vue.js Developer"
    job_location_preference: str = "India + Remote"
    experience_level: str = "0-2 years"

    # Email Automation (Gmail IMAP Drafts + SMTP)
    gmail_user: str = ""
    gmail_app_password: str = ""

    # Notifications
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    discord_webhook_url: str = ""
    enable_desktop_notifications: bool = True

    # Optional RapidAPI / JSearch Key (Aggregates LinkedIn, Indeed, Glassdoor & Wellfound)
    rapidapi_key: str = ""

    # Auto-cleanup & Expiry (Hours before unreviewed jobs are auto-deleted)
    job_expiry_hours: int = 18

    # Scheduler & Timezone (Default 09:00 AM IST)
    morning_time: str = "09:00"
    timezone: str = "Asia/Kolkata"

    model_config = SettingsConfigDict(
        env_file=ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )


settings = Settings()

# Ensure required directories exist
(ROOT / "data").mkdir(exist_ok=True)
(ROOT / "data" / "drafts").mkdir(parents=True, exist_ok=True)
(ROOT / "uploads").mkdir(exist_ok=True)
