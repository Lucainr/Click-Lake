from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..services.gold_data import (
    get_campaign_funnel_rows,
    get_health_rows,
    get_promotion_performance_rows,
)


@dataclass
class ParsedCommand:
    action: str
    sdk_key: str | None = None
    limit: int = 5


SUPPORTED_COMMANDS = {"health", "top-invalid", "top-ctr", "funnel", "help"}


def _safe_float(value: Any) -> float:
    try:
        if value is None:
            return 0.0
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _safe_int(value: Any) -> int:
    try:
        if value is None:
            return 0
        return int(value)
    except (TypeError, ValueError):
        return 0


def _fmt_ratio(value: float) -> str:
    return f"{value * 100:.2f}%"


def parse_command_text(text: str) -> ParsedCommand:
    tokens = [token.strip() for token in text.split() if token.strip()]
    if not tokens:
        return ParsedCommand(action="help")

    action = tokens[0].lower()
    if action not in SUPPORTED_COMMANDS:
        return ParsedCommand(action="help")

    sdk_key: str | None = None
    limit = 5

    for token in tokens[1:]:
        if token.isdigit():
            limit = max(1, min(20, int(token)))
            continue
        if sdk_key is None:
            sdk_key = token

    return ParsedCommand(action=action, sdk_key=sdk_key, limit=limit)


def _help_text() -> str:
    return "\n".join(
        [
            "Click Lake Slack Query Commands",
            "- /clicklake health [sdk_key]",
            "- /clicklake top-invalid [sdk_key] [limit]",
            "- /clicklake top-ctr [sdk_key] [limit]",
            "- /clicklake funnel [sdk_key] [limit]",
            "- /clicklake help",
            "",
            "Examples:",
            "- /clicklake health clk_live_demo",
            "- /clicklake top-ctr clk_live_demo 5",
        ]
    )


def _render_health(sdk_key: str | None) -> str:
    rows = get_health_rows(sdk_key=sdk_key)
    if not rows:
        return "Health: 조회 결과가 없습니다."

    latest_date = rows[0]["event_date"]
    latest_rows = [row for row in rows if row.get("event_date") == latest_date]

    lines = [f"Click Lake Health ({latest_date})"]
    for row in latest_rows:
        lines.extend(
            [
                f"- sdk_key: {row.get('sdk_key', '-')}",
                f"  raw={_safe_int(row.get('raw_event_count'))}, valid={_safe_int(row.get('valid_event_count'))}, invalid={_safe_int(row.get('invalid_event_count'))}",
                f"  invalid_ratio={_fmt_ratio(_safe_float(row.get('invalid_event_ratio')))}, sessions={_safe_int(row.get('distinct_sessions'))}",
            ]
        )
    return "\n".join(lines)


def _render_top_invalid(sdk_key: str | None, limit: int) -> str:
    rows = get_health_rows(sdk_key=sdk_key)
    if not rows:
        return "Top Invalid: 조회 결과가 없습니다."

    sorted_rows = sorted(
        rows,
        key=lambda row: (
            _safe_float(row.get("invalid_event_ratio")),
            _safe_int(row.get("invalid_event_count")),
            row.get("event_date", ""),
        ),
        reverse=True,
    )

    lines = [f"Top Invalid Ratio (limit={limit})"]
    for idx, row in enumerate(sorted_rows[:limit], start=1):
        lines.append(
            f"{idx}. {row.get('event_date')} | {row.get('sdk_key')} | ratio={_fmt_ratio(_safe_float(row.get('invalid_event_ratio')))} | invalid={_safe_int(row.get('invalid_event_count'))}"
        )
    return "\n".join(lines)


def _render_top_ctr(sdk_key: str | None, limit: int) -> str:
    rows = get_promotion_performance_rows(sdk_key=sdk_key)
    if not rows:
        return "Top CTR: 조회 결과가 없습니다."

    sorted_rows = sorted(
        rows,
        key=lambda row: (
            _safe_float(row.get("ctr")),
            _safe_int(row.get("promotion_clicks")),
            row.get("event_date", ""),
        ),
        reverse=True,
    )

    lines = [f"Top CTR Promotions (limit={limit})"]
    for idx, row in enumerate(sorted_rows[:limit], start=1):
        lines.append(
            f"{idx}. {row.get('campaign_id', '-')} / {row.get('promotion_id', '-')} | "
            f"ctr={_fmt_ratio(_safe_float(row.get('ctr')))} | "
            f"clicks={_safe_int(row.get('promotion_clicks'))} views={_safe_int(row.get('promotion_views'))}"
        )
    return "\n".join(lines)


def _render_funnel(sdk_key: str | None, limit: int) -> str:
    rows = get_campaign_funnel_rows(sdk_key=sdk_key)
    if not rows:
        return "Funnel: 조회 결과가 없습니다."

    sorted_rows = sorted(
        rows,
        key=lambda row: (
            row.get("event_date", ""),
            _safe_int(row.get("promotion_view_sessions")),
        ),
        reverse=True,
    )

    lines = [f"Campaign Funnel Summary (limit={limit})"]
    for idx, row in enumerate(sorted_rows[:limit], start=1):
        lines.append(
            f"{idx}. {row.get('event_date')} | {row.get('campaign_id', '-')} | view={_safe_int(row.get('promotion_view_sessions'))} click={_safe_int(row.get('promotion_click_sessions'))} pv={_safe_int(row.get('product_view_sessions'))} atc={_safe_int(row.get('add_to_cart_sessions'))}"
        )
        lines.append(
            f"   rates: view→click={_fmt_ratio(_safe_float(row.get('view_to_click_rate')))}, click→pv={_fmt_ratio(_safe_float(row.get('click_to_product_view_rate')))}, click→atc={_fmt_ratio(_safe_float(row.get('click_to_add_to_cart_rate')))}"
        )
    return "\n".join(lines)


def build_slack_response_text(command_text: str) -> str:
    parsed = parse_command_text(command_text)

    if parsed.action == "help":
        return _help_text()
    if parsed.action == "health":
        return _render_health(parsed.sdk_key)
    if parsed.action == "top-invalid":
        return _render_top_invalid(parsed.sdk_key, parsed.limit)
    if parsed.action == "top-ctr":
        return _render_top_ctr(parsed.sdk_key, parsed.limit)
    if parsed.action == "funnel":
        return _render_funnel(parsed.sdk_key, parsed.limit)

    return _help_text()
