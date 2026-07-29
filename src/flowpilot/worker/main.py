from __future__ import annotations

import asyncio
import logging
import os
import socket
import uuid

from flowpilot.config import get_settings
from flowpilot.db.base import create_schema, session_scope
from flowpilot.services.jobs import claim_job, fail_job
from flowpilot.services.outbox import publish_pending
from flowpilot.worker.handlers import handle_job

LOGGER = logging.getLogger("flowpilot.worker")


async def run_once(worker_id: str | None = None) -> bool:
    settings = get_settings()
    identity = worker_id or f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:8]}"
    with session_scope(settings.effective_worker_database_url) as session:
        job = claim_job(
            session,
            worker_id=identity,
            lease_seconds=settings.worker_lease_seconds,
        )
        if not job:
            publish_pending(session, settings)
            return False
        job_id = job.id
    try:
        with session_scope(
            settings.effective_worker_database_url,
            organization_id=job.organization_id,
        ) as session:
            active_job = session.get(type(job), job_id)
            assert active_job is not None
            await handle_job(session, settings, active_job)
            publish_pending(session, settings)
    except Exception as exc:
        LOGGER.exception("job_failed", extra={"job_id": job_id, "error": str(exc)})
        with session_scope(
            settings.effective_worker_database_url,
            organization_id=job.organization_id,
        ) as session:
            fail_job(session, job_id, str(exc))
    return True


async def serve() -> None:
    settings = get_settings()
    if settings.auto_create_schema:
        create_schema(settings.effective_worker_database_url)
    LOGGER.info("worker_started")
    while True:
        claimed = await run_once()
        if not claimed:
            await asyncio.sleep(settings.worker_poll_seconds)


def run() -> None:
    logging.basicConfig(level=get_settings().log_level)
    asyncio.run(serve())


if __name__ == "__main__":
    run()
