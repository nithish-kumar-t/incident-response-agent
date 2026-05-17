from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # ── LLM ───────────────────────────────────────────────────────────────────
    # Ollama by default. To use OpenAI: set LLM_BASE_URL=https://api.openai.com/v1
    # and LLM_API_KEY to your OpenAI key.
    LLM_BASE_URL: str = "http://host.docker.internal:11434/v1"
    LLM_API_KEY: str = "ollama"
    LLM_MODEL: str = "mistral-nemo"

    # ── Services ──────────────────────────────────────────────────────────────
    NOTIFIER_URL: str = "http://notifier:8002/notify"

    # ── Paths (resolved inside the Docker container) ──────────────────────────
    SERVICE_REGISTRY_PATH: str = "/app/service_registry.json"

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
