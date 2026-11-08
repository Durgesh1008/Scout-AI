# ==============================================================================
# SCOUT-AI PRODUCTION DOCKERFILE
# ==============================================================================
FROM python:3.11-slim

# Prevent Python from writing .pyc and buffer stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000

WORKDIR /app

# Install system dependencies + Node.js (required for live JS compiler execution)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    nodejs \
    npm \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source code
COPY . .

# Ensure data and uploads directories exist
RUN mkdir -p /app/data /app/uploads /app/data/drafts /app/data/resumes

EXPOSE 8000

# Start FastAPI server (Telegram bot daemon starts automatically via startup event)
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
