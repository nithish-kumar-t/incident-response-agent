from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    OPENAI_API_KEY: str
    OPENAI_MODEL: str = "gpt-4o"

    # Service health check — {service_name} is interpolated at call time
    SERVICE_HEALTH_URL_TEMPLATE: str = "http://localhost:8080/health/{service_name}"

    # Log file paths — {service_name} is interpolated where applicable
    SERVICE_LOGS_PATH_TEMPLATE: str = "C:\\UIC_COURSES\\uncommon_hack\\final_ones\\apps\\mongo-api-service\\logs\\service.log"
    API_ERROR_LOGS_PATH: str = "C:\\UIC_COURSES\\uncommon_hack\\final_ones\\apps\\mongo-api-service\\logs\\api_errors.log"
    ERROR_LOGS_PATH: str = "C:\\UIC_COURSES\\uncommon_hack\\final_ones\\apps\\mongo-api-service\\logs\\errors.log"
    LOG_TAIL_LINES: int = 200

    # Local git repo for Agent 3 to read source code from
    GIT_REPO_PATH: str = "."

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
