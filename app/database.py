from datetime import datetime, date
import logging
from sqlalchemy import create_engine, String, Integer, Text, Boolean, DateTime, Date, UniqueConstraint, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker
from app.config import ROOT, settings

logger = logging.getLogger("scout.database")

# Normalize database URL for SQLAlchemy 2.0 (PostgreSQL / Supabase compatibility)
raw_db_url = settings.database_url
if raw_db_url.startswith("postgres://"):
    raw_db_url = raw_db_url.replace("postgres://", "postgresql+psycopg2://", 1)
elif raw_db_url.startswith("postgresql://") and not raw_db_url.startswith("postgresql+"):
    raw_db_url = raw_db_url.replace("postgresql://", "postgresql+psycopg2://", 1)

# Handle special characters like '@' in database password
if raw_db_url.count("@") > 1 and "://" in raw_db_url:
    try:
        import urllib.parse
        prefix, remainder = raw_db_url.split("://", 1)
        auth_part, host_part = remainder.rsplit("@", 1)
        if ":" in auth_part:
            u_name, p_word = auth_part.split(":", 1)
            raw_db_url = f"{prefix}://{u_name}:{urllib.parse.quote(p_word)}@{host_part}"
    except Exception:
        pass

# Ensure Supabase connections enforce SSL
if "supabase" in raw_db_url and "sslmode" not in raw_db_url:
    delimiter = "&" if "?" in raw_db_url else "?"
    raw_db_url = f"{raw_db_url}{delimiter}sslmode=require"

if raw_db_url.startswith("sqlite"):
    engine = create_engine(raw_db_url, connect_args={"check_same_thread": False})
else:
    try:
        # Production PostgreSQL (Supabase pooler / Render) with connection recovery
        engine = create_engine(raw_db_url, pool_pre_ping=True, pool_recycle=300)
    except Exception as e:
        logger.warning("Could not initialize database engine for %s: %s. Falling back to SQLite.", raw_db_url, e)
        fallback_db = ROOT / "data" / "assistant.db"
        fallback_db.parent.mkdir(parents=True, exist_ok=True)
        engine = create_engine(f"sqlite:///{fallback_db.as_posix()}", connect_args={"check_same_thread": False})

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

class Base(DeclarativeBase):
    pass

class Job(Base):
    __tablename__ = "jobs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    source: Mapped[str] = mapped_column(String(50), default="unknown")
    title: Mapped[str] = mapped_column(String(250))
    company: Mapped[str] = mapped_column(String(250))
    location: Mapped[str] = mapped_column(String(250), default="Not specified")
    url: Mapped[str] = mapped_column(Text)
    description: Mapped[str] = mapped_column(Text, default="")
    score: Mapped[int] = mapped_column(Integer, default=0)
    date_found: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    status: Mapped[str] = mapped_column(String(40), default="New")
    recruiter_name: Mapped[str] = mapped_column(String(200), default="")
    recruiter_email: Mapped[str] = mapped_column(String(250), default="")
    contact_source: Mapped[str] = mapped_column(Text, default="")

class HabitLog(Base):
    __tablename__ = "habit_logs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[str] = mapped_column(String(64), index=True, default="default")
    habit: Mapped[str] = mapped_column(String(200))
    day: Mapped[date] = mapped_column(Date, default=date.today)
    completed: Mapped[bool] = mapped_column(Boolean, default=False)
    __table_args__ = (UniqueConstraint("session_id", "habit", "day", name="uq_session_habit_day"),)

class Task(Base):
    __tablename__ = "tasks"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[str] = mapped_column(String(64), index=True, default="default")
    title: Mapped[str] = mapped_column(String(300))
    day: Mapped[date] = mapped_column(Date, default=date.today)
    completed: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class AgentRun(Base):
    __tablename__ = "agent_runs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    agent: Mapped[str] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(30))
    summary: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class UserResume(Base):
    __tablename__ = "user_resumes"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[str] = mapped_column(String(64), index=True, default="default")
    filename: Mapped[str] = mapped_column(String(250))
    filepath: Mapped[str] = mapped_column(String(500))
    skills: Mapped[str] = mapped_column(Text, default="[]")
    experience_level: Mapped[str] = mapped_column(String(100), default="Entry Level")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class UserJobState(Base):
    """Isolates individual match scores, statuses (Interested/Applied/etc.), and notes per user."""
    __tablename__ = "user_job_states"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[str] = mapped_column(String(64), index=True, default="default")
    job_id: Mapped[int] = mapped_column(Integer, index=True)
    score: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(40), default="New")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    __table_args__ = (UniqueConstraint("session_id", "job_id", name="uq_session_job"),)

def init_db():
    global engine, SessionLocal
    try:
        Base.metadata.create_all(bind=engine)
        # Safe auto-migration for existing SQLite/Postgres schemas
        with engine.connect() as conn:
            for tbl in ["tasks", "habit_logs"]:
                try:
                    conn.execute(text(f"ALTER TABLE {tbl} ADD COLUMN session_id VARCHAR(64) DEFAULT 'default'"))
                    conn.commit()
                except Exception:
                    pass
    except Exception as e:
        if not str(engine.url).startswith("sqlite"):
            print("\n" + "=" * 80)
            print("⚠️ [SCOUT-AI DATABASE CONNECTION WARNING]")
            print(f"Failed to connect to configured database: {e}")
            if "supabase.co" in str(engine.url) and "pooler.supabase.com" not in str(engine.url):
                print("\n💡 ROOT CAUSE: You configured Supabase Direct Connection ('db.xxx.supabase.co').")
                print("   Direct Supabase connections are IPv6-only, but Render free tier is IPv4-only.")
                print("   SOLUTION: Use the Supabase Connection Pooler URI instead:")
                print("   postgresql://postgres.[ref]:[password]@aws-0-[region].pooler.supabase.com:6543/postgres?sslmode=require")
            print("\n>> Falling back to local SQLite database so the app can start and run on Render.")
            print("=" * 80 + "\n", flush=True)

            fallback_db = ROOT / "data" / "assistant.db"
            fallback_db.parent.mkdir(parents=True, exist_ok=True)
            engine = create_engine(f"sqlite:///{fallback_db.as_posix()}", connect_args={"check_same_thread": False})
            SessionLocal.configure(bind=engine)
            Base.metadata.create_all(bind=engine)
        else:
            raise e

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
