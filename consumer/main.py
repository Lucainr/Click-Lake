import json
import logging
import os
import signal
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from kafka import KafkaConsumer

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
logger = logging.getLogger("clicklake.consumer")

BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092")
TOPIC = os.getenv("KAFKA_TOPIC_RAW_EVENTS", "clicklake.events.raw")
GROUP_ID = os.getenv("KAFKA_CONSUMER_GROUP", "clicklake-consumer")
AUTO_OFFSET_RESET = os.getenv("KAFKA_AUTO_OFFSET_RESET", "latest")

ENABLE_RAW_SINK = os.getenv("KAFKA_ENABLE_RAW_SINK", "true").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}
RAW_SINK_DIR = Path(os.getenv("KAFKA_SINK_DIR", "/data/raw_events_kafka"))
RAW_MAX_EVENTS_PER_FILE = max(1, int(os.getenv("SINK_MAX_EVENTS_PER_FILE", "1000")))

ENABLE_BRONZE_DIRECT = os.getenv("KAFKA_ENABLE_BRONZE_DIRECT", "true").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}
BRONZE_SINK_DIR = Path(os.getenv("KAFKA_BRONZE_SINK_DIR", "/data/bronze_batches_kafka"))
BRONZE_MAX_EVENTS_PER_FILE = max(
    1, int(os.getenv("KAFKA_BRONZE_MAX_EVENTS_PER_FILE", "1000"))
)

_running = True
_raw_file_state: dict[str, tuple[Path, int, int]] = {}
_bronze_file_state: dict[str, tuple[Path, int, int]] = {}
_bronze_batch_id: str = ""
_bronze_loaded_at: str = ""


def _handle_signal(signum: int, _frame: Any) -> None:
    global _running
    logger.info("shutdown signal received: %s", signum)
    _running = False


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _extract_partition_date(payload: dict[str, Any]) -> str:
    raw_received_at = str(payload.get("received_at") or "").strip()
    if raw_received_at:
        try:
            normalized = raw_received_at.replace("Z", "+00:00")
            parsed = datetime.fromisoformat(normalized)
            return parsed.date().isoformat()
        except ValueError:
            pass
    return datetime.now(timezone.utc).date().isoformat()


def _extract_index(file_path: Path) -> int:
    file_stem = file_path.stem
    suffix = file_stem.split("-")[-1]
    return int(suffix)


def _count_lines(file_path: Path) -> int:
    line_count = 0
    with file_path.open("r", encoding="utf-8") as handle:
        for _ in handle:
            line_count += 1
    return line_count


def _resolve_active_file(
    partition_date: str,
    base_dir: Path,
    file_prefix: str,
    max_events_per_file: int,
    state_map: dict[str, tuple[Path, int, int]],
) -> tuple[Path, int, int]:
    cached = state_map.get(partition_date)
    if cached is not None:
        return cached

    target_dir = base_dir / f"date={partition_date}"
    target_dir.mkdir(parents=True, exist_ok=True)

    files = sorted(target_dir.glob(f"{file_prefix}-*.jsonl"))
    if not files:
        active_file = target_dir / f"{file_prefix}-0001.jsonl"
        state = (active_file, 1, 0)
        state_map[partition_date] = state
        return state

    last_file = files[-1]
    current_index = _extract_index(last_file)
    current_count = _count_lines(last_file)

    if current_count >= max_events_per_file:
        current_index += 1
        last_file = target_dir / f"{file_prefix}-{current_index:04d}.jsonl"
        current_count = 0

    state = (last_file, current_index, current_count)
    state_map[partition_date] = state
    return state


def _append_jsonl_record(
    partition_date: str,
    record: dict[str, Any],
    *,
    base_dir: Path,
    file_prefix: str,
    max_events_per_file: int,
    state_map: dict[str, tuple[Path, int, int]],
    sink_name: str,
) -> Path:
    active_file, file_index, line_count = _resolve_active_file(
        partition_date=partition_date,
        base_dir=base_dir,
        file_prefix=file_prefix,
        max_events_per_file=max_events_per_file,
        state_map=state_map,
    )
    if line_count >= max_events_per_file:
        file_index += 1
        active_file = base_dir / f"date={partition_date}" / f"{file_prefix}-{file_index:04d}.jsonl"
        line_count = 0
        logger.info(
            "%s file rollover date=%s next_file=%s",
            sink_name,
            partition_date,
            str(active_file),
        )

    with active_file.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False))
        handle.write("\n")

    state_map[partition_date] = (active_file, file_index, line_count + 1)
    return active_file


def _normalize_records(payload: dict[str, Any]) -> tuple[str, str, str, list[dict[str, Any]]]:
    partition_date = _extract_partition_date(payload)
    received_at = str(payload.get("received_at") or "").strip() or _utc_now_iso()
    sdk_key = str(payload.get("sdk_key") or "").strip()
    events = payload.get("events")

    if not sdk_key:
        raise ValueError("missing sdk_key")
    if not isinstance(events, list) or not events:
        raise ValueError("events must be a non-empty array")

    valid_events: list[dict[str, Any]] = []
    for event in events:
        if isinstance(event, dict):
            valid_events.append(event)
    if not valid_events:
        raise ValueError("events array contains no valid event object")

    return partition_date, received_at, sdk_key, valid_events


def _to_raw_sink_record(received_at: str, sdk_key: str, event: dict[str, Any]) -> dict[str, Any]:
    return {
        "received_at": received_at,
        "sdk_key": sdk_key,
        "event": event,
    }


def _to_bronze_record(
    *,
    received_at: str,
    sdk_key: str,
    event: dict[str, Any],
    source_file: str,
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
        "exported_at": _bronze_loaded_at,
        "export_batch_id": _bronze_batch_id,
        "source_file": source_file,
        "ingestion_source": "kafka_consumer_direct",
        "loaded_at": _bronze_loaded_at,
    }


def _process_payload(payload: dict[str, Any], *, source_file: str) -> tuple[int, int]:
    partition_date, received_at, sdk_key, events = _normalize_records(payload)
    raw_written = 0
    bronze_written = 0

    if ENABLE_RAW_SINK:
        for event in events:
            raw_record = _to_raw_sink_record(received_at, sdk_key, event)
            raw_sink_path = _append_jsonl_record(
                partition_date,
                raw_record,
                base_dir=RAW_SINK_DIR,
                file_prefix="events",
                max_events_per_file=RAW_MAX_EVENTS_PER_FILE,
                state_map=_raw_file_state,
                sink_name="raw sink",
            )
            raw_written += 1
        logger.info(
            "raw sink write success date=%s records=%d file=%s",
            partition_date,
            raw_written,
            str(raw_sink_path),
        )

    if ENABLE_BRONZE_DIRECT:
        for event in events:
            bronze_record = _to_bronze_record(
                received_at=received_at,
                sdk_key=sdk_key,
                event=event,
                source_file=source_file,
            )
            bronze_sink_path = _append_jsonl_record(
                partition_date,
                bronze_record,
                base_dir=BRONZE_SINK_DIR,
                file_prefix="bronze_events",
                max_events_per_file=BRONZE_MAX_EVENTS_PER_FILE,
                state_map=_bronze_file_state,
                sink_name="bronze direct sink",
            )
            bronze_written += 1
        logger.info(
            "bronze direct write success date=%s records=%d file=%s",
            partition_date,
            bronze_written,
            str(bronze_sink_path),
        )

    return raw_written, bronze_written


def main() -> None:
    global _running, _bronze_batch_id, _bronze_loaded_at

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    if ENABLE_RAW_SINK:
        RAW_SINK_DIR.mkdir(parents=True, exist_ok=True)
    if ENABLE_BRONZE_DIRECT:
        BRONZE_SINK_DIR.mkdir(parents=True, exist_ok=True)

    if not ENABLE_RAW_SINK and not ENABLE_BRONZE_DIRECT:
        logger.warning("both sinks disabled; consumer will only commit offsets")

    _bronze_batch_id = (
        f"kafka_bronze_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}_{uuid.uuid4().hex[:8]}"
    )
    _bronze_loaded_at = _utc_now_iso()

    logger.info(
        (
            "consumer start bootstrap_servers=%s topic=%s group=%s "
            "raw_sink_enabled=%s bronze_direct_enabled=%s raw_sink_dir=%s bronze_sink_dir=%s"
        ),
        BOOTSTRAP_SERVERS,
        TOPIC,
        GROUP_ID,
        ENABLE_RAW_SINK,
        ENABLE_BRONZE_DIRECT,
        str(RAW_SINK_DIR),
        str(BRONZE_SINK_DIR),
    )

    consumer = KafkaConsumer(
        TOPIC,
        bootstrap_servers=[
            server.strip() for server in BOOTSTRAP_SERVERS.split(",") if server.strip()
        ],
        group_id=GROUP_ID,
        auto_offset_reset=AUTO_OFFSET_RESET,
        enable_auto_commit=False,
        value_deserializer=lambda value: json.loads(value.decode("utf-8")),
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
                        message.topic,
                        message.partition,
                        message.offset,
                    )

                    try:
                        if not isinstance(payload, dict):
                            raise ValueError("payload must be object")
                        source_file = (
                            f"kafka://{message.topic}/partition={message.partition}/offset={message.offset}"
                        )
                        raw_written, bronze_written = _process_payload(
                            payload, source_file=source_file
                        )
                        raw_sink_records += raw_written
                        bronze_sink_records += bronze_written
                        consumer.commit()
                    except Exception as exc:
                        logger.warning(
                            "sink write failed topic=%s partition=%d offset=%d reason=%s",
                            message.topic,
                            message.partition,
                            message.offset,
                            str(exc),
                        )
                        # skip poison-message to avoid infinite retry loop in MVP stage
                        consumer.commit()
    finally:
        consumer.close()
        logger.info(
            (
                "consumer stopped consumed_messages=%d raw_sink_records=%d "
                "bronze_sink_records=%d bronze_batch_id=%s"
            ),
            consumed_messages,
            raw_sink_records,
            bronze_sink_records,
            _bronze_batch_id,
        )


if __name__ == "__main__":
    main()
