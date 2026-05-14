import json
import logging
from datetime import datetime, timezone
from typing import Any

from ..config import settings

logger = logging.getLogger("clicklake.kafka")

_producer: Any | None = None
_disabled_reason: str | None = None


def _is_enabled() -> bool:
    return settings.kafka_enabled


def _bootstrap_servers() -> list[str]:
    raw = (settings.kafka_bootstrap_servers or "").strip()
    if not raw:
        return []
    return [server.strip() for server in raw.split(",") if server.strip()]


def _build_message(sdk_key: str, events: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "received_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "sdk_key": sdk_key,
        "events": events,
    }


def _create_producer() -> Any | None:
    global _disabled_reason

    if not _is_enabled():
        _disabled_reason = "KAFKA_ENABLED is false"
        logger.info("kafka producer disabled: %s", _disabled_reason)
        return None

    servers = _bootstrap_servers()
    if not servers:
        _disabled_reason = "KAFKA_BOOTSTRAP_SERVERS is empty"
        logger.info("kafka producer disabled: %s", _disabled_reason)
        return None

    try:
        from kafka import KafkaProducer
    except ImportError:
        _disabled_reason = "kafka-python dependency is missing"
        logger.warning("kafka producer init failed: %s", _disabled_reason)
        return None

    try:
        producer = KafkaProducer(
            bootstrap_servers=servers,
            client_id=settings.kafka_client_id,
            value_serializer=lambda value: json.dumps(
                value, ensure_ascii=False, separators=(",", ":")
            ).encode("utf-8"),
            acks="1",
            retries=1,
            linger_ms=20,
            request_timeout_ms=max(1000, int(settings.kafka_publish_timeout_seconds * 1000)),
        )
    except Exception as exc:
        _disabled_reason = str(exc)
        logger.warning("kafka producer init failed: %s", str(exc))
        return None

    _disabled_reason = None
    logger.info(
        "kafka producer initialized bootstrap_servers=%s topic=%s",
        ",".join(servers),
        settings.kafka_topic_raw_events,
    )
    return producer


def init_kafka_producer() -> None:
    global _producer
    if _producer is not None:
        return
    _producer = _create_producer()


def _ensure_producer() -> Any | None:
    global _producer
    if _producer is None:
        _producer = _create_producer()
    return _producer


def publish_collect_payload(sdk_key: str, events: list[dict[str, Any]]) -> bool:
    producer = _ensure_producer()
    if producer is None:
        if _disabled_reason:
            logger.debug("skip kafka publish: %s", _disabled_reason)
        return False

    topic = settings.kafka_topic_raw_events
    message = _build_message(sdk_key=sdk_key, events=events)

    try:
        future = producer.send(topic, value=message)
        metadata = future.get(timeout=settings.kafka_publish_timeout_seconds)
        logger.info(
            "kafka publish success topic=%s partition=%s offset=%s events=%d sdk_key=%s",
            topic,
            metadata.partition,
            metadata.offset,
            len(events),
            sdk_key,
        )
        return True
    except Exception as exc:
        logger.warning(
            "kafka publish failed topic=%s events=%d sdk_key=%s reason=%s",
            topic,
            len(events),
            sdk_key,
            str(exc),
        )
        _reset_producer()
        return False


def _reset_producer() -> None:
    global _producer
    if _producer is None:
        return
    try:
        _producer.close(timeout=1)
    except Exception:
        pass
    _producer = None


def close_kafka_producer() -> None:
    global _producer
    if _producer is None:
        return

    try:
        _producer.flush(timeout=settings.kafka_publish_timeout_seconds)
    except Exception:
        pass

    try:
        _producer.close(timeout=1)
    except Exception:
        pass

    _producer = None
    logger.info("kafka producer closed")
