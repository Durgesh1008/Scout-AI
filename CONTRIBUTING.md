# Contributing to Scout-AI

Thank you for your interest in contributing to **Scout-AI**! We welcome contributions of all kinds: bug reports, feature requests, documentation improvements, new job feed integrations, and plugin enhancements.

---

## Code of Conduct

By participating in this project, you agree to maintain a respectful, welcoming, and harassment-free environment for everyone.

---

## How Can I Contribute?

### 1. Reporting Bugs
- Search existing issues to ensure the bug hasn't already been reported.
- Open a new issue with a clear title and description.
- Include reproduction steps, environment details (OS, Python version, LLM provider), and error tracebacks.

### 2. Suggesting Features & Job Sources
- Open an issue describing the proposed feature or job source.
- Explain the use case and why it benefits users.
- If proposing a job source, check that it provides a public, compliant API or feed.

### 3. Submitting Pull Requests
1. **Fork the repo** and clone your fork locally.
2. **Create a branch** for your work:
   ```bash
   git checkout -b feature/my-cool-feature
   ```
3. **Set up your environment**:
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # Or .venv\Scripts\Activate.ps1 on Windows
   pip install -r requirements.txt
   ```
4. **Ensure clean secrets handling**:
   - **NEVER** commit personal API keys, passwords, or resumes.
   - Keep default values in `app/config.py` generic (empty strings).
   - Use `.env` for local testing.
5. **Test your changes**:
   - Ensure the FastAPI server boots cleanly (`uvicorn app.main:app`).
   - Test endpoints and agent flows.
6. **Commit your changes**:
   ```bash
   git commit -m "feat(job_hunter): add new remote feed parser"
   ```
7. **Push to your fork and open a Pull Request**:
   - Provide a clear summary of what was changed and why.
   - Reference any related issues.

---

## Coding Standards

- **Python**: Follow PEP 8 guidelines. Write clean, readable code with type hints where appropriate.
- **Error Handling**: Gracefully handle network timeouts and external API outages without crashing the background scheduler.
- **Privacy First**: Respect user privacy. Any persistent user data must remain in local SQLite or local filesystem.

Thank you for helping make Scout-AI better for everyone!
