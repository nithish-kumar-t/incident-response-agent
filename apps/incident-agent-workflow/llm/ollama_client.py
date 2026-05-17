import httpx

OLLAMA_URL = "http://host.docker.internal:11434"
OLLAMA_MODEL = "mistral-nemo"


def send_prompt(prompt: str) -> str:
    try:
        response = httpx.post(
            f"{OLLAMA_URL}/api/generate",
            json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": False},
            timeout=60.0,
        )
        response.raise_for_status()
        return response.json()["response"]
    except httpx.TimeoutException:
        return "LLM timed out — no analysis available."
    except Exception as e:
        return f"LLM error: {str(e)}"
