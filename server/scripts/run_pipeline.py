from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
import sys
from typing import Callable

SCRIPT_DIR = Path(__file__).resolve().parent
SERVER_DIR = SCRIPT_DIR.parent
PROJECT_ROOT = SERVER_DIR.parent

if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from app.services.databricks_sql import execute_sql_file  # noqa: E402
from export_raw_to_bronze import export_raw_to_bronze  # noqa: E402
from upload_bronze_batches_to_databricks import UploadError, upload_bronze_batches  # noqa: E402


BRONZE_SQL_FILES = [
    PROJECT_ROOT / "sql" / "bronze" / "03_create_events_raw_json.sql",
]
SILVER_SQL_FILES = [
    PROJECT_ROOT / "sql" / "silver" / "04_create_silver_invalid_events_json.sql",
    PROJECT_ROOT / "sql" / "silver" / "05_create_silver_events_json.sql",
]
GOLD_SQL_FILES = [
    PROJECT_ROOT / "sql" / "gold" / "05_create_gold_workspace_health_daily_json.sql",
    PROJECT_ROOT / "sql" / "gold" / "06_create_gold_promotion_performance_daily_json.sql",
    PROJECT_ROOT / "sql" / "gold" / "07_create_gold_campaign_funnel_daily_json.sql",
]


@dataclass(frozen=True)
class Step:
    name: str
    action: Callable[[], None]


class PipelineStepError(Exception):
    pass


def _run_export_step() -> None:
    result = export_raw_to_bronze()
    if result.export_file:
        print(f"  - export_file: {result.export_file}")
        print(f"  - export_batch_id: {result.export_batch_id}")
        print(f"  - processed_files: {len(result.processed_files)}")
        print(f"  - exported_rows: {result.exported_rows}")
    else:
        print("  - no new raw files to export")


def _run_upload_step() -> None:
    code = upload_bronze_batches()
    if code != 0:
        raise PipelineStepError("upload step returned non-zero exit code")


def _run_sql_group(group_name: str, sql_files: list[Path]) -> None:
    total_executed = 0
    for sql_file in sql_files:
        print(f"  - executing: {sql_file.relative_to(PROJECT_ROOT)}")
        executed = execute_sql_file(sql_file)
        total_executed += executed
        print(f"    statements_executed: {executed}")
    print(f"  - {group_name} total statements: {total_executed}")


def _build_steps(args: argparse.Namespace) -> list[Step]:
    steps: list[Step] = []

    if args.bronze_only:
        return [Step("Bronze SQL", lambda: _run_sql_group("Bronze SQL", BRONZE_SQL_FILES))]
    if args.silver_only:
        return [Step("Silver SQL", lambda: _run_sql_group("Silver SQL", SILVER_SQL_FILES))]
    if args.gold_only:
        return [Step("Gold SQL", lambda: _run_sql_group("Gold SQL", GOLD_SQL_FILES))]

    if not args.skip_export:
        steps.append(Step("Export raw to bronze batch", _run_export_step))
    if not args.skip_upload:
        steps.append(Step("Upload bronze batch files", _run_upload_step))

    if not args.skip_sql:
        steps.append(Step("Run Bronze SQL", lambda: _run_sql_group("Bronze SQL", BRONZE_SQL_FILES)))
        steps.append(Step("Run Silver SQL", lambda: _run_sql_group("Silver SQL", SILVER_SQL_FILES)))
        steps.append(Step("Run Gold SQL", lambda: _run_sql_group("Gold SQL", GOLD_SQL_FILES)))

    return steps


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Click Lake pipeline end-to-end")
    parser.add_argument("--skip-export", action="store_true", help="Skip export_raw_to_bronze step")
    parser.add_argument("--skip-upload", action="store_true", help="Skip upload_bronze_batches step")
    parser.add_argument("--skip-sql", action="store_true", help="Skip Databricks SQL refresh steps")
    parser.add_argument("--bronze-only", action="store_true", help="Run only Bronze SQL refresh")
    parser.add_argument("--silver-only", action="store_true", help="Run only Silver SQL refresh")
    parser.add_argument("--gold-only", action="store_true", help="Run only Gold SQL refresh")
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    selected_modes = [args.bronze_only, args.silver_only, args.gold_only]
    if sum(1 for mode in selected_modes if mode) > 1:
        print("Pipeline configuration error: only one of --bronze-only/--silver-only/--gold-only can be used")
        return 1

    steps = _build_steps(args)
    if not steps:
        print("No steps selected. Nothing to run.")
        return 0

    total_steps = len(steps)
    for index, step in enumerate(steps, start=1):
        print(f"[{index}/{total_steps}] {step.name}...")
        try:
            step.action()
            print(f"[OK] {step.name}")
        except (PipelineStepError, UploadError, FileNotFoundError, Exception) as exc:  # noqa: BLE001
            print(f"[FAIL] {step.name}")
            print(f"Pipeline failed at step: {step.name}")
            print(f"Reason: {exc}")
            return 1

    print("Pipeline completed successfully")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
