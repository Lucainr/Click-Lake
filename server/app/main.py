import logging

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .schemas import CollectRequest, CollectResponse, HealthResponse
from .config import settings
from .storage import append_raw_events_jsonl

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
    if not payload.sdk_key or not payload.sdk_key.strip():
        raise HTTPException(status_code=400, detail="sdk_key is required")
    if not payload.events:
        raise HTTPException(
            status_code=400, detail="events must contain at least one item"
        )

    event_count = len(payload.events)

    logger.info("received sdk_key=%s events=%d", payload.sdk_key, event_count)
    logger.debug("payload=%s", payload.json())

    try:
        stored_count = append_raw_events_jsonl(
            sdk_key=payload.sdk_key,
            events=payload.events,
            file_path=settings.raw_events_abs_path,
        )
    except OSError as exc:
        logger.exception("failed to store raw events")
        raise HTTPException(status_code=500, detail="failed to store raw events") from exc

    return CollectResponse(
        success=True,
        received_events=stored_count,
        stored_path=settings.raw_events_rel_path,
    )
