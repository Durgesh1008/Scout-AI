import logging
import requests
from typing import Optional
from app.config import settings

logger = logging.getLogger(__name__)


class LLMError(RuntimeError):
    pass


def _call_gemini(
    prompt: str,
    system: str,
    temperature: float = 0.3,
    model: Optional[str] = None
) -> str:
    """Call Google Gemini API (100% Free tier: 15 RPM / 1M TPM via Google AI Studio)."""
    api_key = settings.gemini_api_key
    if not api_key:
        raise LLMError("GEMINI_API_KEY is not configured.")

    model_name = model or settings.gemini_model or "gemini-1.5-flash"
    # Auto-correct invalid or experimental model names
    if "2.5" in model_name:
        model_name = "gemini-1.5-flash"

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"

    payload = {
        "contents": [
            {
                "role": "user",
                "parts": [{"text": prompt}]
            }
        ],
        "systemInstruction": {
            "parts": [{"text": system}]
        },
        "generationConfig": {
            "temperature": temperature,
            "maxOutputTokens": 4096
        }
    }

    response = requests.post(url, json=payload, timeout=(10, 60))
    # If 404 Not Found (invalid model name on Google endpoint), retry with standard gemini-1.5-flash
    if response.status_code == 404 and model_name != "gemini-1.5-flash":
        fallback_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}"
        response = requests.post(fallback_url, json=payload, timeout=(10, 60))

    if response.status_code == 429:
        raise LLMError("Gemini rate limit reached (HTTP 429).")
    response.raise_for_status()

    data = response.json()
    try:
        candidates = data.get("candidates", [])
        if not candidates:
            raise LLMError("Gemini returned no candidates.")
        parts = candidates[0].get("content", {}).get("parts", [])
        text = "".join(part.get("text", "") for part in parts)
        return text.strip()
    except (IndexError, KeyError) as e:
        raise LLMError(f"Unexpected Gemini response structure: {e}")


def _call_groq(
    prompt: str,
    system: str,
    temperature: float = 0.3,
    model: Optional[str] = None
) -> str:
    """Call Groq Cloud API (100% Free tier: 30 RPM via console.groq.com)."""
    api_key = settings.groq_api_key
    if not api_key:
        raise LLMError("GROQ_API_KEY is not configured.")

    model_name = model or settings.groq_model or "llama-3.3-70b-versatile"
    url = "https://api.groq.com/openai/v1/chat/completions"

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": model_name,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt}
        ],
        "temperature": temperature,
        "max_tokens": 4096
    }

    response = requests.post(url, headers=headers, json=payload, timeout=(10, 60))
    if response.status_code == 429:
        raise LLMError("Groq rate limit reached (HTTP 429).")
    response.raise_for_status()

    data = response.json()
    choices = data.get("choices", [])
    if not choices:
        raise LLMError("Groq returned empty choices.")
    content = choices[0].get("message", {}).get("content", "")
    return content.strip()


def _call_ollama(
    prompt: str,
    system: str,
    temperature: float = 0.3,
    response_format=None
) -> str:
    """Call local Ollama server (100% Free & Local execution)."""
    url = settings.ollama_base_url.rstrip("/") + "/api/chat"

    payload = {
        "model": settings.ollama_model,
        "stream": False,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt}
        ],
        "options": {
            "temperature": temperature,
            "num_ctx": 4096
        }
    }

    if response_format:
        payload["format"] = response_format

    try:
        response = requests.post(url, json=payload, timeout=(10, 180))
        response.raise_for_status()

        data = response.json()
        content = data.get("message", {}).get("content")

        if not content:
            raise LLMError("Ollama returned an empty response.")

        return content.strip()

    except requests.Timeout as exc:
        raise LLMError("Ollama request timed out.") from exc

    except requests.RequestException as exc:
        raise LLMError(
            f"Cannot connect to Ollama at {url}. "
            f"Check that Ollama is running (`ollama serve`). Details: {exc}"
        ) from exc


# For backward compatibility
OllamaError = LLMError


def generate(
    prompt: str,
    system: str = "You are a careful, helpful personal assistant.",
    temperature: float = 0.3,
    response_format=None
) -> str:
    """
    Generate LLM completion with automatic provider fallback:
    Configured Provider -> Gemini -> Groq -> Local Ollama
    """
    preferred = (settings.llm_provider or "gemini").lower()
    errors = []

    # Build sequence of providers to try
    providers = []
    if preferred == "gemini":
        providers = ["gemini", "groq", "ollama"]
    elif preferred == "groq":
        providers = ["groq", "gemini", "ollama"]
    else:
        providers = ["ollama", "gemini", "groq"]

    for provider in providers:
        try:
            if provider == "gemini" and settings.gemini_api_key:
                logger.info("Generating with Google Gemini...")
                return _call_gemini(prompt, system, temperature)
            elif provider == "groq" and settings.groq_api_key:
                logger.info("Generating with Groq...")
                return _call_groq(prompt, system, temperature)
            elif provider == "ollama":
                logger.info("Generating with Ollama...")
                return _call_ollama(prompt, system, temperature, response_format)
        except Exception as e:
            logger.warning(f"Provider {provider} failed: {e}")
            errors.append(f"{provider}: {e}")

    raise LLMError(f"All LLM providers failed. Errors: {'; '.join(errors)}")


def check_connection() -> dict:
    """Check connectivity for all configured free-tier LLM providers."""
    status = {"gemini": False, "groq": False, "ollama": False}

    # Gemini check
    if settings.gemini_api_key:
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models?key={settings.gemini_api_key}"
            res = requests.get(url, timeout=5)
            status["gemini"] = res.status_code == 200
        except Exception:
            status["gemini"] = False

    # Groq check
    if settings.groq_api_key:
        try:
            headers = {"Authorization": f"Bearer {settings.groq_api_key}"}
            res = requests.get("https://api.groq.com/openai/v1/models", headers=headers, timeout=5)
            status["groq"] = res.status_code == 200
        except Exception:
            status["groq"] = False

    # Ollama check
    try:
        url = settings.ollama_base_url.rstrip("/") + "/api/tags"
        res = requests.get(url, timeout=5)
        status["ollama"] = res.status_code == 200
    except Exception:
        status["ollama"] = False

    return status
