from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from flowpilot.agent.context import AgentContext
from flowpilot.agent.factory import create_runtime
from flowpilot.agent.prompt import PROMPT_VERSION, TOOLSET_VERSION
from flowpilot.config import Settings
from flowpilot.db.models import ActionProposal, AgentRun, UsageRecord
from flowpilot.schemas import Actor
from flowpilot.services.approvals import create_action_proposals
from flowpilot.services.cases import add_case_event, get_case


class AgentRunNotFoundError(LookupError):
    pass


async def execute_investigation(
    session: Session,
    *,
    settings: Settings,
    actor: Actor,
    case_id: str,
    message: str,
) -> tuple[AgentRun, list[ActionProposal]]:
    case = get_case(session, actor.tenant_id, case_id)
    runtime = create_runtime(settings)
    run = AgentRun(
        organization_id=actor.tenant_id,
        case_id=case.id,
        user_id=actor.user_id,
        status="running",
        runtime=runtime.name,
        model="pending",
        prompt_version=PROMPT_VERSION,
        toolset_version=TOOLSET_VERSION,
        input_text=message,
    )
    session.add(run)
    session.flush()
    add_case_event(
        session,
        organization_id=actor.tenant_id,
        case_id=case.id,
        event_type="agent.started",
        actor_type="user",
        actor_id=actor.user_id,
        message="Durable agent investigation started",
        payload={"agent_run_id": run.id, "runtime": runtime.name},
    )
    session.commit()

    context = AgentContext(
        organization_id=actor.tenant_id,
        case_id=case.id,
        user_id=actor.user_id,
        database_url=settings.effective_worker_database_url,
        settings=settings,
    )
    try:
        result = await runtime.run(context, message)
    except Exception as exc:
        run = session.get(AgentRun, run.id)
        assert run is not None
        run.status = "failed"
        run.error_json = {"type": type(exc).__name__, "message": str(exc)[:4_000]}
        add_case_event(
            session,
            organization_id=actor.tenant_id,
            case_id=case.id,
            event_type="agent.failed",
            actor_type="agent",
            actor_id=run.id,
            message="Agent investigation failed",
            payload=run.error_json,
        )
        session.flush()
        raise

    run = session.get(AgentRun, run.id)
    assert run is not None
    run.status = "completed"
    run.model = result.model
    run.trace_id = result.trace_id
    run.corpus_version = result.corpus_version
    run.output_json = result.answer.model_dump(mode="json")
    run.input_tokens = result.usage.input_tokens
    run.output_tokens = result.usage.output_tokens
    run.cost_usd_micros = result.usage.cost_usd_micros
    run.latency_ms = result.usage.latency_ms
    actions = create_action_proposals(
        session,
        organization_id=actor.tenant_id,
        case_id=case.id,
        agent_run_id=run.id,
        drafts=result.actions,
    )
    session.add_all(
        [
            UsageRecord(
                organization_id=actor.tenant_id,
                user_id=actor.user_id,
                case_id=case.id,
                agent_run_id=run.id,
                meter="input_tokens",
                quantity=result.usage.input_tokens,
                unit="tokens",
                cost_usd_micros=0,
            ),
            UsageRecord(
                organization_id=actor.tenant_id,
                user_id=actor.user_id,
                case_id=case.id,
                agent_run_id=run.id,
                meter="output_tokens",
                quantity=result.usage.output_tokens,
                unit="tokens",
                cost_usd_micros=result.usage.cost_usd_micros,
            ),
            UsageRecord(
                organization_id=actor.tenant_id,
                user_id=actor.user_id,
                case_id=case.id,
                agent_run_id=run.id,
                meter="tool_calls",
                quantity=result.usage.tool_calls,
                unit="calls",
                cost_usd_micros=0,
            ),
        ]
    )
    add_case_event(
        session,
        organization_id=actor.tenant_id,
        case_id=case.id,
        event_type="agent.completed",
        actor_type="agent",
        actor_id=run.id,
        message=result.answer.headline,
        payload={
            "agent_run_id": run.id,
            "model": result.model,
            "trace_id": result.trace_id,
            "actions": [action.id for action in actions],
            "latency_ms": result.usage.latency_ms,
        },
    )
    session.flush()
    return run, actions


def get_agent_run(
    session: Session,
    *,
    organization_id: str,
    case_id: str,
    run_id: str,
) -> tuple[AgentRun, list[ActionProposal]]:
    run = session.scalar(
        select(AgentRun).where(
            AgentRun.id == run_id,
            AgentRun.organization_id == organization_id,
            AgentRun.case_id == case_id,
        )
    )
    if not run:
        raise AgentRunNotFoundError(run_id)
    actions = list(
        session.scalars(
            select(ActionProposal)
            .where(
                ActionProposal.organization_id == organization_id,
                ActionProposal.agent_run_id == run_id,
            )
            .order_by(ActionProposal.created_at.asc())
        )
    )
    return run, actions
