from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from flowpilot.config import Settings
from flowpilot.db.models import ActionProposal, Job
from flowpilot.odoo.client import build_odoo_client
from flowpilot.odoo.operations import execute_write_action
from flowpilot.schemas import Actor
from flowpilot.security import action_payload_hash, verify_action_authorization
from flowpilot.services.agent_runs import execute_investigation
from flowpilot.services.cases import add_case_event
from flowpilot.services.jobs import complete_job
from flowpilot.services.outbox import add_outbox_event


class WorkerPolicyError(RuntimeError):
    pass


async def handle_job(session: Session, settings: Settings, job: Job) -> dict[str, Any]:
    if job.job_type == "run_agent_investigation":
        actor = Actor.model_validate(job.payload_json["actor"])
        run, actions = await execute_investigation(
            session,
            settings=settings,
            actor=actor,
            case_id=str(job.payload_json["case_id"]),
            message=str(job.payload_json["message"]),
        )
        result = {"run_id": run.id, "action_ids": [action.id for action in actions]}
        complete_job(session, job.id, result)
        return result
    if job.job_type == "execute_approved_action":
        result = execute_approved_action(session, settings, job)
        complete_job(session, job.id, result)
        return result
    raise WorkerPolicyError(f"Unknown job type: {job.job_type}")


def execute_approved_action(session: Session, settings: Settings, job: Job) -> dict[str, Any]:
    action_id = str(job.payload_json["action_id"])
    expected_hash = str(job.payload_json["payload_hash"])
    statement = select(ActionProposal).where(
        ActionProposal.id == action_id,
        ActionProposal.organization_id == job.organization_id,
    )
    if session.bind and session.bind.dialect.name == "postgresql":
        statement = statement.with_for_update()
    action = session.scalar(statement)
    if not action:
        raise WorkerPolicyError("Approved action no longer exists")
    if action.approval_status != "approved" or action.execution_status not in {"queued", "retry"}:
        if action.execution_status == "succeeded":
            return action.execution_result_json
        raise WorkerPolicyError("Action is not in an executable approved state")
    if action.payload_hash != expected_hash:
        raise WorkerPolicyError("Queued payload hash does not match the action")
    current_hash = action_payload_hash(
        organization_id=action.organization_id,
        case_id=action.case_id,
        tool_name=action.tool_name,
        target=action.target,
        payload=action.payload_json,
        expires_at=action.expires_at,
    )
    if current_hash != action.payload_hash:
        raise WorkerPolicyError("The persisted action payload was modified after proposal")
    if (action.expires_at.replace(tzinfo=UTC) if action.expires_at.tzinfo is None else action.expires_at) <= datetime.now(UTC):
        action.approval_status = "expired"
        action.execution_status = "cancelled"
        raise WorkerPolicyError("The approved action expired before execution")
    if not action.approved_by or not action.authorization_signature:
        raise WorkerPolicyError("Approval authorization is incomplete")
    if not verify_action_authorization(
        secret=settings.odoo_action_signing_secret,
        action_id=action.id,
        payload_hash=action.payload_hash,
        approver=action.approved_by,
        signature=action.authorization_signature,
    ):
        raise WorkerPolicyError("Approval signature verification failed")

    action.execution_status = "running"
    session.flush()
    client = build_odoo_client(settings)
    if settings.odoo_write_mode == "bridge" and settings.odoo_mode != "fake":
        result = client.call(
            "flowpilot.bridge",
            "execute_approved_action",
            {
                "tool_name": action.tool_name,
                "payload": action.payload_json,
                "idempotency_key": f"{action.id}:{action.payload_hash}",
            },
        )
    else:
        result = execute_write_action(
            client,
            tool_name=action.tool_name,
            payload=action.payload_json,
        )
    receipt = result if isinstance(result, dict) else {"result": result}
    action.execution_status = "succeeded"
    action.executed_at = datetime.now(UTC)
    action.execution_result_json = receipt
    add_case_event(
        session,
        organization_id=action.organization_id,
        case_id=action.case_id,
        event_type="action.executed",
        actor_type="worker",
        actor_id=job.locked_by,
        message=f"Executed approved action: {action.title}",
        payload={"action_id": action.id, "receipt": receipt},
    )
    add_outbox_event(
        session,
        organization_id=action.organization_id,
        aggregate_type="action_proposal",
        aggregate_id=action.id,
        event_type="flowpilot.action.executed",
        payload={
            "action_id": action.id,
            "case_id": action.case_id,
            "tool_name": action.tool_name,
            "receipt": receipt,
        },
        idempotency_key=f"action-executed:{action.id}:{action.payload_hash}",
    )
    session.flush()
    return receipt
