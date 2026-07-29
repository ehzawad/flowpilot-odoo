from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from flowpilot.config import Settings
from flowpilot.db.models import ActionProposal, ApprovalDecision
from flowpilot.schemas import ActionDraft, Actor, ApprovalDecisionRequest
from flowpilot.security import action_payload_hash, sign_action_authorization
from flowpilot.services.cases import add_case_event
from flowpilot.services.jobs import enqueue_job


class ApprovalError(ValueError):
    pass


def create_action_proposals(
    session: Session,
    *,
    organization_id: str,
    case_id: str,
    agent_run_id: str,
    drafts: list[ActionDraft],
) -> list[ActionProposal]:
    actions: list[ActionProposal] = []
    now = datetime.now(UTC)
    for draft in drafts:
        expires_at = now + timedelta(minutes=draft.expires_in_minutes)
        digest = action_payload_hash(
            organization_id=organization_id,
            case_id=case_id,
            tool_name=draft.tool_name,
            target=draft.target,
            payload=draft.payload,
            expires_at=expires_at,
        )
        existing = session.scalar(
            select(ActionProposal).where(
                ActionProposal.organization_id == organization_id,
                ActionProposal.payload_hash == digest,
            )
        )
        if existing:
            actions.append(existing)
            continue
        action = ActionProposal(
            organization_id=organization_id,
            case_id=case_id,
            agent_run_id=agent_run_id,
            tool_name=draft.tool_name,
            title=draft.title,
            rationale=draft.rationale,
            target=draft.target,
            payload_json=draft.payload,
            payload_hash=digest,
            risk_level=draft.risk_level,
            expires_at=expires_at,
        )
        session.add(action)
        session.flush()
        add_case_event(
            session,
            organization_id=organization_id,
            case_id=case_id,
            event_type="approval.requested",
            actor_type="agent",
            actor_id=agent_run_id,
            message=draft.title,
            payload={"action_id": action.id, "risk_level": draft.risk_level},
        )
        actions.append(action)
    return actions


def list_pending_actions(session: Session, organization_id: str) -> list[ActionProposal]:
    return list(
        session.scalars(
            select(ActionProposal)
            .where(
                ActionProposal.organization_id == organization_id,
                ActionProposal.approval_status == "pending",
            )
            .order_by(ActionProposal.created_at.desc())
        )
    )


def decide_action(
    session: Session,
    *,
    settings: Settings,
    actor: Actor,
    action_id: str,
    request: ApprovalDecisionRequest,
) -> tuple[ActionProposal, str | None]:
    if request.decision == "approve" and not actor.can_approve():
        raise ApprovalError("The current role cannot approve consequential actions")
    statement = select(ActionProposal).where(
        ActionProposal.id == action_id,
        ActionProposal.organization_id == actor.tenant_id,
    )
    if session.bind and session.bind.dialect.name == "postgresql":
        statement = statement.with_for_update()
    action = session.scalar(statement)
    if not action:
        raise ApprovalError("Action proposal was not found")
    if action.approval_status != "pending":
        raise ApprovalError(f"Action is already {action.approval_status}")
    if (action.expires_at.replace(tzinfo=UTC) if action.expires_at.tzinfo is None else action.expires_at) <= datetime.now(UTC):
        action.approval_status = "expired"
        raise ApprovalError("Action proposal has expired")
    if request.expected_payload_hash != action.payload_hash:
        raise ApprovalError("Action payload changed; reload before deciding")

    decision = ApprovalDecision(
        organization_id=actor.tenant_id,
        action_proposal_id=action.id,
        user_id=actor.user_id,
        decision=request.decision,
        reason=request.reason,
        bound_payload_hash=action.payload_hash,
    )
    session.add(decision)

    job_id: str | None = None
    if request.decision == "approve":
        action.approval_status = "approved"
        action.approved_by = actor.user_id
        action.approved_at = datetime.now(UTC)
        action.authorization_signature = sign_action_authorization(
            secret=settings.odoo_action_signing_secret,
            action_id=action.id,
            payload_hash=action.payload_hash,
            approver=actor.user_id,
        )
        action.execution_status = "queued"
        job = enqueue_job(
            session,
            organization_id=actor.tenant_id,
            job_type="execute_approved_action",
            payload={"action_id": action.id, "payload_hash": action.payload_hash},
            idempotency_key=f"execute-action:{action.id}:{action.payload_hash}",
            priority=20,
            max_attempts=settings.worker_max_attempts,
        )
        job_id = job.id
        event_type = "approval.approved"
        message = f"Approved exact payload: {action.title}"
    else:
        action.approval_status = "rejected"
        action.rejection_reason = request.reason
        action.execution_status = "cancelled"
        event_type = "approval.rejected"
        message = f"Rejected: {action.title}"

    add_case_event(
        session,
        organization_id=actor.tenant_id,
        case_id=action.case_id,
        event_type=event_type,
        actor_type="user",
        actor_id=actor.user_id,
        message=message,
        payload={"action_id": action.id, "reason": request.reason},
    )
    session.flush()
    return action, job_id
