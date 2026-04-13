from typing import Any, List, Optional

from pydantic import BaseModel, Field, validator


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
    sdk_key: str = Field(..., description="Issued SDK key")
    events: List[Event]

    @validator("sdk_key")
    def validate_sdk_key(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("sdk_key is required")
        return v

    @validator("events")
    def validate_events(cls, v: List[Event]) -> List[Event]:
        if not v:
            raise ValueError("events must contain at least one item")
        return v


class CollectResponse(BaseModel):
    success: bool
    received_events: int


class HealthResponse(BaseModel):
    status: str = "ok"
