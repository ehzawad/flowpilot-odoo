from __future__ import annotations

from flowpilot.db.base import session_scope
from flowpilot.services.jobs import claim_job, complete_job, enqueue_job


def test_job_idempotency_and_claim(settings) -> None:
    with session_scope(settings.database_url, organization_id=settings.demo_tenant_id) as session:
        first = enqueue_job(
            session,
            organization_id=settings.demo_tenant_id,
            job_type="test",
            payload={"value": 1},
            idempotency_key="same",
        )
        second = enqueue_job(
            session,
            organization_id=settings.demo_tenant_id,
            job_type="test",
            payload={"value": 2},
            idempotency_key="same",
        )
        assert first.id == second.id
    with session_scope(settings.database_url, organization_id=settings.demo_tenant_id) as session:
        claimed = claim_job(session, worker_id="worker", lease_seconds=60)
        assert claimed and claimed.state == "running" and claimed.attempts == 1
        complete_job(session, claimed.id, {"ok": True})
        assert claimed.state == "succeeded"
