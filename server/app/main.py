from typing import Any
import logging

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .schemas import CollectRequest, CollectResponse, HealthResponse
from .config import settings

logger = logging.getLogger("clicklake.collector")
logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")

app = FastAPI(title=settings.app_name)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse()


@app.post("/collect", response_model=CollectResponse)
async def collect(payload: CollectRequest) -> CollectResponse:
    # sdk_key 및 events는 Pydantic validator에서 검증됨
    event_count = len(payload.events)

    # 간단한 수신 로그 (필요 시 추후 Kafka/DB 연동 지점)
    logger.info(
        "received sdk_key=%s events=%d", payload.sdk_key, event_count
    )
    logger.debug("payload=%s", payload.json())

    return CollectResponse(success=True, received_events=event_count)
