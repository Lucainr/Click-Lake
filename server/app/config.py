from pathlib import Path

from pydantic import BaseSettings


class Settings(BaseSettings):
    app_name: str = "Click Lake Collector"
    allow_origins: list[str] = ["*"]
    raw_events_base_rel_dir: str = "server/data/raw_events"
    gold_api_data_rel_dir: str = "server/data/api"
    max_events_per_file: int = 1000

    @property
    def raw_events_base_abs_dir(self) -> Path:
        project_root = Path(__file__).resolve().parents[2]
        return project_root / self.raw_events_base_rel_dir

    @property
    def gold_api_data_abs_dir(self) -> Path:
        project_root = Path(__file__).resolve().parents[2]
        return project_root / self.gold_api_data_rel_dir


settings = Settings()
