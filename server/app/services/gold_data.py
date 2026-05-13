from datetime import date, datetime
from decimal import Decimal
import time
from typing import Any
from urllib.parse import urlparse

from ..config import settings
from ..errors import (
    ConfigMissingError,
    DatabricksConnectError,
    DatabricksQueryError,
    ResultParseError,
)

HEALTH_TABLE = "workspace.clicklake_gold.gold_workspace_health_daily_json"
PROMOTION_TABLE = "workspace.clicklake_gold.gold_promotion_performance_daily_json"
FUNNEL_TABLE = "workspace.clicklake_gold.gold_campaign_funnel_daily_json"

HEALTH_COLUMNS = [
    "event_date",
    "sdk_key",
    "raw_event_count",
    "valid_event_count",
    "invalid_event_count",
    "invalid_event_ratio",
    "distinct_sessions",
    "latest_event_time",
    "freshness_minutes",
]

PROMOTION_COLUMNS = [
    "event_date",
    "sdk_key",
    "campaign_id",
    "campaign_name",
    "promotion_id",
    "promotion_name",
    "placement",
    "promotion_views",
    "promotion_clicks",
    "ctr",
    "product_views_after_click",
    "add_to_cart_after_click",
    "product_view_rate_after_click",
    "add_to_cart_rate_after_click",
]

FUNNEL_COLUMNS = [
    "event_date",
    "sdk_key",
    "campaign_id",
    "campaign_name",
    "promotion_view_sessions",
    "promotion_click_sessions",
    "product_view_sessions",
    "add_to_cart_sessions",
    "view_to_click_rate",
    "click_to_product_view_rate",
    "click_to_add_to_cart_rate",
]

CacheKey = tuple[str, str | None]
_CACHE: dict[CacheKey, tuple[float, list[dict[str, Any]]]] = {}


def _normalized_host() -> str:
    host = (settings.databricks_host or "").strip()
    if not host:
        raise ConfigMissingError("Missing DATABRICKS_HOST")
    if host.startswith("http://") or host.startswith("https://"):
        parsed = urlparse(host)
        if not parsed.hostname:
            raise ConfigMissingError("Invalid DATABRICKS_HOST")
        return parsed.hostname
    return host


def _databricks_credentials() -> tuple[str, str, str]:
    host = _normalized_host()
    token = (settings.databricks_token or "").strip()
    http_path = (settings.databricks_http_path or "").strip()

    missing: list[str] = []
    if not token:
        missing.append("DATABRICKS_TOKEN")
    if not http_path:
        missing.append("DATABRICKS_HTTP_PATH")

    if missing:
        raise ConfigMissingError(
            f"Missing required environment variables: {', '.join(missing)}"
        )
    return host, token, http_path


def _serialize_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return value


def _build_query(table_name: str, columns: list[str], sdk_key: str | None) -> tuple[str, list[Any]]:
    select_columns = ", ".join(columns)
    query = f"SELECT {select_columns} FROM {table_name}"
    parameters: list[Any] = []

    if sdk_key and sdk_key.strip():
        query += " WHERE sdk_key = ?"
        parameters.append(sdk_key.strip())

    query += " ORDER BY event_date DESC"
    query += f" LIMIT {max(1, settings.gold_query_limit)}"
    return query, parameters


def _query_rows(table_name: str, columns: list[str], sdk_key: str | None) -> list[dict[str, Any]]:
    cache_key: CacheKey = (table_name, sdk_key.strip() if sdk_key else None)
    now = time.time()
    ttl = max(0, settings.gold_api_cache_ttl_seconds)
    cached = _CACHE.get(cache_key)
    if cached and now - cached[0] < ttl:
        return cached[1]

    host, token, http_path = _databricks_credentials()
    query, params = _build_query(table_name, columns, sdk_key)

    try:
        from databricks import sql
    except ImportError as exc:
        raise ConfigMissingError(
            "databricks-sql-connector is not installed. Run: pip install -r requirements.txt"
        ) from exc

    try:
        with sql.connect(
            server_hostname=host,
            http_path=http_path,
            access_token=token,
        ) as connection:
            with connection.cursor() as cursor:
                if params:
                    cursor.execute(query, params)
                else:
                    cursor.execute(query)
                rows = cursor.fetchall()
                column_names = [col[0] for col in (cursor.description or [])]
    except Exception as exc:
        message = str(exc).lower()
        if "warehouse" in message and (
            "stopped" in message
            or "not running" in message
            or "unavailable" in message
            or "start" in message
        ):
            raise DatabricksConnectError(str(exc), warehouse_unavailable=True) from exc
        if "connect" in message or "dns" in message or "timeout" in message:
            raise DatabricksConnectError(str(exc)) from exc
        raise DatabricksQueryError(str(exc)) from exc

    try:
        result: list[dict[str, Any]] = []
        for row in rows:
            mapped = {
                column_names[idx]: _serialize_value(value)
                for idx, value in enumerate(row)
                if idx < len(column_names)
            }
            result.append(mapped)
        _CACHE[cache_key] = (now, result)
        return result
    except Exception as exc:
        raise ResultParseError(str(exc)) from exc


def get_health_rows(sdk_key: str | None = None) -> list[dict[str, Any]]:
    return _query_rows(HEALTH_TABLE, HEALTH_COLUMNS, sdk_key)


def get_promotion_performance_rows(sdk_key: str | None = None) -> list[dict[str, Any]]:
    return _query_rows(PROMOTION_TABLE, PROMOTION_COLUMNS, sdk_key)


def get_campaign_funnel_rows(sdk_key: str | None = None) -> list[dict[str, Any]]:
    return _query_rows(FUNNEL_TABLE, FUNNEL_COLUMNS, sdk_key)
