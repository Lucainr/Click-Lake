from pathlib import Path

from pydantic import BaseSettings


class Settings(BaseSettings):
    app_name: str = "Click Lake Collector"
    allow_origins: list[str] = ["*"]
    raw_events_rel_path: str = "server/data/raw_events.jsonl"

    @property
    def raw_events_abs_path(self) -> Path:
        project_root = Path(__file__).resolve().parents[2]
        return project_root / self.raw_events_rel_path


settings = Settings()
