from pathlib import Path
import pymupdf
from docx import Document

SUPPORTED = {".pdf", ".docx", ".txt"}

def extract_resume_text(path: str) -> str:
    file = Path(path)
    if not file.exists():
        raise FileNotFoundError(f"Resume not found: {file}. Upload a PDF, DOCX, or TXT resume in the dashboard.")
    suffix = file.suffix.lower()
    if suffix == ".pdf":
        with pymupdf.open(file) as pdf:
            text = "\n".join(page.get_text() for page in pdf)
    elif suffix == ".docx":
        doc = Document(file)
        text = "\n".join(p.text for p in doc.paragraphs)
    elif suffix == ".txt":
        text = file.read_text(encoding="utf-8", errors="ignore")
    else:
        raise ValueError("Only PDF, DOCX, and TXT resumes are supported.")
    if not text.strip():
        raise ValueError("No readable text found. If this is a scanned PDF, run OCR before uploading.")
    return text[:30000]
