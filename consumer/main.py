import json
import logging
import os
import signal
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
SINK_DIR = Path(os.getenv("KAFKA_SINK_DIR", "/data/raw_events_kafka"))
MAX_EVENTS_PER_FILE = max(1, int(os.getenv("SINK_MAX_EVENTS_PER_FILE", "1000")))

_running = True
_file_state: dict[str, tuple[Path, int, int]] = {}


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


def _date_dir(partition_date: str) -> Path:
    return SINK_DIR / f"date={partition_date}"


def _count_lines(file_path: Path) -> int:
    line_count = 0
    with file_path.open("r", encoding="utf-8") as handle:
        for _ in handle:
            line_count += 1
    return line_count


def _extract_index(file_path: Path) -> int:
    file_stem = file_path.stem
    # expected: events-0001
    suffix = file_stem.split("-")[-1]
    return int(suffix)


def _resolve_active_file(partition_date: str) -> tuple[Path, int, int]:
    cached = _file_state.get(partition_date)
    if cached is not None:
        return cached

    target_dir = _date_dir(partition_date)
    target_dir.mkdir(parents=True, exist_ok=True)

    files = sorted(target_dir.glob("events-*.jsonl"))
    if not files:
        active_file = target_dir / "events-0001.jsonl"
        state = (active_file, 1, 0)
        _file_state[partition_date] = state
        return state

    last_file = files[-1]
    current_index = _extract_index(last_file)
    current_count = _count_lines(last_file)

    if current_count >= MAX_EVENTS_PER_FILE:
        current_index += 1
        last_file = target_dir / f"events-{current_index:04d}.jsonl"
        current_count = 0

    state = (last_file, current_index, current_count)
    _file_state[partition_date] = state
    return state


def _append_record(partition_date: str, record: dict[str, Any]) -> Path:
    active_file, file_index, line_count = _resolve_active_file(partition_date)
    if line_count >= MAX_EVENTS_PER_FILE:
        file_index += 1
        active_file = _date_dir(partition_date) / f"events-{file_index:04d}.jsonl"
        line_count = 0

    with active_file.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False))
        handle.write("\n")

    _file_state[partition_date] = (active_file, file_index, line_count + 1)
    return active_file


def _normalize_records(payload: dict[str, Any]) -> tuple[str, list[dict[str, Any]]]:
    partition_date = _extract_partition_date(payload)
    received_at = str(payload.get("received_at") or "").strip() or _utc_now_iso()
    sdk_key = str(payload.get("sdk_key") or "").strip()
    events = payload.get("events")

    if not sdk_key:
        raise ValueError("missing sdk_key")
    if not isinstance(events, list) or not events:
        raise ValueError("events must be a non-empty array")

    records: list[dict[str, Any]] = []
    for event in events:
        if not isinstance(event, dict):
            continue
        records.append(
            {
                "received_at": received_at,
                "sdk_key": sdk_key,
                "event": event,
            }
        )

    if not records:
        raise ValueError("events array contains no valid event object")
    return partition_date, records


def _process_payload(payload: dict[str, Any]) -> int:
    partition_date, records = _normalize_records(payload)
    for record in records:
        sink_path = _append_record(partition_date, record)
    logger.info(
        "sink write success date=%s records=%d file=%s",
        partition_date,
        len(records),
        sink_path,
    )
    return len(records)


def main() -> None:
    global _running

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    SINK_DIR.mkdir(parents=True, exist_ok=True)

    logger.info(
        "consumer start bootstrap_servers=%s topic=%s group=%s sink_dir=%s",
        BOOTSTRAP_SERVERS,
        TOPIC,
        GROUP_ID,
        str(SINK_DIR),
    )

    consumer = KafkaConsumer(
        TOPIC,
        bootstrap_servers=[server.strip() for server in BOOTSTRAP_SERVERS.split(",") if server.strip()],
        group_id=GROUP_ID,
        auto_offset_reset=AUTO_OFFSET_RESET,
        enable_auto_commit=False,
        value_deserializer=lambda value: json.loads(value.decode("utf-8")),
        consumer_timeout_ms=1000,
    )
    logger.info("topic subscribed: %s", TOPIC)

    consumed_messages = 0
    sink_records = 0

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
                        sink_records += _process_payload(payload)
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
            "consumer stopped consumed_messages=%d sink_records=%d",
            consumed_messages,
            sink_records,
        )


if __name__ == "__main__":
    main()
