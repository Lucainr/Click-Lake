from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

from ..errors import ApiError, UnknownApiError
from ..schemas import (
    ErrorResponse,
    GoldDashboardResponse,
    GoldCampaignFunnelRow,
    GoldHealthRow,
    GoldPromotionPerformanceRow,
)
from ..services.gold_data import (
    get_dashboard_rows,
    get_campaign_funnel_rows,
    get_health_rows,
    get_promotion_performance_rows,
)

router = APIRouter(prefix="/api/gold", tags=["gold"])


def _error_response(exc: ApiError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content=ErrorResponse(
            error_code=exc.error_code,
            message=exc.message,
            details=exc.details,
        ).dict(),
    )


@router.get("/health", response_model=list[GoldHealthRow])
async def get_gold_health(
    sdk_key: str | None = Query(default=None, description="Optional sdk_key filter"),
) -> list[GoldHealthRow] | JSONResponse:
    try:
        return get_health_rows(sdk_key=sdk_key)
    except ApiError as exc:
        return _error_response(exc)
    except Exception as exc:
        return _error_response(UnknownApiError(str(exc)))


@router.get("/promotion-performance", response_model=list[GoldPromotionPerformanceRow])
async def get_gold_promotion_performance(
    sdk_key: str | None = Query(default=None, description="Optional sdk_key filter"),
) -> list[GoldPromotionPerformanceRow] | JSONResponse:
    try:
        return get_promotion_performance_rows(sdk_key=sdk_key)
    except ApiError as exc:
        return _error_response(exc)
    except Exception as exc:
        return _error_response(UnknownApiError(str(exc)))


@router.get("/campaign-funnel", response_model=list[GoldCampaignFunnelRow])
async def get_gold_campaign_funnel(
    sdk_key: str | None = Query(default=None, description="Optional sdk_key filter"),
) -> list[GoldCampaignFunnelRow] | JSONResponse:
    try:
        return get_campaign_funnel_rows(sdk_key=sdk_key)
    except ApiError as exc:
        return _error_response(exc)
    except Exception as exc:
        return _error_response(UnknownApiError(str(exc)))


@router.get("/dashboard", response_model=GoldDashboardResponse)
async def get_gold_dashboard(
    sdk_key: str | None = Query(default=None, description="Optional sdk_key filter"),
) -> GoldDashboardResponse | JSONResponse:
    try:
        rows = get_dashboard_rows(sdk_key=sdk_key)
        return GoldDashboardResponse(**rows)
    except ApiError as exc:
        return _error_response(exc)
    except Exception as exc:
        return _error_response(UnknownApiError(str(exc)))
