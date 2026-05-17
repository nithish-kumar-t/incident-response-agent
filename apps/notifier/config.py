from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    SMTP_HOST: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    EMAIL_SENDER: str
    EMAIL_RECEIVER: str
    EMAIL_APP_PASSWORD: str

    class Config:
        env_file = ".env"


settings = Settings()
