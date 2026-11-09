import csv
import hashlib
import logging
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
import zoneinfo
from pathlib import Path
from typing import Dict, List, Optional, Set, Any
from urllib.parse import urlparse

import requests
from sqlalchemy.orm import Session

from app.config import ROOT, settings
from app.database import Job
from app.agents.contact_finder import find_public_contacts
from app.services.resume import extract_resume_text

logger = logging.getLogger(__name__)

# Comprehensive technical skills database
TECH_TAXONOMY = {
    # Core Languages
    "python", "javascript", "typescript", "java", "c++", "c#", "go", "golang",
    "rust", "ruby", "php", "swift", "kotlin", "sql", "html", "css", "bash",
    # Frameworks & Libraries
    "react", "react.js", "next.js", "vue", "vue.js", "angular", "node.js",
    "express", "express.js", "fastapi", "django", "flask", "spring boot",
    ".net", "asp.net", "tailwind", "bootstrap", "graphql", "rest api", "redux",
    # Databases & Caching
    "mongodb", "postgresql", "postgres", "mysql", "redis", "firebase",
    "supabase", "sqlite", "elasticsearch", "cassandra",
    # Cloud & DevOps
    "docker", "kubernetes", "aws", "azure", "gcp", "ci/cd", "git", "github",
    "linux", "nginx", "terraform",
    # Architecture & Concepts
    "microservices", "oop", "data structures", "algorithms", "system design",
    "machine learning", "deep learning", "ai", "llm"
}

# Non-tech / Non-engineering exclusions
NON_TECH_ROLE_EXCLUSIONS = {
    "account executive", "sales", "counsel", "legal", "benefits specialist",
    "recruiter", "talent partner", "finance", "marketing", "payroll", "hr ",
    "customer support", "bdr", "sdr", "copywriter", "content writer",
    "business partner", "office manager", "operations manager", "strategie",
    "strategy", "consolidation", "onderzoek", "advies", "arbeidsmarkt",
    "human resources", "recruitment", "procurement", "supply chain",
    "accounting", "auditor", "scriptwriter", "expansion", "officer", "privacy",
    "compliance", "paralegal", "paie", "rh", "apporteur", "servicetechniker"
}

# Academic and non-English / European language markers
FOREIGN_LANGUAGE_OR_ACADEMIC_EXCLUSIONS = {
    "post-doc", "postdoc", "post doctoral", "post-doctoral", "post doctorant",
    "post-doctorant", "phd", "ph.d", "doctorat", "doctorant", "cdd", "alternance",
    "stagiair", "stage ", "stage-", "meewerkstage", "thèse", "(m/w/d)", "(f/m/d)", "werkstudent"
}

# Disallowed foreign countries/regions when India + Remote is required
FOREIGN_EXCLUSIONS = {
    "usa", "united states", "us only", "u.s.", "u.s.a", "canada", "uk",
    "united kingdom", "germany", "deutschland", "berlin", "munich", "hamburg",
    "frankfurt", "kassel", "dach", "france", "paris", "netherlands", "amsterdam",
    "poland", "australia", "sydney", "melbourne", "japan", "tokyo", "singapore",
    "brazil", "latin america", "latam", "emea", "noram", "apac", "africa",
    "southern europe", "eastern europe", "switzerland", "austria"
}

INDIAN_LOCATIONS = {
    "india", "bangalore", "bengaluru", "hyderabad", "pune", "mumbai",
    "delhi", "noida", "gurgaon", "gurugram", "chennai", "kolkata",
    "ahmedabad", "chandigarh", "mohali", "kerala", "kochi", "jaipur", "indore",
    "vapi", "malappuram", "work from home"
}

# Standard Role Categories & Labels
ROLE_LABELS = {
    "intern": "🎓 Intern / Fresher",
    "fullstack": "⚡ Full Stack",
    "frontend": "🎨 Frontend",
    "backend": "⚙️ Backend",
    "aiml": "🤖 AI / ML",
    "web": "🌐 Web Dev",
    "mobile": "📱 Mobile Dev",
    "devops": "☁️ DevOps",
    "software": "💻 Software Eng"
}


def get_job_roles(title: str, desc: str = "") -> List[str]:
    """
    Returns ALL matching role tags for a job so filters work accurately.
    E.g. 'Software Engineer Intern' -> ['intern', 'software']
         'Full Stack Software Engineer Intern' -> ['fullstack', 'intern', 'software']
         'Frontend Developer Intern' -> ['frontend', 'intern', 'software']
    """
    t = (title or "").lower()
    d = (desc or "").lower()
    roles = set()

    # Intern / Fresher
    if any(k in t for k in ["intern", "internship", "trainee", "fresher", "co-op", "apprentice"]) or "intern" in d:
        roles.add("intern")

    # Fullstack
    if any(k in t for k in ["full stack", "fullstack", "mern", "mean"]) or "full stack" in d or "fullstack" in d:
        roles.add("fullstack")

    # Frontend
    if any(k in t for k in ["frontend", "front end", "front-end", "react", "vue", "angular", "ui developer", "javascript developer"]) or "frontend" in d:
        roles.add("frontend")

    # Backend
    if any(k in t for k in ["backend", "back end", "back-end", "node", "django", "fastapi", "flask", "golang", "java developer", "python developer"]) or "backend" in d:
        roles.add("backend")

    # AI / ML
    if any(k in t for k in ["ai", "ml", "machine learning", "deep learning", "nlp", "llm", "data scientist", "data engineer"]) or "machine learning" in d:
        roles.add("aiml")

    # Web Dev
    if any(k in t for k in ["web developer", "web development", "wordpress", "php"]) or "web developer" in d:
        roles.add("web")

    # Mobile Dev
    if any(k in t for k in ["mobile", "android", "ios", "flutter", "react native", "swift", "kotlin"]) or "mobile developer" in d:
        roles.add("mobile")

    # DevOps
    if any(k in t for k in ["devops", "cloud", "aws", "infrastructure", "sre", "platform"]) or "devops" in d:
        roles.add("devops")

    # Software Engineering (umbrella for developer, engineer, SDE, software, coder)
    if any(k in t for k in ["software", "engineer", "developer", "sde", "programmer", "coding"]) or any(r in roles for r in ["fullstack", "frontend", "backend", "web", "mobile", "devops", "aiml"]):
        roles.add("software")

    if not roles:
        roles.add("software")

    return sorted(list(roles))


def classify_role(title: str, desc: str = "") -> str:
    """Classifies a job into a primary standard role category for badge display."""
    t = (title or "").lower()
    d = (desc or "").lower()

    if any(k in t for k in ["intern", "internship", "trainee", "fresher", "co-op", "apprentice"]):
        return "intern"
    if any(k in t for k in ["full stack", "fullstack", "mern", "mean"]):
        return "fullstack"
    if any(k in t for k in ["frontend", "front end", "front-end", "react", "vue", "angular", "ui developer", "javascript developer"]):
        return "frontend"
    if any(k in t for k in ["backend", "back end", "back-end", "node", "django", "fastapi", "flask", "golang", "java developer", "python developer"]):
        return "backend"
    if any(k in t for k in ["ai", "ml", "machine learning", "deep learning", "nlp", "llm", "data scientist", "data engineer"]):
        return "aiml"
    if any(k in t for k in ["web developer", "web development", "wordpress", "php"]):
        return "web"
    if any(k in t for k in ["mobile", "android", "ios", "flutter", "react native", "swift", "kotlin"]):
        return "mobile"
    if any(k in t for k in ["devops", "cloud", "aws", "infrastructure", "sre", "platform"]):
        return "devops"

    if "intern" in d:
        return "intern"
    if "full stack" in d or "fullstack" in d:
        return "fullstack"
    if "backend" in d:
        return "backend"
    if "frontend" in d:
        return "frontend"

    return "software"

# Roles strictly excluded for 3 months internship / entry level candidates
SENIOR_ROLE_EXCLUSIONS = {
    "senior", "sr.", "sr ", "lead", "principal", "principle", "staff", "architect",
    "director", "head of", "head ", "vp", "vice president", "manager", "chief",
    "specialist", "expert", "team lead", "tech lead", "engineering manager",
    "partner engineer"
}

SOURCES = {
    "linkedin": {
        "type": "linkedin",
        "queries": [
            ("Software Engineer Intern", "India"),
            ("Full Stack Developer Intern", "India"),
            ("Frontend Developer Intern", "India"),
            ("Backend Developer Intern", "India"),
            ("MERN Stack Developer", "India"),
            ("React Developer Intern", "India"),
            ("Node.js Developer", "India"),
            ("Software Engineer", "India")
        ]
    },
    "jsearch": {
        "type": "jsearch"
    },
    "himalayas": {
        "type": "himalayas"
    },
    "remotive": {
        "type": "json",
        "url": "https://remotive.com/api/remote-jobs",
        "params": {"category": "software-dev", "limit": 50},
        "data_key": "jobs",
        "title_key": "title",
        "company_key": "company",
        "location_key": "candidate_required_location",
        "url_key": "url",
        "description_key": "description",
        "remote_key": "is_remote",
    },
    "arbeitnow": {
        "type": "json",
        "url": "https://www.arbeitnow.com/api/job-board-api",
        "data_key": "data",
        "title_key": "title",
        "company_key": "company_name",
        "location_key": "candidate_required_location",
        "url_key": "url",
        "description_key": "description",
        "remote_key": "remote",
    },
    "jobicy": {
        "type": "json",
        "url": "https://jobicy.com/api/v2/remote-jobs?count=50&industry=engineering",
        "data_key": "jobs",
        "title_key": "jobTitle",
        "company_key": "companyName",
        "location_key": "jobGeo",
        "url_key": "url",
        "description_key": "jobDescription",
        "remote_key": "jobType",
    },
    "weworkremotely": {
        "type": "rss",
        "url": "https://weworkremotely.com/categories/remote-programming-jobs.rss",
    }
}


def get_now_ist() -> datetime:
    """Returns current date and time in Indian Standard Time (IST, UTC+05:30)."""
    try:
        ist_zone = zoneinfo.ZoneInfo("Asia/Kolkata")
        return datetime.now(timezone.utc).astimezone(ist_zone).replace(tzinfo=None)
    except Exception:
        return datetime.now(timezone.utc).astimezone(timezone(timedelta(hours=5, minutes=30))).replace(tzinfo=None)


def calculate_job_expiry(dt: Optional[datetime], max_age_hours: int = 18) -> dict:
    """
    Computes time remaining before 18-hour auto-deletion, formatted in IST.
    """
    total_allowed = max_age_hours * 3600
    if not dt:
        return {
            "ist_str": "Recent (IST)",
            "expires_in_str": f"{max_age_hours}h 0m",
            "is_expiring_soon": False,
            "remaining_seconds": total_allowed
        }

    now_ist = get_now_ist()
    age_seconds = (now_ist - dt).total_seconds()
    remaining_seconds = max(0, total_allowed - age_seconds)

    hours = int(remaining_seconds // 3600)
    mins = int((remaining_seconds % 3600) // 60)

    is_expiring_soon = remaining_seconds <= (4 * 3600)
    expires_in_str = f"{hours}h {mins}m" if remaining_seconds > 0 else "Expiring now"
    ist_str = dt.strftime("%d %b %Y, %I:%M %p IST")

    return {
        "ist_str": ist_str,
        "expires_in_str": expires_in_str,
        "is_expiring_soon": is_expiring_soon,
        "remaining_seconds": remaining_seconds
    }


def cleanup_expired_jobs(db: Session, max_age_hours: int = 18, preserve_saved: bool = True) -> int:
    """
    Auto-deletes unreviewed 'New' jobs that were found more than `max_age_hours` (18 hours) ago.
    Keeps jobs marked as Interested, Applied, or Interview by the candidate.
    """
    now_ist = get_now_ist()
    cutoff = now_ist - timedelta(hours=max_age_hours)

    query = db.query(Job).filter(Job.date_found < cutoff)
    if preserve_saved:
        query = query.filter(Job.status == "New")

    expired = query.all()
    count = len(expired)
    if count > 0:
        for j in expired:
            db.delete(j)
        db.commit()
        logger.info(f"Auto-deleted {count} expired jobs older than {max_age_hours} hours (IST).")
    return count


def get_location_category(location: str, remote: bool = False) -> str:
    """
    Returns location classification: 'india', 'remote', or 'out_of_india'.
    """
    loc_low = (location or "").lower().strip()
    if any(ind in loc_low for ind in INDIAN_LOCATIONS) or "india" in loc_low:
        return "india"

    # Check if restricted to foreign country
    for f in FOREIGN_EXCLUSIONS:
        if re.search(rf"\b{re.escape(f)}\b", loc_low):
            return "out_of_india"

    if remote or any(w in loc_low for w in ["remote", "anywhere", "worldwide", "global", "work from anywhere", "all locations"]):
        return "remote"

    return "out_of_india"


def is_location_eligible(location: str, remote: bool = False, allow_out_of_india: bool = False) -> bool:
    """
    Check if a job matches India or Global Remote preference.
    """
    cat = get_location_category(location, remote)
    if cat in {"india", "remote"}:
        return True
    return allow_out_of_india


def is_experience_eligible(title: str, desc: str, user_exp_months: int = 0) -> bool:
    """
    Dynamically filters tech jobs based on candidate's parsed resume experience:
    - If resume has no experience or <= 2 years:
      Strictly filters for 0-2 years (intern, fresher, junior). Reject all 3+, 4+, 5+, etc.
      and all senior/lead/architect roles.
    - If resume has 2+ years of experience (e.g. 3, 4, 5+ years):
      Dynamically unlocks matching mid-level and senior opportunities calibrated to their
      actual career level (up to candidate_years + 1.5).
    """
    title_low = (title or "").lower().strip()
    desc_low = (desc or "").lower().strip()
    combo = f"{title_low} {desc_low}"

    candidate_years = round((user_exp_months or 0) / 12.0, 1)

    # 1. Reject non-tech roles
    for non_tech in NON_TECH_ROLE_EXCLUSIONS:
        if re.search(rf"\b{re.escape(non_tech.strip())}\b", title_low):
            return False

    # 2. Extract job required experience range and minimum
    low_yr, high_yr = None, None
    m_range = re.search(r"\b([0-9]|1\d)\s*(?:-|–|to)\s*([0-9]|1\d)\s*(?:years?|yrs?|yr)\b", combo)
    if m_range:
        low_yr = int(m_range.group(1))
        high_yr = int(m_range.group(2))

    min_yr = None
    if low_yr is not None:
        min_yr = low_yr
    else:
        for pat in [
            r"\b([1-9]|1\d)\s*\+\s*(?:years?|yrs?|yr)\b",
            r"\b(?:minimum|min\.?|at least)\s+(?:of\s+)?([1-9]|1\d)\+?\s*(?:years?|yrs?|yr)\b",
            r"\b(?:experience|exp)\s*(?:required|needed|level)?\s*[:=-]\s*([0-9]|1\d)",
            r"\b(?:must have|requires?|seeking|needs?)\s+(?:at least\s+|a minimum of\s+)?([1-9]|1\d)\+?\s*(?:years?|yrs?|yr)\b",
            r"\b([1-9]|1\d)\+?\s*(?:years?|yrs?|yr)\b(?:\s+(?:of\s+)?(?:relevant|professional|hands[- ]on|industry|software|development|work|prior|practical))?\s+experience\b",
            r"\b([1-9]|1\d)\+?\s*(?:years?|yrs?|yr)\b\s+(?:in|with|working|building|developing|designing|architecting)\b",
            r"\(\s*([1-9]|1\d)\+?\s*(?:-|–|to)?\s*\d*\s*(?:years?|yrs?|yr)\s*\)"
        ]:
            m = re.search(pat, combo if pat != r"\(\s*([1-9]|1\d)\+?\s*(?:-|–|to)?\s*\d*\s*(?:years?|yrs?|yr)\s*\)" else title_low)
            if m:
                min_yr = int(m.group(1))
                break

    # 3. Check role seniority
    is_senior_title = bool(re.search(r"\b(?:sr\.?|senior)\b", title_low))
    is_leadership = bool(re.search(r"\b(?:lead|principal|staff|architect|director|vp|vice\s+president|head\s+of|manager|chief|partner\s+engineer)\b", title_low))

    # CASE A: Candidate has 0 - 2 years experience (or no experience in resume)
    if candidate_years <= 2.0:
        # Strictly reject senior or leadership titles
        if is_senior_title or is_leadership:
            return False
        # Reject explicit senior declaration in description
        if re.search(r"\b(?:looking for|seeking|hiring|we need)\s+(?:an?\s+)?(?:senior|lead|principal|staff|architect)\b", desc_low):
            return False
        if re.search(r"\b(?:role|position|job title|level)\s*[:=-]\s*(?:senior|lead|principal|staff|architect)\b", desc_low):
            return False

        # Reject academic / postdoc / foreign language markers in title
        for academic in FOREIGN_LANGUAGE_OR_ACADEMIC_EXCLUSIONS:
            if academic.strip() in title_low:
                return False

        # Reject if job asks for >= 3 years min, or 2-5+ years range
        if low_yr is not None and high_yr is not None:
            if low_yr >= 3 or (low_yr >= 2 and high_yr >= 4):
                return False
        elif min_yr is not None and min_yr >= 3:
            return False

    # CASE B: Candidate has 2+ years experience (e.g. 3, 4, 5+ years)
    else:
        max_allowed = max(candidate_years + 1.5, 3.0)
        # If job demands more experience than candidate has + 1.5 years
        if min_yr is not None and min_yr > max_allowed:
            return False
        if low_yr is not None and low_yr > max_allowed:
            return False

        # Only allow leadership roles if candidate has at least 5 years
        if is_leadership and candidate_years < 5.0:
            return False
        # Only allow senior titles if candidate has at least 3.0 years
        if is_senior_title and candidate_years < 3.0:
            return False

    # 4. Tech role pattern check
    tech_patterns = [
        r"\bdeveloper\b", r"\bsoftware\b", r"\bengineer\b", r"\bfull\s*stack\b",
        r"\bbackend\b", r"\bfrontend\b", r"\bmern\b", r"\breact\b", r"\bnode\b",
        r"\bpython\b", r"\bjava\b", r"\bintern\b", r"\binternship\b", r"\bjunior\b",
        r"\bassociate\b", r"\bsde\b", r"\bweb\b", r"\bai\b", r"\bcloud\b",
        r"\bprogrammer\b", r"\bprogramming\b"
    ]
    return any(re.search(p, title_low) for p in tech_patterns)


def parse_resume_profile(resume_text: str) -> Dict[str, Any]:
    """
    Extract technical skills, estimated experience, and role hints from resume text
    using keyword taxonomy and temporal date range heuristics.
    """
    lower = resume_text.lower()
    extracted_skills = {skill for skill in TECH_TAXONOMY if re.search(rf"\b{re.escape(skill)}\b", lower)}

    # 1. Look for explicit experience mentions
    month_match = re.search(r"(\d+)\s*(?:month|months)\s*(?:of)?\s*(?:internship|experience)", lower)
    exp_prefix_match = re.search(r"(?:total\s+)?(?:experience|exp)\s*[:=-]?\s*(\d+(?:\.\d+)?)\+?\s*(?:years?|yrs?)", lower)
    exp_phrase_match = re.search(r"(\d+(?:\.\d+)?)\s*\+?\s*(?:year|years|yrs)\s*(?:of)?\s*(?:relevant\s+|professional\s+|software\s+|hands[- ]on\s+)?(?:experience|exp)", lower)
    exp_context_match = re.search(r"(\d+(?:\.\d+)?)\s*\+?\s*(?:year|years|yrs)\s+(?:in|as a|working with)\b", lower)

    estimated_months = 0
    if exp_prefix_match:
        estimated_months = int(float(exp_prefix_match.group(1)) * 12)
    elif exp_phrase_match:
        estimated_months = int(float(exp_phrase_match.group(1)) * 12)
    elif exp_context_match:
        estimated_months = int(float(exp_context_match.group(1)) * 12)
    elif month_match:
        estimated_months = int(month_match.group(1))

    # 2. Date ranges heuristic: e.g., "2021 - 2024", "2022 - present"
    current_year = datetime.now().year
    date_ranges = re.findall(r"\b(201\d|202\d)\s*(?:-|–|to)\s*(201\d|202\d|present|current)\b", lower)
    if date_ranges and estimated_months == 0:
        total_range_years = 0
        for start_y, end_y in date_ranges:
            start_val = int(start_y)
            end_val = current_year if end_y in ["present", "current"] else int(end_y)
            diff = max(0, min(end_val - start_val, 15))
            total_range_years = max(total_range_years, diff)
        is_student = bool(re.search(r"\b(student|b\.?tech|undergraduate|bachelor|pursuing)\b", lower))
        if not is_student and total_range_years >= 2:
            estimated_months = max(estimated_months, total_range_years * 12)

    # 3. Determine calibrated experience level
    is_intern = bool(re.search(r"\b(intern|internship|trainee|apprentice|student|b\.?tech|undergraduate)\b", lower))
    is_senior = bool(re.search(r"\b(senior|lead|principal|architect|staff engineer)\b", lower))

    if is_senior or estimated_months >= 48:
        level = "4+ Years (Senior Engineer)"
    elif estimated_months >= 24:
        level = "2-4 Years (Mid-Level Developer)"
    elif estimated_months >= 12:
        level = "1-2 Years (Associate Engineer)"
    elif is_intern or estimated_months > 0:
        months_display = f"{estimated_months} Months" if estimated_months > 0 else "Entry Level"
        level = f"{months_display} (Intern / Fresher)"
    else:
        level = "Entry Level (0-2 Years)"

    return {
        "skills": extracted_skills,
        "estimated_months": estimated_months,
        "experience_level": level
    }


def _fetch_rss_jobs(url: str) -> List[dict]:
    """Fetch jobs from public RSS feeds (e.g. WeWorkRemotely)."""
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) ScoutAI/2.0"}
    res = requests.get(url, headers=headers, timeout=25)
    res.raise_for_status()

    root = ET.fromstring(res.content)
    items = []
    for item in root.findall(".//item"):
        title_raw = item.findtext("title", "")
        if ":" in title_raw:
            company, title = title_raw.split(":", 1)
        else:
            company, title = "Unknown", title_raw

        link = item.findtext("link", "")
        desc = item.findtext("description", "")

        items.append({
            "title": title.strip(),
            "company": company.strip(),
            "url": link.strip(),
            "description": desc.strip(),
            "location": "Remote",
            "remote": True
        })
    return items


def fetch_linkedin_jobs(queries: Optional[List[tuple]] = None, limit_per_query: int = 12, max_total: int = 60) -> List[dict]:
    """
    Scrapes live LinkedIn guest job postings across India without requiring any API key.
    Runs multiple high-demand tech queries for 0-2 year / intern / entry-level roles.
    """
    from bs4 import BeautifulSoup
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9",
    }
    if not queries:
        queries = [
            ("Software Engineer Intern", "India"),
            ("Full Stack Developer Intern", "India"),
            ("Frontend Developer Intern", "India"),
            ("Backend Developer Intern", "India"),
            ("MERN Stack Developer", "India"),
            ("React Developer Intern", "India"),
            ("Node.js Developer", "India"),
            ("Software Engineer", "India")
        ]

    items = []
    seen = set()

    for keywords, location in queries:
        if len(items) >= max_total:
            break
        url = f"https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search?keywords={requests.utils.quote(keywords)}&location={requests.utils.quote(location)}"
        try:
            r = requests.get(url, headers=headers, timeout=15)
            if r.status_code != 200:
                continue
            soup = BeautifulSoup(r.text, "html.parser")
            q_count = 0
            for card in soup.select("li"):
                if q_count >= limit_per_query or len(items) >= max_total:
                    break
                title_el = card.select_one(".base-search-card__title")
                comp_el = card.select_one(".base-search-card__subtitle")
                loc_el = card.select_one(".job-search-card__location")
                link_el = card.select_one("a.base-card__full-link") or card.select_one("a")

                if not title_el or not comp_el or not link_el:
                    continue

                title = title_el.get_text(strip=True)
                company = comp_el.get_text(strip=True)
                loc = loc_el.get_text(strip=True) if loc_el else "India"
                href = link_el.get("href", "").split("?")[0]

                if not href or href in seen:
                    continue
                seen.add(href)
                q_count += 1

                clean_loc = f"{loc}, India" if "india" not in loc.lower() else loc
                source_id = hashlib.sha256(f"linkedin:{href}".encode()).hexdigest()
                desc = f"{title} at {company} in {clean_loc}. Direct LinkedIn tech posting. Apply on LinkedIn: {href}"

                items.append({
                    "source_id": source_id,
                    "source": "linkedin",
                    "title": title,
                    "company": company,
                    "location": clean_loc,
                    "url": href,
                    "description": desc,
                    "remote": "remote" in loc.lower()
                })
            time.sleep(0.3)
        except Exception as e:
            logger.warning(f"LinkedIn fetch failed for {keywords}: {e}")

    return items


def fetch_himalayas_jobs(limit: int = 30) -> List[dict]:
    """
    Fetches real-time startup tech jobs from Himalayas (modern startup job board like Wellfound).
    Completely free public JSON API.
    """
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) ScoutAI/2.0"}
    url = "https://himalayas.app/jobs/api?limit=50"
    items = []
    seen = set()

    try:
        res = requests.get(url, headers=headers, timeout=20)
        if res.status_code != 200:
            return []
        data = res.json()
        jobs = data.get("jobs", [])
        for j in jobs:
            if len(items) >= limit:
                break
            title = j.get("title", "")
            company = j.get("companyName", "")
            url_link = j.get("applicationLink") or f"https://himalayas.app/companies/{j.get('companySlug')}/jobs/{j.get('slug')}"
            loc = j.get("location", "Remote")

            if not title or not company or not url_link or url_link in seen:
                continue
            seen.add(url_link)

            desc = re.sub(r"<[^>]+>", " ", j.get("description", ""))
            desc = re.sub(r"\s+", " ", desc).strip()[:4000]

            source_id = hashlib.sha256(f"himalayas:{url_link}".encode()).hexdigest()
            items.append({
                "source_id": source_id,
                "source": "himalayas",
                "title": title,
                "company": company,
                "location": loc or "Worldwide Remote",
                "url": url_link,
                "description": desc,
                "remote": True
            })
    except Exception as e:
        logger.warning(f"Himalayas fetch failed: {e}")

    return items


def fetch_jsearch_jobs(api_key: str, queries: Optional[List[str]] = None, limit: int = 35) -> List[dict]:
    """
    Fetches real-time tech jobs from JSearch RapidAPI v2 (aggregating Wellfound, LinkedIn, Indeed, Glassdoor).
    Auto-detects Wellfound and LinkedIn direct source badges.
    """
    if not api_key:
        return []

    url = "https://jsearch.p.rapidapi.com/search-v2"
    headers = {
        "X-RapidAPI-Key": api_key,
        "X-RapidAPI-Host": "jsearch.p.rapidapi.com"
    }
    if not queries:
        queries = [
            "Software Engineer Intern India",
            "MERN Stack Developer India",
            "Full Stack Developer India",
            "Frontend Developer Intern India",
            "Backend Developer Intern India",
            "Wellfound Developer India"
        ]

    items = []
    seen = set()

    for q in queries:
        if len(items) >= limit:
            break
        params = {"query": q, "page": "1", "num_pages": "1"}
        try:
            res = requests.get(url, headers=headers, params=params, timeout=30)
            if res.status_code != 200:
                logger.warning(f"JSearch API returned {res.status_code} for query '{q}': {res.text[:120]}")
                if res.status_code in (401, 403, 404):
                    break
                continue

            data = res.json()
            raw_data = data.get("data", {})
            if isinstance(raw_data, dict):
                job_list = raw_data.get("jobs", [])
            elif isinstance(raw_data, list):
                job_list = raw_data
            else:
                job_list = []

            for j in job_list:
                title = j.get("job_title", "")
                company = j.get("employer_name", "")
                url_link = j.get("job_apply_link") or j.get("job_google_link", "")
                city = j.get("job_city") or ""
                state = j.get("job_state") or ""
                country = j.get("job_country") or "India"
                loc = f"{city}, {state}, {country}".strip(", ")
                if not loc or loc == ",":
                    loc = "India"
                desc = (j.get("job_description") or "")[:4000]

                if not title or not company or not url_link or url_link in seen:
                    continue
                seen.add(url_link)

                # Identify if origin is Wellfound, LinkedIn, or general JSearch
                publisher = (j.get("job_publisher") or "").lower()
                apply_opts = j.get("apply_options", [])
                pub_all = publisher + " " + " ".join((opt.get("publisher", "") + " " + opt.get("apply_link", "")).lower() for opt in apply_opts)

                if "wellfound" in pub_all or "angellist" in pub_all:
                    source_label = "wellfound"
                elif "linkedin" in pub_all:
                    source_label = "linkedin"
                else:
                    source_label = "jsearch"

                source_id = hashlib.sha256(f"{source_label}:{url_link}".encode()).hexdigest()
                items.append({
                    "source_id": source_id,
                    "source": source_label,
                    "title": title,
                    "company": company,
                    "location": loc or "India",
                    "url": url_link,
                    "description": desc,
                    "remote": bool(j.get("job_is_remote", False))
                })
        except Exception as e:
            logger.warning(f"JSearch API error for '{q}': {e}")
            break

    return items


def _fetch_source(name: str, config: dict) -> List[dict]:
    """Fetch jobs from a specific source."""
    if config.get("type") == "linkedin":
        return fetch_linkedin_jobs(config.get("queries"))
    if config.get("type") == "jsearch":
        return fetch_jsearch_jobs(settings.rapidapi_key)
    if config.get("type") == "himalayas":
        return fetch_himalayas_jobs()
    if config.get("type") == "rss":
        return _fetch_rss_jobs(config["url"])

    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) ScoutAI/2.0"}
    params = config.get("params", {})
    res = requests.get(config["url"], headers=headers, params=params, timeout=25)
    res.raise_for_status()
    data = res.json()
    return data.get(config.get("data_key", "jobs"), [])


def _normalize(raw: dict, source_name: str, config: dict) -> Optional[dict]:
    """Normalize raw job payload into standardized schema."""
    if config.get("type") in {"linkedin", "jsearch", "himalayas"} or raw.get("source") in {"linkedin", "wellfound", "jsearch", "himalayas"}:
        return raw

    if config.get("type") == "rss":
        title = raw.get("title", "").strip()
        company = raw.get("company", "").strip()
        url = raw.get("url", "").strip()
        description = raw.get("description", "")
        location = raw.get("location", "Remote")
        remote = True
    else:
        title = (raw.get(config["title_key"]) or "").strip()
        company = (raw.get(config["company_key"]) or "").strip()
        url = (raw.get(config["url_key"]) or "").strip()
        description = raw.get(config["description_key"]) or ""
        location = (raw.get(config["location_key"]) or "Remote").strip()
        remote = bool(raw.get(config.get("remote_key") or "remote", False))

    if not title or not company or not url:
        return None

    clean_desc = re.sub(r"<[^>]+>", " ", description)
    clean_desc = re.sub(r"\s+", " ", clean_desc).strip()[:10000]

    source_id = hashlib.sha256(f"{source_name}:{url}".encode()).hexdigest()

    return {
        "source_id": source_id,
        "source": source_name,
        "title": title,
        "company": company,
        "location": location or "Remote",
        "url": url,
        "description": clean_desc,
        "remote": remote
    }


def score_job(
    resume_skills: Set[str],
    job_desc: str,
    job_title: str,
    job_location: str,
    remote: bool = False
) -> int:
    """
    Score job match (0-100) based on skills, target roles, and location.
    Puts India and Remote on top with highest score multipliers.
    """
    if not resume_skills:
        return 0

    desc_lower = job_desc.lower()
    title_lower = job_title.lower()

    # 1. Technical skill overlap (50% weight)
    matched_skills = {s for s in resume_skills if s in desc_lower or s in title_lower}
    skill_ratio = min(1.0, len(matched_skills) / max(min(len(resume_skills), 7), 1))

    # 2. Role Title Relevance (30% weight)
    role_score = 0.4
    target_terms = [t.strip().lower() for t in settings.target_roles.split(",") if t.strip()]
    if any(term in title_lower for term in target_terms):
        role_score = 1.0
    elif any(term in desc_lower for term in target_terms):
        role_score = 0.7

    # Intern/Junior bonus for 3-months intern candidate
    if any(k in title_lower for k in ["intern", "internship", "junior", "associate", "fresher", "trainee"]):
        role_score = min(1.0, role_score + 0.2)

    # 3. Location Relevance (20% weight) - India and Remote on top
    loc_cat = get_location_category(job_location, remote)
    if loc_cat == "india":
        loc_score = 1.0
    elif loc_cat == "remote":
        loc_score = 0.95
    else:
        loc_score = 0.3

    total = (skill_ratio * 0.50) + (role_score * 0.30) + (loc_score * 0.20)
    return round(total * 100)


def export_jobs_to_csv(jobs: List[Job], csv_path: Optional[str] = None):
    """
    Save tracked leads to CSV ordered with India & Remote on top.
    """
    target = Path(csv_path or settings.csv_tracker_path)
    target.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = [
        "Job Title", "Company", "Location", "Job URL",
        "Recruiter Name", "Recruiter Email", "Match Score %",
        "Date Found", "Status"
    ]

    with open(target, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for job in jobs:
            writer.writerow({
                "Job Title": job.title,
                "Company": job.company,
                "Location": job.location,
                "Job URL": job.url,
                "Recruiter Name": job.recruiter_name or "N/A",
                "Recruiter Email": job.recruiter_email or "N/A",
                "Match Score %": job.score,
                "Date Found": job.date_found.strftime("%Y-%m-%d %H:%M") if job.date_found else "",
                "Status": job.status
            })


def cleanup_ineligible_jobs(db: Session, user_exp_months: int = 3) -> int:
    """
    Prunes jobs that are not software engineering, are senior/manager roles,
    or require 3+ years of experience (or mid-senior ranges).
    Also removes corresponding UserJobState records.
    """
    from app.database import UserJobState
    all_jobs = db.query(Job).all()
    removed = 0
    kept_jobs = []

    for j in all_jobs:
        exp_ok = is_experience_eligible(j.title, j.description, user_exp_months)

        if not exp_ok:
            try:
                db.query(UserJobState).filter_by(job_id=j.id).delete()
            except Exception:
                pass
            db.delete(j)
            removed += 1
        else:
            kept_jobs.append(j)

    db.commit()
    if kept_jobs:
        try:
            export_jobs_to_csv(kept_jobs)
        except Exception as e:
            logger.warning(f"Failed to export jobs to CSV: {e}")
    if removed > 0:
        logger.info(f"Cleaned up {removed} ineligible senior/experienced jobs.")
    return removed


def get_calibrated_linkedin_queries(exp_months: int = 0) -> List[tuple]:
    """
    Returns search queries calibrated to candidate's parsed resume experience.
    If no experience / <= 2 yrs, focuses on 0-2 yr / intern / junior roles.
    If 2+ years, unlocks mid-level and senior roles.
    """
    years = (exp_months or 0) / 12.0
    if years >= 4.0:
        return [
            ("Senior Full Stack Developer", "India"),
            ("Senior Software Engineer", "India"),
            ("Senior Frontend Developer", "India"),
            ("Senior Backend Developer", "India"),
            ("Tech Lead", "India"),
            ("MERN Stack Developer", "India")
        ]
    elif years >= 2.0:
        return [
            ("Full Stack Developer", "India"),
            ("Software Engineer", "India"),
            ("Frontend Developer", "India"),
            ("Backend Developer", "India"),
            ("Node.js Developer", "India"),
            ("React Developer", "India"),
            ("MERN Stack Developer", "India")
        ]
    else:
        return [
            ("Software Engineer Intern", "India"),
            ("Full Stack Developer Intern", "India"),
            ("Frontend Developer Intern", "India"),
            ("Backend Developer Intern", "India"),
            ("MERN Stack Developer", "India"),
            ("React Developer Intern", "India"),
            ("Junior Software Engineer", "India"),
            ("Software Engineer", "India")
        ]


def hunt_jobs(
    db: Session,
    resume_path: Optional[str] = None,
    limit: Optional[int] = None,
    search_query: Optional[str] = None,
    session_id: str = "default"
) -> dict:
    """
    Hunt for jobs prioritizing India & Remote roles calibrated to candidate's resume experience.
    """
    from app.database import UserJobState

    path = resume_path
    if not path or not Path(path).exists():
        for candidate in [
            ROOT / "app" / "Resume" / "CV-Durgesh.pdf",
            Path(settings.resume_path),
            ROOT / "data" / "resume.pdf"
        ]:
            if candidate.exists():
                path = str(candidate)
                break

    max_jobs = limit or settings.daily_job_limit
    threshold = settings.match_threshold

    # Clean up expired jobs (>18h IST)
    cleanup_expired_jobs(db, max_age_hours=settings.job_expiry_hours)

    resume_skills = {"python", "javascript", "react", "node.js", "sql", "git", "fastapi", "html", "css"}
    exp_months = 0

    if path and Path(path).exists():
        try:
            resume_text = extract_resume_text(path)
            profile = parse_resume_profile(resume_text)
            if profile.get("skills"):
                resume_skills = profile["skills"]
            exp_months = profile.get("estimated_months", 0)
        except Exception as e:
            logger.warning(f"Failed to parse resume at {path}: {e}. Using standard tech profile.")

    cleanup_ineligible_jobs(db, exp_months)

    added_jobs = []
    errors = []
    skipped_no_match = 0
    calibrated_queries = get_calibrated_linkedin_queries(exp_months)

    for source_name, config in SOURCES.items():
        if len(added_jobs) >= max_jobs:
            break

        try:
            if source_name == "linkedin":
                raw_listings = fetch_linkedin_jobs(calibrated_queries)
            else:
                raw_listings = _fetch_source(source_name, config)

            for raw in raw_listings:
                if len(added_jobs) >= max_jobs:
                    break

                item = _normalize(raw, source_name, config)
                if not item:
                    continue

                # 1. Experience & Tech Role Check (calibrated to candidate level)
                if not is_experience_eligible(item["title"], item["description"], exp_months):
                    skipped_no_match += 1
                    continue

                # 2. Location Check (India + Worldwide Remote only)
                if not is_location_eligible(item["location"], item.get("remote", False)):
                    skipped_no_match += 1
                    continue

                # Deduplication check
                existing = db.query(Job).filter_by(source_id=item["source_id"]).first()
                if existing:
                    # Associate existing job with this session if not already associated
                    if session_id:
                        user_state = db.query(UserJobState).filter_by(session_id=session_id, job_id=existing.id).first()
                        if not user_state:
                            s = score_job(resume_skills, existing.description, existing.title, existing.location, "remote" in existing.location.lower())
                            db.add(UserJobState(session_id=session_id, job_id=existing.id, score=s, status="New"))
                            added_jobs.append(existing)
                    continue

                # 4. Score job
                score = score_job(
                    resume_skills,
                    item["description"],
                    item["title"],
                    item["location"],
                    item.get("remote", False)
                )

                if score < threshold:
                    skipped_no_match += 1
                    continue

                # Recruiter contact discovery
                recruiter_name = ""
                recruiter_email = ""
                contact_source = ""
                contacts = find_public_contacts(item["company"], item["url"], item["description"])
                if contacts:
                    recruiter_name = contacts[0].get("name", "")
                    recruiter_email = contacts[0].get("email", "")
                    contact_source = contacts[0].get("type", contacts[0].get("source", ""))

                remote_flag = item.pop("remote", False)
                job = Job(
                    **item,
                    score=score,
                    date_found=get_now_ist(),
                    status="New",
                    recruiter_name=recruiter_name,
                    recruiter_email=recruiter_email,
                    contact_source=contact_source
                )
                db.add(job)
                db.flush()

                if session_id:
                    db.add(UserJobState(
                        session_id=session_id,
                        job_id=job.id,
                        score=score,
                        status="New"
                    ))

                added_jobs.append(job)
                time.sleep(0.01)

            db.commit()

        except Exception as exc:
            db.rollback()
            errors.append(f"{source_name}: {exc}")

    # Re-order and export so India & Remote are strictly on top
    clean_jobs = (
        db.query(Job)
        .order_by(Job.score.desc())
        .all()
    )
    if clean_jobs:
        export_jobs_to_csv(clean_jobs)

    return {
        "added": len(added_jobs),
        "errors": errors,
        "jobs": added_jobs,
        "skipped_no_match": skipped_no_match,
        "total_fetched": len(added_jobs) + skipped_no_match
    }


def rescore_all_jobs(db: Session, resume_path: Optional[str] = None, session_id: str = "default") -> dict:
    """
    Recalculates match scores with India & Remote prioritized on top.
    Persists scores into UserJobState scoped to this specific user session.
    """
    from app.database import UserJobState
    path = resume_path or settings.resume_path
    try:
        resume_text = extract_resume_text(path)
        profile = parse_resume_profile(resume_text)
        skills = profile["skills"]
        exp_months = profile.get("estimated_months", 0)

        cleanup_ineligible_jobs(db, exp_months)

        jobs = db.query(Job).all()
        existing_states = {
            s.job_id: s for s in db.query(UserJobState).filter_by(session_id=session_id).all()
        }

        for j in jobs:
            s = score_job(
                skills,
                j.description,
                j.title,
                j.location,
                "remote" in j.location.lower()
            )
            if j.id in existing_states:
                existing_states[j.id].score = s
                existing_states[j.id].updated_at = datetime.utcnow()
            else:
                db.add(UserJobState(
                    session_id=session_id,
                    job_id=j.id,
                    score=s,
                    status=j.status or "New"
                ))

            if session_id == "default":
                j.score = s

        db.commit()

        export_jobs_to_csv(jobs)

        return {
            "success": True,
            "jobs_rescored": len(jobs),
            "skills": sorted(list(skills)),
            "experience_level": profile.get("experience_level", "Entry Level"),
            "resume_name": Path(path).name,
            "session_id": session_id
        }
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to rescore jobs: {e}")
        return {"success": False, "error": str(e)}
