from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DATE_DIR_PREFIX = "date="
FILE_RE = re.compile(r"^events-(\d{4})\.jsonl$")
SOURCE_DIRS = ("raw_events", "raw_events_kafka")
INGESTION_SOURCE_BY_ROOT = {
    "raw_events": "direct_raw",
    "raw_events_kafka": "kafka_consumer",
}


@dataclass(frozen=True)
class ExportPaths:
    raw_roots: dict[str, Path]
    checkpoint_file: Path
    out_dir: Path


@dataclass(frozen=True)
class ExportResult:
    export_file: Path | None
    export_batch_id: str | None
    processed_files: list[str]
    exported_rows: int


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _resolve_paths() -> ExportPaths:
    server_dir = Path(__file__).resolve().parents[1]
    return ExportPaths(
        raw_roots={name: server_dir / "data" / name for name in SOURCE_DIRS},
        checkpoint_file=server_dir / "data" / "checkpoints" / "bronze_export_state.json",
        out_dir=server_dir / "out" / "bronze_batches",
    )


def _load_checkpoint(path: Path) -> set[str]:
    if not path.exists():
        return set()

    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    files = data.get("processed_files", [])
    if not isinstance(files, list):
        raise ValueError("checkpoint processed_files must be a list")

    normalized: set[str] = set()
    for item in files:
        if not isinstance(item, str):
            raise ValueError("checkpoint processed_files items must be strings")
        if item.startswith("date=/") or item.startswith("date="):
            # backward compatibility: legacy key from raw_events-only era
            normalized.add(f"raw_events/{item}")
            continue
        normalized.add(item)
    return normalized


def _save_checkpoint(path: Path, processed_files: set[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"processed_files": sorted(processed_files)}

    temp = path.with_suffix(".tmp")
    with temp.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
        f.write("\n")
    temp.replace(path)


def _parse_partition_key(partition_relative_path: str) -> tuple[str, int, str]:
    rel = Path(partition_relative_path)
    if len(rel.parts) != 2:
        raise ValueError(f"invalid raw file relative path: {partition_relative_path}")

    date_part, file_part = rel.parts
    if not date_part.startswith(DATE_DIR_PREFIX):
        raise ValueError(f"invalid date partition directory: {date_part}")

    date_str = date_part[len(DATE_DIR_PREFIX) :]
    datetime.strptime(date_str, "%Y-%m-%d")

    file_match = FILE_RE.match(file_part)
    if not file_match:
        raise ValueError(f"invalid file name: {file_part}")

    seq = int(file_match.group(1))
    return (date_str, seq, partition_relative_path)


def _parse_sort_key(relative_path_with_source: str) -> tuple[str, str, int, str]:
    rel = Path(relative_path_with_source)
    if len(rel.parts) != 3:
        raise ValueError(f"invalid source relative path: {relative_path_with_source}")
    root_name, date_part, file_part = rel.parts
    _, seq, _ = _parse_partition_key(f"{date_part}/{file_part}")
    date_str = date_part[len(DATE_DIR_PREFIX) :]
    return (date_str, root_name, seq, relative_path_with_source)


def _discover_raw_files(raw_root: Path, root_name: str) -> list[str]:
    if not raw_root.exists():
        return []

    discovered: list[str] = []
    for path in raw_root.rglob("events-*.jsonl"):
        if not path.is_file():
            continue
        relative_partition = path.relative_to(raw_root).as_posix()
        # validate path shape + include only valid partitioned files
        _parse_partition_key(relative_partition)
        discovered.append(f"{root_name}/{relative_partition}")

    discovered.sort(key=_parse_sort_key)
    return discovered


def _parse_raw_line(raw_line: str, source_file: str, line_no: int) -> dict[str, Any]:
    try:
        item = json.loads(raw_line)
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid json in {source_file}:{line_no}") from exc

    if not isinstance(item, dict):
        raise ValueError(f"invalid record type in {source_file}:{line_no}")

    event = item.get("event")
    if not isinstance(event, dict):
        raise ValueError(f"missing event object in {source_file}:{line_no}")

    return item


def _build_bronze_record(
    raw_record: dict[str, Any],
    source_file: str,
    ingestion_source: str,
    export_batch_id: str,
    exported_at: str,
) -> dict[str, Any]:
    event = raw_record.get("event", {})
    if not isinstance(event, dict):
        event = {}

    return {
        "received_at": raw_record.get("received_at"),
        "sdk_key": raw_record.get("sdk_key"),
        "event_id": event.get("event_id"),
        "event_type": event.get("event_type"),
        "event_time": event.get("event_time"),
        "session_id": event.get("session_id"),
        "page_url": event.get("page_url"),
        "raw_event_json": json.dumps(event, ensure_ascii=False, separators=(",", ":")),
        "exported_at": exported_at,
        "export_batch_id": export_batch_id,
        "source_file": source_file,
        "ingestion_source": ingestion_source,
        "loaded_at": exported_at,
    }


def export_raw_to_bronze() -> ExportResult:
    paths = _resolve_paths()
    paths.out_dir.mkdir(parents=True, exist_ok=True)

    processed = _load_checkpoint(paths.checkpoint_file)
    all_files: list[str] = []
    for root_name, root_path in paths.raw_roots.items():
        all_files.extend(_discover_raw_files(root_path, root_name))
    all_files.sort(key=_parse_sort_key)
    pending_files = [relative for relative in all_files if relative not in processed]

    if not pending_files:
        return ExportResult(
            export_file=None,
            export_batch_id=None,
            processed_files=[],
            exported_rows=0,
        )

    export_batch_id = f"bronze_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}_{uuid.uuid4().hex[:8]}"
    exported_at = _utc_now_iso()
    output_name = f"bronze_events_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.jsonl"
    output_file = paths.out_dir / output_name

    exported_rows = 0
    with output_file.open("w", encoding="utf-8") as out_f:
        for relative_file in pending_files:
            rel_path = Path(relative_file)
            if len(rel_path.parts) != 3:
                raise ValueError(f"invalid source file key: {relative_file}")
            root_name = rel_path.parts[0]
            root_path = paths.raw_roots.get(root_name)
            if root_path is None:
                raise ValueError(f"unknown raw root in key: {relative_file}")
            full_path = root_path / Path(*rel_path.parts[1:])
            ingestion_source = INGESTION_SOURCE_BY_ROOT.get(root_name, root_name)
            with full_path.open("r", encoding="utf-8") as in_f:
                for line_no, line in enumerate(in_f, start=1):
                    if not line.strip():
                        continue
                    raw = _parse_raw_line(line, relative_file, line_no)
                    bronze_record = _build_bronze_record(
                        raw_record=raw,
                        source_file=relative_file,
                        ingestion_source=ingestion_source,
                        export_batch_id=export_batch_id,
                        exported_at=exported_at,
                    )
                    out_f.write(
                        json.dumps(bronze_record, ensure_ascii=False, separators=(",", ":"))
                        + "\n"
                    )
                    exported_rows += 1

    processed.update(pending_files)
    _save_checkpoint(paths.checkpoint_file, processed)

    return ExportResult(
        export_file=output_file,
        export_batch_id=export_batch_id,
        processed_files=pending_files,
        exported_rows=exported_rows,
    )


def main() -> int:
    result = export_raw_to_bronze()

    if not result.export_file:
        print("No new raw files to export.")
        return 0

    print(f"Export file: {result.export_file}")
    print(f"Export batch id: {result.export_batch_id}")
    print(f"Processed files: {len(result.processed_files)}")
    print(f"Exported rows: {result.exported_rows}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
