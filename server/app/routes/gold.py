from fastapi import APIRouter, HTTPException, Query

from ..schemas import (
    GoldCampaignFunnelRow,
    GoldHealthRow,
    GoldPromotionPerformanceRow,
)
from ..services.gold_data import (
    get_campaign_funnel_rows,
    get_health_rows,
    get_promotion_performance_rows,
)

router = APIRouter(prefix="/api/gold", tags=["gold"])


@router.get("/health", response_model=list[GoldHealthRow])
async def get_gold_health(
    sdk_key: str | None = Query(default=None, description="Optional sdk_key filter"),
) -> list[GoldHealthRow]:
    try:
        return get_health_rows(sdk_key=sdk_key)
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/promotion-performance", response_model=list[GoldPromotionPerformanceRow])
async def get_gold_promotion_performance(
    sdk_key: str | None = Query(default=None, description="Optional sdk_key filter"),
) -> list[GoldPromotionPerformanceRow]:
    try:
        return get_promotion_performance_rows(sdk_key=sdk_key)
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/campaign-funnel", response_model=list[GoldCampaignFunnelRow])
async def get_gold_campaign_funnel(
    sdk_key: str | None = Query(default=None, description="Optional sdk_key filter"),
) -> list[GoldCampaignFunnelRow]:
    try:
        return get_campaign_funnel_rows(sdk_key=sdk_key)
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
