from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Iterable

from .schemas import Event

FILE_PATTERN = re.compile(r"^events-(\d{4})\.jsonl$")


@dataclass
class StoreResult:
    stored_count: int
    stored_dir_abs: Path
    stored_dir_rel: str


def _line_count(file_path: Path) -> int:
    if not file_path.exists():
        return 0
    with file_path.open("r", encoding="utf-8") as f:
        return sum(1 for _ in f)


def _list_event_files(partition_dir: Path) -> list[tuple[int, Path]]:
    files: list[tuple[int, Path]] = []
    if not partition_dir.exists():
        return files

    for path in partition_dir.iterdir():
        if not path.is_file():
            continue
        match = FILE_PATTERN.match(path.name)
        if not match:
            continue
        files.append((int(match.group(1)), path))
    files.sort(key=lambda item: item[0])
    return files


def _event_file_path(partition_dir: Path, seq: int) -> Path:
    return partition_dir / f"events-{seq:04d}.jsonl"


def _today_partition_dir(base_dir: Path) -> tuple[Path, str]:
    today = date.today().isoformat()
    rel_dir = f"date={today}"
    return base_dir / rel_dir, rel_dir


def append_raw_events_partitioned(
    sdk_key: str,
    events: Iterable[Event],
    base_dir: Path,
    base_rel_dir: str,
    max_events_per_file: int,
) -> StoreResult:
    if max_events_per_file <= 0:
        raise ValueError("max_events_per_file must be greater than zero")

    partition_dir, partition_rel_dir = _today_partition_dir(base_dir)
    partition_dir.mkdir(parents=True, exist_ok=True)

    received_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    event_files = _list_event_files(partition_dir)
    if event_files:
        current_seq, current_file = event_files[-1]
        current_count = _line_count(current_file)
    else:
        current_seq = 1
        current_file = _event_file_path(partition_dir, current_seq)
        current_count = 0

    stored_count = 0
    writer = current_file.open("a", encoding="utf-8")
    try:
        for event in events:
            if current_count >= max_events_per_file:
                writer.close()
                current_seq += 1
                current_file = _event_file_path(partition_dir, current_seq)
                writer = current_file.open("a", encoding="utf-8")
                current_count = 0

            record = {
                "received_at": received_at,
                "sdk_key": sdk_key,
                "event": event.dict(exclude_unset=True),
            }
            writer.write(
                json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n"
            )
            current_count += 1
            stored_count += 1
    finally:
        writer.close()

    return StoreResult(
        stored_count=stored_count,
        stored_dir_abs=partition_dir,
        stored_dir_rel=f"{base_rel_dir}/{partition_rel_dir}",
    )
