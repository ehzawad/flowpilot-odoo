from __future__ import annotations

import random
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from flowpilot.db.models import Job


class JobNotFoundError(LookupError):
    pass


def enqueue_job(
    session: Session,
    *,
    organization_id: str,
    job_type: str,
    payload: dict[str, Any],
    idempotency_key: str,
    priority: int = 100,
    max_attempts: int = 6,
    available_at: datetime | None = None,
) -> Job:
    existing = session.scalar(select(Job).where(Job.idempotency_key == idempotency_key))
    if existing:
        return existing
    job = Job(
        organization_id=organization_id,
        job_type=job_type,
        payload_json=payload,
        idempotency_key=idempotency_key,
        priority=priority,
        max_attempts=max_attempts,
        available_at=available_at or datetime.now(UTC),
    )
    session.add(job)
    session.flush()
    return job


def claim_job(
    session: Session,
    *,
    worker_id: str,
    lease_seconds: int,
    job_types: set[str] | None = None,
) -> Job | None:
    now = datetime.now(UTC)
    statement = (
        select(Job)
        .where(
            Job.state.in_(["queued", "retry"]),
            Job.available_at <= now,
            or_(Job.lease_until.is_(None), Job.lease_until < now),
        )
        .order_by(Job.priority.asc(), Job.created_at.asc())
        .limit(1)
    )
    if job_types:
        statement = statement.where(Job.job_type.in_(job_types))
    if session.bind and session.bind.dialect.name == "postgresql":
        statement = statement.with_for_update(skip_locked=True)
    job = session.scalar(statement)
    if not job:
        return None
    job.state = "running"
    job.attempts += 1
    job.locked_by = worker_id
    job.locked_at = now
    job.lease_until = now + timedelta(seconds=lease_seconds)
    session.flush()
    return job


def get_job(session: Session, organization_id: str, job_id: str) -> Job:
    job = session.scalar(
        select(Job).where(Job.id == job_id, Job.organization_id == organization_id)
    )
    if not job:
        raise JobNotFoundError(job_id)
    return job


def complete_job(session: Session, job_id: str, result: dict[str, Any]) -> Job:
    job = session.get(Job, job_id)
    if not job:
        raise JobNotFoundError(job_id)
    job.state = "succeeded"
    job.result_json = result
    job.last_error = None
    job.lease_until = None
    job.locked_by = None
    session.flush()
    return job


def fail_job(session: Session, job_id: str, error: str) -> Job:
    job = session.get(Job, job_id)
    if not job:
        raise JobNotFoundError(job_id)
    job.last_error = error[:10_000]
    job.lease_until = None
    job.locked_by = None
    if job.attempts >= job.max_attempts:
        job.state = "dead"
    else:
        backoff = min(900.0, float(2 ** max(job.attempts - 1, 0))) + random.random()
        job.state = "retry"
        job.available_at = datetime.now(UTC) + timedelta(seconds=backoff)
    session.flush()
    return job
