from __future__ import annotations

import hashlib
import hmac
import json
import time
from datetime import UTC, datetime
from typing import Any


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def action_payload_hash(
    *,
    organization_id: str,
    case_id: str,
    tool_name: str,
    target: str,
    payload: dict[str, Any],
    expires_at: datetime,
) -> str:
    message = {
        "organization_id": organization_id,
        "case_id": case_id,
        "tool_name": tool_name,
        "target": target,
        "payload": payload,
        "expires_at": (
            expires_at.replace(tzinfo=UTC) if expires_at.tzinfo is None else expires_at.astimezone(UTC)
        ).isoformat().replace("+00:00", "Z"),
    }
    return hashlib.sha256(canonical_json(message).encode()).hexdigest()


def sign_action_authorization(*, secret: str, action_id: str, payload_hash: str, approver: str) -> str:
    message = f"{action_id}:{payload_hash}:{approver}".encode()
    return hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()


def verify_action_authorization(
    *, secret: str, action_id: str, payload_hash: str, approver: str, signature: str
) -> bool:
    expected = sign_action_authorization(
        secret=secret,
        action_id=action_id,
        payload_hash=payload_hash,
        approver=approver,
    )
    return hmac.compare_digest(expected, signature)


def sign_webhook(*, secret: str, body: bytes, timestamp: int | None = None) -> tuple[str, str]:
    value = timestamp or int(time.time())
    message = str(value).encode() + b"." + body
    signature = hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()
    return str(value), f"sha256={signature}"


def verify_webhook(
    *,
    secret: str,
    body: bytes,
    timestamp_header: str | None,
    signature_header: str | None,
    max_age_seconds: int,
    now: int | None = None,
) -> bool:
    if not timestamp_header or not signature_header:
        return False
    try:
        timestamp = int(timestamp_header)
    except ValueError:
        return False
    current = now or int(time.time())
    if abs(current - timestamp) > max_age_seconds:
        return False
    expected_timestamp, expected_signature = sign_webhook(
        secret=secret, body=body, timestamp=timestamp
    )
    return expected_timestamp == timestamp_header and hmac.compare_digest(
        expected_signature, signature_header
    )
