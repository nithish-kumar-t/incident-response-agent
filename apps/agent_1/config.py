from pydantic_settings import BaseSettings
from typing import Dict


class Settings(BaseSettings):
    APP_NAME: str = "Incident Response Agent"
    PORT: int = 8001

    # Ollama
    OLLAMA_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "mistral-nemo"

    # Map service name (from Prometheus alert labels) to its log file path
    SERVICE_LOG_FILES: Dict[str, str] = {
        "weather-app1": "../../apps/weather-app1/logs/service.log",
        "mongo-api-service": "../../apps/mongo-api-service/logs/service.log",
    }

    # How many log lines to send to the LLM
    LOG_TAIL_LINES: int = 50

    class Config:
        env_file = ".env"


settings = Settings()
