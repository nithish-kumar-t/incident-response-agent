import httpx
from config import settings


def send_prompt(prompt: str) -> str:
    payload = {
        "model": settings.OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
    }
    try:
        response = httpx.post(
            f"{settings.OLLAMA_URL}/api/generate",
            json=payload,
            timeout=60.0,
        )
        response.raise_for_status()
        return response.json()["response"]
    except httpx.TimeoutException:
        return "LLM timed out — no analysis available."
    except Exception as e:
        return f"LLM error: {str(e)}"
