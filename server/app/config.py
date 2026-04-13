from pydantic import BaseSettings


class Settings(BaseSettings):
    app_name: str = "Click Lake Collector"
    allow_origins: list[str] = ["*"]


settings = Settings()
