from __future__ import annotations

import json
import logging
import os
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger("clicklake.consumer")

# replica마다 고유한 파일 prefix → 동일 디렉토리에 동시 write해도 충돌 없음
_INSTANCE_ID = os.getenv("KAFKA_CONSUMER_INSTANCE_ID", "").strip()


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _file_prefix(base_prefix: str) -> str:
    if _INSTANCE_ID:
        return f"{base_prefix}-{_INSTANCE_ID}"
    return base_prefix


class Sink(ABC):
    @abstractmethod
    def write(self, partition_date: str, record: dict[str, Any]) -> Path:
        ...

    def close(self) -> None:
        pass


class JsonlSink(Sink):
    """날짜 파티션 기반 JSONL 파일 Sink. 인스턴스별 상태를 내부에서 관리."""

    def __init__(
        self,
        base_dir: Path,
        file_prefix: str,
        max_events_per_file: int,
        sink_name: str,
    ) -> None:
        self._base_dir = base_dir
        self._file_prefix = _file_prefix(file_prefix)
        self._max_events = max_events_per_file
        self._sink_name = sink_name
        self._state: dict[str, tuple[Path, int, int]] = {}

    def _extract_index(self, file_path: Path) -> int:
        return int(file_path.stem.split("-")[-1])

    def _count_lines(self, file_path: Path) -> int:
        if not file_path.exists():
            return 0
        with file_path.open("r", encoding="utf-8") as f:
            return sum(1 for _ in f)

    def _resolve_active_file(self, partition_date: str) -> tuple[Path, int, int]:
        cached = self._state.get(partition_date)
        if cached is not None:
            return cached

        target_dir = self._base_dir / f"date={partition_date}"
        target_dir.mkdir(parents=True, exist_ok=True)

        files = sorted(target_dir.glob(f"{self._file_prefix}-*.jsonl"))
        if not files:
            active_file = target_dir / f"{self._file_prefix}-0001.jsonl"
            state = (active_file, 1, 0)
        else:
            last_file = files[-1]
            current_index = self._extract_index(last_file)
            current_count = self._count_lines(last_file)
            if current_count >= self._max_events:
                current_index += 1
                last_file = target_dir / f"{self._file_prefix}-{current_index:04d}.jsonl"
                current_count = 0
            state = (last_file, current_index, current_count)

        self._state[partition_date] = state
        return state

    def write(self, partition_date: str, record: dict[str, Any]) -> Path:
        active_file, file_index, line_count = self._resolve_active_file(partition_date)

        if line_count >= self._max_events:
            file_index += 1
            active_file = (
                self._base_dir
                / f"date={partition_date}"
                / f"{self._file_prefix}-{file_index:04d}.jsonl"
            )
            line_count = 0
            logger.info(
                "%s file rollover date=%s next_file=%s",
                self._sink_name,
                partition_date,
                str(active_file),
            )

        with active_file.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False))
            handle.write("\n")

        self._state[partition_date] = (active_file, file_index, line_count + 1)
        return active_file


class DlqSink:
    """처리 실패 메시지를 날짜별 JSONL 파일로 기록."""

    def __init__(self, dlq_dir: Path) -> None:
        self._dlq_dir = dlq_dir
        self._dlq_dir.mkdir(parents=True, exist_ok=True)

    def write(
        self,
        *,
        topic: str,
        partition: int,
        offset: int,
        payload: Any,
        reason: str,
    ) -> None:
        date_str = datetime.now(timezone.utc).date().isoformat()
        prefix = _file_prefix("dlq")
        dlq_file = self._dlq_dir / f"{prefix}-{date_str}.jsonl"
        record = {
            "failed_at": _utc_now_iso(),
            "topic": topic,
            "partition": partition,
            "offset": offset,
            "reason": reason,
            "payload": payload,
        }
        with dlq_file.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False))
            handle.write("\n")
        logger.warning(
            "dlq record written topic=%s partition=%d offset=%d file=%s reason=%s",
            topic,
            partition,
            offset,
            str(dlq_file),
            reason,
        )
