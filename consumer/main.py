import json
import logging
import os
import signal
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from kafka import KafkaConsumer

from sinks import DlqSink, JsonlSink, _utc_now_iso

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
logger = logging.getLogger("clicklake.consumer")

BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092")
TOPIC = os.getenv("KAFKA_TOPIC_RAW_EVENTS", "clicklake.events.raw")
GROUP_ID = os.getenv("KAFKA_CONSUMER_GROUP", "clicklake-consumer")
AUTO_OFFSET_RESET = os.getenv("KAFKA_AUTO_OFFSET_RESET", "latest")

ENABLE_RAW_SINK = os.getenv("KAFKA_ENABLE_RAW_SINK", "true").strip().lower() in {
    "1", "true", "yes", "on",
}
RAW_SINK_DIR = Path(os.getenv("KAFKA_SINK_DIR", "/data/raw_events_kafka"))
RAW_MAX_EVENTS_PER_FILE = max(1, int(os.getenv("SINK_MAX_EVENTS_PER_FILE", "1000")))

ENABLE_BRONZE_DIRECT = os.getenv("KAFKA_ENABLE_BRONZE_DIRECT", "true").strip().lower() in {
    "1", "true", "yes", "on",
}
BRONZE_SINK_DIR = Path(os.getenv("KAFKA_BRONZE_SINK_DIR", "/data/bronze_batches_kafka"))
BRONZE_MAX_EVENTS_PER_FILE = max(1, int(os.getenv("KAFKA_BRONZE_MAX_EVENTS_PER_FILE", "1000")))

DLQ_DIR = Path(os.getenv("KAFKA_DLQ_DIR", "/data/dlq"))

_running = True


def _handle_signal(signum: int, _frame: Any) -> None:
    global _running
    logger.info("shutdown signal received: %s", signum)
    _running = False


def _extract_partition_date(payload: dict[str, Any]) -> str:
    raw_received_at = str(payload.get("received_at") or "").strip()
    if raw_received_at:
        try:
            parsed = datetime.fromisoformat(raw_received_at.replace("Z", "+00:00"))
            return parsed.date().isoformat()
        except ValueError:
            pass
    return datetime.now(timezone.utc).date().isoformat()


def _normalize_records(
    payload: dict[str, Any],
) -> tuple[str, str, str, list[dict[str, Any]]]:
    partition_date = _extract_partition_date(payload)
    received_at = str(payload.get("received_at") or "").strip() or _utc_now_iso()
    sdk_key = str(payload.get("sdk_key") or "").strip()
    events = payload.get("events")

    if not sdk_key:
        raise ValueError("missing sdk_key")
    if not isinstance(events, list) or not events:
        raise ValueError("events must be a non-empty array")

    valid_events = [e for e in events if isinstance(e, dict)]
    if not valid_events:
        raise ValueError("events array contains no valid event object")

    return partition_date, received_at, sdk_key, valid_events


def _to_raw_sink_record(
    received_at: str, sdk_key: str, event: dict[str, Any]
) -> dict[str, Any]:
    return {"received_at": received_at, "sdk_key": sdk_key, "event": event}


def _to_bronze_record(
    *,
    received_at: str,
    sdk_key: str,
    event: dict[str, Any],
    source_file: str,
    batch_id: str,
    loaded_at: str,
) -> dict[str, Any]:
    return {
        "received_at": received_at,
        "sdk_key": sdk_key,
        "event_id": event.get("event_id"),
        "event_type": event.get("event_type"),
        "event_time": event.get("event_time"),
        "session_id": event.get("session_id"),
        "page_url": event.get("page_url"),
        "raw_event_json": json.dumps(event, ensure_ascii=False, separators=(",", ":")),
        "exported_at": loaded_at,
        "export_batch_id": batch_id,
        "source_file": source_file,
        "ingestion_source": "kafka_consumer_direct",
        "loaded_at": loaded_at,
    }


def _process_payload(
    payload: dict[str, Any],
    *,
    source_file: str,
    raw_sink: JsonlSink | None,
    bronze_sink: JsonlSink | None,
    batch_id: str,
    loaded_at: str,
) -> tuple[int, int]:
    partition_date, received_at, sdk_key, events = _normalize_records(payload)
    raw_written = 0
    bronze_written = 0

    if raw_sink is not None:
        for event in events:
            raw_sink_path = raw_sink.write(
                partition_date, _to_raw_sink_record(received_at, sdk_key, event)
            )
            raw_written += 1
        logger.info(
            "raw sink write success date=%s records=%d file=%s",
            partition_date, raw_written, str(raw_sink_path),
        )

    if bronze_sink is not None:
        for event in events:
            bronze_sink_path = bronze_sink.write(
                partition_date,
                _to_bronze_record(
                    received_at=received_at,
                    sdk_key=sdk_key,
                    event=event,
                    source_file=source_file,
                    batch_id=batch_id,
                    loaded_at=loaded_at,
                ),
            )
            bronze_written += 1
        logger.info(
            "bronze direct write success date=%s records=%d file=%s",
            partition_date, bronze_written, str(bronze_sink_path),
        )

    return raw_written, bronze_written


def main() -> None:
    global _running

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    raw_sink: JsonlSink | None = None
    if ENABLE_RAW_SINK:
        RAW_SINK_DIR.mkdir(parents=True, exist_ok=True)
        raw_sink = JsonlSink(
            base_dir=RAW_SINK_DIR,
            file_prefix="events",
            max_events_per_file=RAW_MAX_EVENTS_PER_FILE,
            sink_name="raw sink",
        )

    bronze_sink: JsonlSink | None = None
    if ENABLE_BRONZE_DIRECT:
        BRONZE_SINK_DIR.mkdir(parents=True, exist_ok=True)
        bronze_sink = JsonlSink(
            base_dir=BRONZE_SINK_DIR,
            file_prefix="bronze_events",
            max_events_per_file=BRONZE_MAX_EVENTS_PER_FILE,
            sink_name="bronze direct sink",
        )

    dlq_sink = DlqSink(DLQ_DIR)

    if raw_sink is None and bronze_sink is None:
        logger.warning("both sinks disabled; consumer will only commit offsets")

    batch_id = (
        f"kafka_bronze_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}_{uuid.uuid4().hex[:8]}"
    )
    loaded_at = _utc_now_iso()

    logger.info(
        "consumer start bootstrap_servers=%s topic=%s group=%s "
        "raw_sink_enabled=%s bronze_direct_enabled=%s raw_sink_dir=%s bronze_sink_dir=%s",
        BOOTSTRAP_SERVERS, TOPIC, GROUP_ID,
        ENABLE_RAW_SINK, ENABLE_BRONZE_DIRECT,
        str(RAW_SINK_DIR), str(BRONZE_SINK_DIR),
    )

    consumer = KafkaConsumer(
        TOPIC,
        bootstrap_servers=[s.strip() for s in BOOTSTRAP_SERVERS.split(",") if s.strip()],
        group_id=GROUP_ID,
        auto_offset_reset=AUTO_OFFSET_RESET,
        enable_auto_commit=False,
        value_deserializer=lambda v: json.loads(v.decode("utf-8")),
        consumer_timeout_ms=1000,
    )
    logger.info("topic subscribed: %s", TOPIC)

    consumed_messages = 0
    raw_sink_records = 0
    bronze_sink_records = 0

    try:
        while _running:
            polled = consumer.poll(timeout_ms=1000, max_records=20)
            if not polled:
                continue

            for _topic_partition, messages in polled.items():
                for message in messages:
                    consumed_messages += 1
                    payload = message.value
                    logger.info(
                        "message consumed topic=%s partition=%d offset=%d",
                        message.topic, message.partition, message.offset,
                    )

                    try:
                        if not isinstance(payload, dict):
                            raise ValueError("payload must be object")
                        source_file = (
                            f"kafka://{message.topic}"
                            f"/partition={message.partition}"
                            f"/offset={message.offset}"
                        )
                        raw_written, bronze_written = _process_payload(
                            payload,
                            source_file=source_file,
                            raw_sink=raw_sink,
                            bronze_sink=bronze_sink,
                            batch_id=batch_id,
                            loaded_at=loaded_at,
                        )
                        raw_sink_records += raw_written
                        bronze_sink_records += bronze_written
                        consumer.commit()
                    except Exception as exc:
                        logger.warning(
                            "sink write failed topic=%s partition=%d offset=%d reason=%s",
                            message.topic, message.partition, message.offset, str(exc),
                        )
                        try:
                            dlq_sink.write(
                                topic=message.topic,
                                partition=message.partition,
                                offset=message.offset,
                                payload=message.value,
                                reason=str(exc),
                            )
                        except Exception as dlq_exc:
                            logger.error(
                                "dlq write also failed topic=%s partition=%d offset=%d reason=%s",
                                message.topic, message.partition, message.offset, str(dlq_exc),
                            )
                        consumer.commit()
    finally:
        consumer.close()
        logger.info(
            "consumer stopped consumed_messages=%d raw_sink_records=%d "
            "bronze_sink_records=%d batch_id=%s",
            consumed_messages, raw_sink_records, bronze_sink_records, batch_id,
        )


if __name__ == "__main__":
    main()
