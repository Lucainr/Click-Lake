import json
import logging
import time
from datetime import date, datetime
from decimal import Decimal
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

_redis_client: Any | None = None


def _get_redis() -> Any | None:
    global _redis_client
    if _redis_client is not None:
        return _redis_client
    try:
        import redis
        _redis_client = redis.Redis.from_url(settings.redis_url, decode_responses=True)
        _redis_client.ping()
        return _redis_client
    except Exception as exc:
        logging.getLogger("clicklake.gold_data").warning("redis unavailable, falling back to in-process cache: %s", exc)
        return None


_FALLBACK_CACHE: dict[str, tuple[float, str]] = {}


def _cache_get(key: str) -> Any | None:
    r = _get_redis()
    if r is not None:
        raw = r.get(key)
        return json.loads(raw) if raw is not None else None

    entry = _FALLBACK_CACHE.get(key)
    if entry and time.time() - entry[0] < max(0, settings.gold_api_cache_ttl_seconds):
        return json.loads(entry[1])
    return None


def _cache_set(key: str, value: Any) -> None:
    ttl = max(1, settings.gold_api_cache_ttl_seconds)
    r = _get_redis()
    if r is not None:
        r.setex(key, ttl, json.dumps(value))
        return
    _FALLBACK_CACHE[key] = (time.time(), json.dumps(value))


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


def _load_sql_module():
    try:
        from databricks import sql
        return sql
    except ImportError as exc:
        raise ConfigMissingError(
            "databricks-sql-connector is not installed. Run: pip install -r requirements.txt"
        ) from exc


def _normalize_dbx_error(exc: Exception) -> Exception:
    message = str(exc).lower()
    if "warehouse" in message and (
        "stopped" in message
        or "not running" in message
        or "unavailable" in message
        or "start" in message
    ):
        return DatabricksConnectError(str(exc), warehouse_unavailable=True)
    if "connect" in message or "dns" in message or "timeout" in message:
        return DatabricksConnectError(str(exc))
    return DatabricksQueryError(str(exc))


def _execute_query(cursor: Any, table_name: str, columns: list[str], sdk_key: str | None) -> list[dict[str, Any]]:
    query, params = _build_query(table_name, columns, sdk_key)

    try:
        if params:
            cursor.execute(query, params)
        else:
            cursor.execute(query)
        rows = cursor.fetchall()
        column_names = [col[0] for col in (cursor.description or [])]
    except Exception as exc:
        raise _normalize_dbx_error(exc) from exc

    try:
        result: list[dict[str, Any]] = []
        for row in rows:
            mapped = {
                column_names[idx]: _serialize_value(value)
                for idx, value in enumerate(row)
                if idx < len(column_names)
            }
            result.append(mapped)
        return result
    except Exception as exc:
        raise ResultParseError(str(exc)) from exc


def _query_rows(table_name: str, columns: list[str], sdk_key: str | None) -> list[dict[str, Any]]:
    normalized_key = sdk_key.strip() if sdk_key else None
    cache_key = f"gold:table:{table_name}:{normalized_key or 'all'}"

    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    host, token, http_path = _databricks_credentials()
    sql = _load_sql_module()

    try:
        with sql.connect(
            server_hostname=host,
            http_path=http_path,
            access_token=token,
        ) as connection:
            with connection.cursor() as cursor:
                result = _execute_query(cursor, table_name, columns, sdk_key)
    except Exception as exc:
        if isinstance(exc, (ConfigMissingError, DatabricksConnectError, DatabricksQueryError, ResultParseError)):
            raise
        raise _normalize_dbx_error(exc) from exc

    _cache_set(cache_key, result)
    return result


def get_health_rows(sdk_key: str | None = None) -> list[dict[str, Any]]:
    return _query_rows(HEALTH_TABLE, HEALTH_COLUMNS, sdk_key)


def get_promotion_performance_rows(sdk_key: str | None = None) -> list[dict[str, Any]]:
    return _query_rows(PROMOTION_TABLE, PROMOTION_COLUMNS, sdk_key)


def get_campaign_funnel_rows(sdk_key: str | None = None) -> list[dict[str, Any]]:
    return _query_rows(FUNNEL_TABLE, FUNNEL_COLUMNS, sdk_key)


def get_dashboard_rows(sdk_key: str | None = None) -> dict[str, list[dict[str, Any]]]:
    normalized_sdk_key = sdk_key.strip() if sdk_key else None
    cache_key = f"gold:dashboard:{normalized_sdk_key or 'all'}"

    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    host, token, http_path = _databricks_credentials()
    sql = _load_sql_module()

    try:
        with sql.connect(
            server_hostname=host,
            http_path=http_path,
            access_token=token,
        ) as connection:
            with connection.cursor() as cursor:
                health_rows = _execute_query(cursor, HEALTH_TABLE, HEALTH_COLUMNS, normalized_sdk_key)
                promotion_rows = _execute_query(cursor, PROMOTION_TABLE, PROMOTION_COLUMNS, normalized_sdk_key)
                funnel_rows = _execute_query(cursor, FUNNEL_TABLE, FUNNEL_COLUMNS, normalized_sdk_key)
    except Exception as exc:
        if isinstance(exc, (ConfigMissingError, DatabricksConnectError, DatabricksQueryError, ResultParseError)):
            raise
        raise _normalize_dbx_error(exc) from exc

    dashboard: dict[str, list[dict[str, Any]]] = {
        "health": health_rows,
        "promotion": promotion_rows,
        "funnel": funnel_rows,
    }
    _cache_set(cache_key, dashboard)
    return dashboard
