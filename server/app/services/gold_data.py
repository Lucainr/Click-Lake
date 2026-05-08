import json
from pathlib import Path
from typing import Any

from ..config import settings


def _read_json_rows(file_name: str) -> list[dict[str, Any]]:
    file_path = settings.gold_api_data_abs_dir / file_name
    if not file_path.exists():
        return []

    with file_path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, list):
        raise ValueError(f"{file_path} must be a JSON array")

    return [row for row in data if isinstance(row, dict)]


def _filter_by_sdk_key(rows: list[dict[str, Any]], sdk_key: str | None) -> list[dict[str, Any]]:
    if not sdk_key:
        return rows
    target = sdk_key.strip()
    if not target:
        return rows
    return [row for row in rows if str(row.get("sdk_key", "")).strip() == target]


def get_health_rows(sdk_key: str | None = None) -> list[dict[str, Any]]:
    rows = _read_json_rows("health.json")
    return _filter_by_sdk_key(rows, sdk_key)


def get_promotion_performance_rows(sdk_key: str | None = None) -> list[dict[str, Any]]:
    rows = _read_json_rows("promotion_performance.json")
    return _filter_by_sdk_key(rows, sdk_key)


def get_campaign_funnel_rows(sdk_key: str | None = None) -> list[dict[str, Any]]:
    rows = _read_json_rows("campaign_funnel.json")
    return _filter_by_sdk_key(rows, sdk_key)


def ensure_data_dir() -> Path:
    settings.gold_api_data_abs_dir.mkdir(parents=True, exist_ok=True)
    return settings.gold_api_data_abs_dir
