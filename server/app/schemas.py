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
    stored_path: str


class HealthResponse(BaseModel):
    status: str = "ok"
