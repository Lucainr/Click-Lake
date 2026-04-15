from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from .schemas import Event


def append_raw_events_jsonl(
    sdk_key: str,
    events: Iterable[Event],
    file_path: Path,
) -> int:
    file_path.parent.mkdir(parents=True, exist_ok=True)

    received_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    count = 0

    with file_path.open("a", encoding="utf-8") as f:
        for event in events:
            record = {
                "received_at": received_at,
                "sdk_key": sdk_key,
                "event": event.dict(),
            }
            f.write(
                json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n"
            )
            count += 1

    return count
