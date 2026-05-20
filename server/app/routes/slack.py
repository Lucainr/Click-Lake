from __future__ import annotations

import hashlib
import hmac
import time
from urllib.parse import parse_qs

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from ..config import settings
from ..errors import ApiError, UnknownApiError
from ..schemas import SlackCommandResponse
from ..services.slack_query_service import build_slack_response_text

router = APIRouter(prefix="/slack", tags=["slack"])


def _verify_slack_signature(headers: dict[str, str], body: bytes) -> tuple[bool, str | None]:
    if not settings.slack_enable_signature_validation:
        return True, None

    signing_secret = (settings.slack_signing_secret or "").strip()
    if not signing_secret:
        return False, "SLACK_SIGNING_SECRET is required when signature validation is enabled"

    timestamp = headers.get("x-slack-request-timestamp", "")
    signature = headers.get("x-slack-signature", "")

    if not timestamp or not signature:
        return False, "Missing Slack signature headers"

    try:
        request_time = int(timestamp)
    except ValueError:
        return False, "Invalid Slack request timestamp"

    # Reject replayed requests older than 5 minutes.
    if abs(int(time.time()) - request_time) > 60 * 5:
        return False, "Stale Slack request timestamp"

    base_string = f"v0:{timestamp}:{body.decode('utf-8')}".encode("utf-8")
    computed = "v0=" + hmac.new(
        signing_secret.encode("utf-8"),
        base_string,
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(computed, signature):
        return False, "Invalid Slack signature"

    return True, None


@router.post("/commands/clicklake", response_model=SlackCommandResponse)
async def clicklake_slash_command(request: Request) -> SlackCommandResponse | JSONResponse:
    body = await request.body()
    is_valid, reason = _verify_slack_signature(dict(request.headers), body)
    if not is_valid:
        return JSONResponse(
            status_code=401,
            content={
                "response_type": "ephemeral",
                "text": f"Slack request validation failed: {reason}",
            },
        )

    form_data = parse_qs(body.decode("utf-8"), keep_blank_values=True)
    command_text = (form_data.get("text", [""])[0] or "").strip()

    try:
        text = build_slack_response_text(command_text)
    except ApiError as exc:
        text = f"[{exc.error_code}] {exc.message}\n{exc.details or ''}".strip()
    except Exception as exc:
        unknown = UnknownApiError(str(exc))
        text = f"[{unknown.error_code}] {unknown.message}\n{unknown.details or ''}".strip()

    return SlackCommandResponse(response_type="ephemeral", text=text)
