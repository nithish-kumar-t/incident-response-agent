from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-4o"

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
