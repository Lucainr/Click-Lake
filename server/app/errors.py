from dataclasses import dataclass


@dataclass
class ApiError(Exception):
    error_code: str
    message: str
    details: str | None = None
    status_code: int = 500


class ConfigMissingError(ApiError):
    def __init__(self, details: str):
        super().__init__(
            error_code="CONFIG_MISSING",
            message="Configuration is missing",
            details=details,
            status_code=500,
        )


class DatabricksConnectError(ApiError):
    def __init__(self, details: str, *, warehouse_unavailable: bool = False):
        if warehouse_unavailable:
            super().__init__(
                error_code="WAREHOUSE_UNAVAILABLE",
                message="Databricks SQL Warehouse may be unavailable",
                details=details,
                status_code=503,
            )
        else:
            super().__init__(
                error_code="DATABRICKS_CONNECT_FAILED",
                message="Failed to connect to Databricks",
                details=details,
                status_code=503,
            )


class DatabricksQueryError(ApiError):
    def __init__(self, details: str):
        super().__init__(
            error_code="DATABRICKS_QUERY_FAILED",
            message="Failed to query Databricks Gold table",
            details=details,
            status_code=500,
        )


class ResultParseError(ApiError):
    def __init__(self, details: str):
        super().__init__(
            error_code="RESULT_PARSE_FAILED",
            message="Failed to parse Databricks query result",
            details=details,
            status_code=500,
        )


class UnknownApiError(ApiError):
    def __init__(self, details: str):
        super().__init__(
            error_code="UNKNOWN_ERROR",
            message="Unknown server error",
            details=details,
            status_code=500,
        )
