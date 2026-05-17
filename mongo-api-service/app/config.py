from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    MONGO_URI: str = "mongodb://mongo:27017"
    MONGO_DB: str = "servicedb"
    APP_NAME: str = "Mongo API Service"
    LOG_FILE: str = "/app/logs/service.log"

    class Config:
        env_file = ".env"


settings = Settings()
