from __future__ import annotations

from pathlib import Path
from typing import Iterable
from urllib.parse import urlparse

from ..config import settings
from ..errors import ConfigMissingError, DatabricksConnectError, DatabricksQueryError


class SqlFileExecutionError(Exception):
    def __init__(self, *, sql_file: Path, statement_index: int, cause: Exception):
        self.sql_file = sql_file
        self.statement_index = statement_index
        self.cause = cause
        super().__init__(
            f"Failed SQL file={sql_file} statement={statement_index}: {cause}"
        )


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


def _credentials() -> tuple[str, str, str]:
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


def _split_sql_statements(script: str) -> list[str]:
    statements: list[str] = []
    current: list[str] = []

    in_single_quote = False
    in_double_quote = False

    for char in script:
        if char == "'" and not in_double_quote:
            in_single_quote = not in_single_quote
        elif char == '"' and not in_single_quote:
            in_double_quote = not in_double_quote

        if char == ";" and not in_single_quote and not in_double_quote:
            statement = "".join(current).strip()
            if statement:
                statements.append(statement)
            current = []
            continue

        current.append(char)

    tail = "".join(current).strip()
    if tail:
        statements.append(tail)

    return statements


def execute_sql_statements(statements: Iterable[str]) -> int:
    host, token, http_path = _credentials()

    try:
        from databricks import sql
    except ImportError as exc:
        raise ConfigMissingError(
            "databricks-sql-connector is not installed. Run: pip install -r requirements.txt"
        ) from exc

    executed = 0
    try:
        with sql.connect(
            server_hostname=host,
            http_path=http_path,
            access_token=token,
        ) as connection:
            with connection.cursor() as cursor:
                for statement in statements:
                    cursor.execute(statement)
                    executed += 1
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

    return executed


def execute_sql_file(sql_file: Path) -> int:
    if not sql_file.exists():
        raise FileNotFoundError(f"SQL file not found: {sql_file}")

    script = sql_file.read_text(encoding="utf-8")
    statements = _split_sql_statements(script)
    if not statements:
        return 0

    try:
        return execute_sql_statements(statements)
    except Exception as exc:  # noqa: BLE001
        raise SqlFileExecutionError(sql_file=sql_file, statement_index=-1, cause=exc) from exc
