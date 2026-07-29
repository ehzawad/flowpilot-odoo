from __future__ import annotations

from datetime import UTC, datetime

from flowpilot.security import (
    action_payload_hash,
    canonical_json,
    sign_action_authorization,
    sign_webhook,
    verify_action_authorization,
    verify_webhook,
)


def test_canonical_json_is_order_independent() -> None:
    assert canonical_json({"b": 2, "a": 1}) == canonical_json({"a": 1, "b": 2})


def test_action_hash_binds_target_and_payload() -> None:
    expires = datetime(2026, 7, 29, tzinfo=UTC)
    first = action_payload_hash(
        organization_id="org",
        case_id="case",
        tool_name="tool",
        target="record:1",
        payload={"quantity": 10},
        expires_at=expires,
    )
    second = action_payload_hash(
        organization_id="org",
        case_id="case",
        tool_name="tool",
        target="record:1",
        payload={"quantity": 11},
        expires_at=expires,
    )
    assert first != second


def test_action_signature_detects_tampering() -> None:
    signature = sign_action_authorization(
        secret="secret", action_id="a1", payload_hash="f" * 64, approver="u1"
    )
    assert verify_action_authorization(
        secret="secret",
        action_id="a1",
        payload_hash="f" * 64,
        approver="u1",
        signature=signature,
    )
    assert not verify_action_authorization(
        secret="secret",
        action_id="a1",
        payload_hash="0" * 64,
        approver="u1",
        signature=signature,
    )


def test_webhook_signature_enforces_timestamp_and_body() -> None:
    body = b'{"event_id":"1"}'
    timestamp, signature = sign_webhook(secret="secret", body=body, timestamp=1_000)
    assert verify_webhook(
        secret="secret",
        body=body,
        timestamp_header=timestamp,
        signature_header=signature,
        max_age_seconds=300,
        now=1_100,
    )
    assert not verify_webhook(
        secret="secret",
        body=b"changed",
        timestamp_header=timestamp,
        signature_header=signature,
        max_age_seconds=300,
        now=1_100,
    )
