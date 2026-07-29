from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from flowpilot.config import Settings
from flowpilot.db.models import OutboxEvent


def add_outbox_event(
    session: Session,
    *,
    organization_id: str,
    aggregate_type: str,
    aggregate_id: str,
    event_type: str,
    payload: dict[str, Any],
    idempotency_key: str,
) -> OutboxEvent:
    existing = session.scalar(
        select(OutboxEvent).where(OutboxEvent.idempotency_key == idempotency_key)
    )
    if existing:
        return existing
    event = OutboxEvent(
        organization_id=organization_id,
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        event_type=event_type,
        payload_json=payload,
        idempotency_key=idempotency_key,
    )
    session.add(event)
    session.flush()
    return event


def publish_pending(session: Session, settings: Settings, *, limit: int = 50) -> int:
    events = list(
        session.scalars(
            select(OutboxEvent)
            .where(OutboxEvent.status == "pending", OutboxEvent.available_at <= datetime.now(UTC))
            .order_by(OutboxEvent.created_at.asc())
            .limit(limit)
        )
    )
    published = 0
    for event in events:
        event.attempts += 1
        if settings.event_sink_url:
            headers = {"Idempotency-Key": event.idempotency_key}
            if settings.event_sink_bearer_token:
                headers["Authorization"] = f"Bearer {settings.event_sink_bearer_token}"
            try:
                response = httpx.post(
                    settings.event_sink_url,
                    json={
                        "id": event.id,
                        "type": event.event_type,
                        "organization_id": event.organization_id,
                        "data": event.payload_json,
                    },
                    headers=headers,
                    timeout=10,
                )
                response.raise_for_status()
            except Exception as exc:
                event.last_error = str(exc)[:2_000]
                continue
        event.status = "published"
        event.published_at = datetime.now(UTC)
        event.last_error = None
        published += 1
    session.flush()
    return published
