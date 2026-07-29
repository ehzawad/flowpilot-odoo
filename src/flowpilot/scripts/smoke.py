from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

from sqlalchemy import select

from flowpilot.config import Settings
from flowpilot.db.base import create_schema, session_scope
from flowpilot.db.models import ActionProposal, Case, Job, OutboxEvent
from flowpilot.schemas import Actor, ApprovalDecisionRequest
from flowpilot.scripts.seed_demo import seed_demo
from flowpilot.services.approvals import decide_action
from flowpilot.services.jobs import claim_job, enqueue_job
from flowpilot.worker.handlers import handle_job


async def smoke() -> dict[str, str | int]:
    with tempfile.TemporaryDirectory(prefix="flowpilot-smoke-") as directory:
        database_url = f"sqlite:///{Path(directory) / 'flowpilot.db'}"
        settings = Settings(
            environment="test",
            database_url=database_url,
            worker_database_url=database_url,
            auto_create_schema=True,
            seed_demo_data=False,
            agent_runtime="fake",
            odoo_mode="fake",
            odoo_write_mode="fake",
            auth_mode="demo",
        )
        create_schema(database_url)
        seed_demo(settings)
        actor = Actor(
            tenant_id=settings.demo_tenant_id,
            user_id=settings.demo_user_id,
            email=settings.demo_user_email,
            role="approver",
        )
        with session_scope(database_url, organization_id=actor.tenant_id) as session:
            case = session.scalar(
                select(Case).where(
                    Case.organization_id == actor.tenant_id,
                    Case.category == "inventory_shortage",
                )
            )
            assert case is not None
            investigation = enqueue_job(
                session,
                organization_id=actor.tenant_id,
                job_type="run_agent_investigation",
                payload={
                    "case_id": case.id,
                    "message": "Investigate and propose the safest next action.",
                    "actor": actor.model_dump(),
                },
                idempotency_key="smoke-investigation",
            )
            investigation_id = investigation.id

        with session_scope(database_url, organization_id=actor.tenant_id) as session:
            job = claim_job(session, worker_id="smoke-worker", lease_seconds=60)
            assert job and job.id == investigation_id
            await handle_job(session, settings, job)

        with session_scope(database_url, organization_id=actor.tenant_id) as session:
            completed = session.get(Job, investigation_id)
            assert completed and completed.state == "succeeded"
            action = session.scalar(
                select(ActionProposal).where(
                    ActionProposal.organization_id == actor.tenant_id,
                    ActionProposal.approval_status == "pending",
                )
            )
            assert action is not None
            action, execution_job_id = decide_action(
                session,
                settings=settings,
                actor=actor,
                action_id=action.id,
                request=ApprovalDecisionRequest(
                    decision="approve",
                    expected_payload_hash=action.payload_hash,
                    reason="Smoke test approval",
                ),
            )
            assert execution_job_id

        with session_scope(database_url, organization_id=actor.tenant_id) as session:
            job = claim_job(session, worker_id="smoke-worker", lease_seconds=60)
            assert job and job.id == execution_job_id
            await handle_job(session, settings, job)

        with session_scope(database_url, organization_id=actor.tenant_id) as session:
            action = session.scalar(
                select(ActionProposal).where(
                    ActionProposal.organization_id == actor.tenant_id,
                    ActionProposal.execution_status == "succeeded",
                )
            )
            assert action is not None
            assert session.scalar(select(OutboxEvent).where(OutboxEvent.aggregate_id == action.id))
            return {
                "status": "ok",
                "case_id": action.case_id,
                "action_id": action.id,
                "execution_status": action.execution_status,
                "outbox_events": int(session.query(OutboxEvent).count()),
            }


def main() -> None:
    print(asyncio.run(smoke()))


if __name__ == "__main__":
    main()
