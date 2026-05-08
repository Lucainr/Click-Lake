from pathlib import Path

from pydantic import BaseSettings


class Settings(BaseSettings):
    app_name: str = "Click Lake Collector"
    allow_origins: list[str] = ["*"]
    raw_events_base_rel_dir: str = "server/data/raw_events"
    max_events_per_file: int = 1000
    databricks_host: str | None = None
    databricks_token: str | None = None
    databricks_http_path: str | None = None

    @property
    def raw_events_base_abs_dir(self) -> Path:
        project_root = Path(__file__).resolve().parents[2]
        return project_root / self.raw_events_base_rel_dir

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
