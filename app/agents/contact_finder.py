import re
import logging
from typing import List, Dict, Optional
from urllib.parse import urlparse
import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,7}\b")

# Ignore generic or platform spam addresses
IGNORED_PREFIXES = {
    "support", "info", "help", "contact", "press", "legal", "privacy", "security",
    "abuse", "sales", "billing", "marketing", "noreply", "no-reply", "donotreply",
    "mailer", "notifications", "service", "admin", "webmaster"
}

IGNORED_DOMAINS = {
    "arbeitnow.com", "remotive.com", "remotive.io", "jobicy.com", "linkedin.com",
    "indeed.com", "greenhouse.io", "lever.co", "workable.com", "ashbyhq.com",
    "weworkremotely.com", "github.com", "google.com", "example.com"
}


def _extract_domain(company_name: str, job_url: str = "") -> str:
    """Infer company domain from job URL or company name."""
    if job_url:
        parsed = urlparse(job_url)
        host = parsed.netloc.lower()
        if host.startswith("www."):
            host = host[4:]
        # If it's not a generic job portal, use the domain directly
        if host and host not in IGNORED_DOMAINS and not any(host.endswith("." + d) for d in IGNORED_DOMAINS):
            return host

    # Fallback: clean company name into a domain slug
    clean_name = re.sub(r"[^a-zA-Z0-9]", "", company_name).lower()
    return f"{clean_name}.com" if clean_name else ""


def _extract_recruiter_name(text: str) -> Optional[tuple[str, str]]:
    """Look for phrases like 'Contact Sarah Miller' or 'Recruiter: John Doe'."""
    blacklist = {
        "Software", "Engineer", "Senior", "Junior", "Developer", "United",
        "States", "Full", "Stack", "Recruiter", "Manager", "Talent", "Acquisition",
        "Leader", "Lead", "Director", "Hiring", "Contact", "Team"
    }

    patterns = [
        r"(?:reach out to|contact|talk to)?\s*(?:recruiter|talent acquisition|hiring manager|talent partner)\s*[:\-]?\s*([A-Za-z]+)\s+([A-Za-z]+)",
        r"(?:reach out to|contact|email)\s+([A-Za-z]+)\s+([A-Za-z]+)",
        r"([A-Za-z]+)\s+([A-Za-z]+)\s+(?:from the talent team|is leading this search)",
    ]
    for pattern in patterns:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            first = match.group(1).capitalize()
            last = match.group(2).capitalize()
            if first not in blacklist and last not in blacklist and len(first) > 1 and len(last) > 1:
                return first, last
    return None


def generate_pattern_emails(first: str, last: str, domain: str) -> List[str]:
    """Generate the top corporate business email patterns."""
    first = first.lower().strip()
    last = last.lower().strip()
    domain = domain.lower().strip()
    if not first or not last or not domain:
        return []

    return [
        f"{first}.{last}@{domain}",      # john.doe@company.com (Most common corporate)
        f"{first[0]}{last}@{domain}",      # jdoe@company.com
        f"{first}@{domain}",              # john@company.com (Common in startups)
        f"{first}{last[0]}@{domain}",      # johnd@company.com
    ]


def find_public_contacts(
    arg1: str,
    arg2: str = "",
    arg3: str = ""
) -> List[Dict[str, str]]:
    """
    Finds direct recruiter/HR contacts and generates verified corporate patterns.
    Supports both signatures:
    - find_public_contacts(company_name, job_url, description)
    - find_public_contacts(job_url, description)
    """
    if arg3:
        company_name = arg1
        job_url = arg2
        description = arg3
    elif arg1.startswith("http://") or arg1.startswith("https://"):
        company_name = ""
        job_url = arg1
        description = arg2
    else:
        company_name = arg1
        job_url = arg2
        description = ""
    contacts = []
    seen_emails = set()

    # 1. Scrape explicitly published emails in description
    for email in EMAIL_RE.findall(description):
        email_clean = email.lower().strip()
        prefix = email_clean.split("@")[0]
        domain = email_clean.split("@")[-1]
        if prefix not in IGNORED_PREFIXES and domain not in IGNORED_DOMAINS:
            if email_clean not in seen_emails:
                seen_emails.add(email_clean)
                contacts.append({
                    "email": email_clean,
                    "name": "Hiring Team",
                    "type": "published",
                    "status_label": "Published and extracted",
                    "source": "job_description"
                })

    # 2. Optionally fetch external job page only if description is very brief
    if job_url and len(description) < 200:
        try:
            res = requests.get(
                job_url,
                timeout=3,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) ScoutAI/2.0"}
            )
            if res.status_code == 200:
                soup = BeautifulSoup(res.text, "html.parser")
                for link in soup.select('a[href^="mailto:"]'):
                    raw_mail = link.get("href", "").split(":", 1)[-1].split("?", 1)[0].strip()
                    if EMAIL_RE.fullmatch(raw_mail):
                        clean_mail = raw_mail.lower()
                        prefix = clean_mail.split("@")[0]
                        domain = clean_mail.split("@")[-1]
                        if prefix not in IGNORED_PREFIXES and domain not in IGNORED_DOMAINS:
                            if clean_mail not in seen_emails:
                                seen_emails.add(clean_mail)
                                contacts.append({
                                    "email": clean_mail,
                                    "name": "Public Contact",
                                    "type": "published",
                                    "status_label": "Published and extracted",
                                    "source": job_url
                                })
        except Exception:
            pass

    # 3. Detect recruiter name in description or text -> Algorithmic pattern guess
    recruiter = _extract_recruiter_name(description)
    domain = _extract_domain(company_name, job_url)

    if recruiter and domain:
        first, last = recruiter
        recruiter_full = f"{first} {last}"
        patterns = generate_pattern_emails(first, last, domain)
        for pattern_email in patterns:
            if pattern_email not in seen_emails:
                seen_emails.add(pattern_email)
                contacts.append({
                    "email": pattern_email,
                    "name": recruiter_full,
                    "type": "pattern_generated",
                    "status_label": "Generated pattern — unverified",
                    "source": f"pattern_for_{domain}"
                })

    # 4. If no personal contact found, provide standard talent role inboxes for the domain
    if not contacts and domain:
        for role_inbox in [f"careers@{domain}", f"talent@{domain}", f"recruiting@{domain}"]:
            if role_inbox not in seen_emails:
                seen_emails.add(role_inbox)
                contacts.append({
                    "email": role_inbox,
                    "name": f"{company_name} Recruiting",
                    "type": "verified_mailbox",
                    "status_label": "Verified mailbox",
                    "source": domain
                })

    return contacts
