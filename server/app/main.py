import logging

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .schemas import CollectRequest, CollectResponse, HealthResponse
from .config import settings
from .errors import ApiError
from .services.gold_data import get_dashboard_rows
from .services.kafka_producer import (
    close_kafka_producer,
    init_kafka_producer,
    publish_collect_payload,
)
from .storage import append_raw_events_partitioned
from .routes.gold import router as gold_router

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

app.include_router(gold_router)


@app.on_event("startup")
async def warmup_gold_cache() -> None:
    init_kafka_producer()

    if not settings.gold_warmup_on_startup:
        logger.info("gold warmup skipped (gold_warmup_on_startup=false)")
        return

    try:
        get_dashboard_rows(sdk_key=None)
        logger.info("gold dashboard cache warmup completed")
    except ApiError as exc:
        logger.warning(
            "gold dashboard warmup failed: %s (%s)",
            exc.error_code,
            exc.details or exc.message,
        )
    except Exception as exc:  # pragma: no cover - defensive log path
        logger.warning("gold dashboard warmup failed: %s", str(exc))


@app.on_event("shutdown")
async def shutdown_producer() -> None:
    close_kafka_producer()


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
        store_result = append_raw_events_partitioned(
            sdk_key=payload.sdk_key,
            events=payload.events,
            base_dir=settings.raw_events_base_abs_dir,
            base_rel_dir=settings.raw_events_base_rel_dir,
            max_events_per_file=settings.max_events_per_file,
        )
    except OSError as exc:
        logger.exception("failed to store raw events")
        raise HTTPException(status_code=500, detail="failed to store raw events") from exc
    except ValueError as exc:
        logger.exception("invalid storage configuration")
        raise HTTPException(status_code=500, detail="invalid storage configuration") from exc

    kafka_events = [event.dict(exclude_none=True) for event in payload.events]
    publish_collect_payload(sdk_key=payload.sdk_key.strip(), events=kafka_events)

    return CollectResponse(
        success=True,
        received_events=store_result.stored_count,
        stored_dir=store_result.stored_dir_rel,
    )
