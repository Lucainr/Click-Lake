from typing import List, Optional

from pydantic import BaseModel


class Event(BaseModel):
    event_id: Optional[str] = None
    event_type: Optional[str] = None
    event_time: Optional[str] = None
    session_id: Optional[str] = None
    page_url: Optional[str] = None
    # allow extra keys by default to keep payload flexible
    class Config:
        extra = "allow"


class CollectRequest(BaseModel):
    sdk_key: Optional[str] = None
    events: Optional[List[Event]] = None


class CollectResponse(BaseModel):
    success: bool
    received_events: int
    stored_dir: str


class HealthResponse(BaseModel):
    status: str = "ok"


class GoldHealthRow(BaseModel):
    event_date: str
    sdk_key: str
    raw_event_count: int
    valid_event_count: int
    invalid_event_count: int
    invalid_event_ratio: float
    distinct_sessions: int
    latest_event_time: str
    freshness_minutes: Optional[int] = None


class GoldPromotionPerformanceRow(BaseModel):
    event_date: str
    sdk_key: str
    campaign_id: str
    campaign_name: Optional[str] = None
    promotion_id: str
    promotion_name: Optional[str] = None
    placement: Optional[str] = None
    promotion_views: int
    promotion_clicks: int
    ctr: float
    product_views_after_click: int
    add_to_cart_after_click: int
    product_view_rate_after_click: float
    add_to_cart_rate_after_click: float


class GoldCampaignFunnelRow(BaseModel):
    event_date: str
    sdk_key: str
    campaign_id: str
    campaign_name: str
    promotion_view_sessions: int
    promotion_click_sessions: int
    product_view_sessions: int
    add_to_cart_sessions: int
    view_to_click_rate: float
    click_to_product_view_rate: float
    click_to_add_to_cart_rate: float
