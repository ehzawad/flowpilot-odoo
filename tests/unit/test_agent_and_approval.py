from __future__ import annotations

import asyncio

import pytest
from sqlalchemy import select

from flowpilot.agent.context import AgentContext
from flowpilot.agent.fake_runtime import FakeAgentRuntime
from flowpilot.db.base import session_scope
from flowpilot.db.models import ActionProposal, Case, Job
from flowpilot.schemas import Actor, ApprovalDecisionRequest
from flowpilot.services.agent_runs import execute_investigation
from flowpilot.services.approvals import ApprovalError, decide_action


def test_fake_agent_proposes_bounded_action(settings) -> None:
    with session_scope(settings.database_url, organization_id=settings.demo_tenant_id) as session:
        case = session.scalar(
            select(Case).where(Case.category == "inventory_shortage")
        )
        assert case
    result = asyncio.run(
        FakeAgentRuntime().run(
            AgentContext(
                organization_id=settings.demo_tenant_id,
                case_id=case.id,
                user_id=settings.demo_user_id,
                database_url=settings.database_url,
                settings=settings,
            ),
            "Investigate this stockout.",
        )
    )
    assert result.answer.evidence
    assert [item.tool_name for item in result.actions] == ["odoo.create_draft_rfq"]


def test_approval_binds_expected_hash(settings) -> None:
    actor = Actor(
        tenant_id=settings.demo_tenant_id,
        user_id=settings.demo_user_id,
        email=settings.demo_user_email,
        role="approver",
    )
    with session_scope(settings.database_url, organization_id=actor.tenant_id) as session:
        case = session.scalar(select(Case).where(Case.category == "inventory_shortage"))
        assert case
        run, actions = asyncio.run(
            execute_investigation(
                session,
                settings=settings,
                actor=actor,
                case_id=case.id,
                message="Investigate.",
            )
        )
        assert run.status == "completed" and actions
        action_id = actions[0].id

    with session_scope(settings.database_url, organization_id=actor.tenant_id) as session:
        with pytest.raises(ApprovalError, match="payload changed"):
            decide_action(
                session,
                settings=settings,
                actor=actor,
                action_id=action_id,
                request=ApprovalDecisionRequest(
                    decision="approve", expected_payload_hash="0" * 64
                ),
            )

    with session_scope(settings.database_url, organization_id=actor.tenant_id) as session:
        action = session.get(ActionProposal, action_id)
        assert action
        action, job_id = decide_action(
            session,
            settings=settings,
            actor=actor,
            action_id=action_id,
            request=ApprovalDecisionRequest(
                decision="approve", expected_payload_hash=action.payload_hash
            ),
        )
        assert action.authorization_signature
        assert job_id and session.get(Job, job_id)
