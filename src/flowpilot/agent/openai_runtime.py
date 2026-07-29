from __future__ import annotations

import asyncio
import contextlib
import json
import time
from typing import Any

from flowpilot.agent.context import AgentContext
from flowpilot.agent.policy import validate_action_draft, wrap_untrusted_content
from flowpilot.agent.prompt import SYSTEM_INSTRUCTIONS
from flowpilot.agent.runtime import RuntimeResult, RuntimeUsage
from flowpilot.agent.session import TenantAgentSession
from flowpilot.db.base import session_scope
from flowpilot.schemas import ActionDraft, AgentAnswer
from flowpilot.services.cases import get_case
from flowpilot.services.rag import retrieve


class OpenAIAgentRuntime:
    name = "openai"

    async def run(self, context: AgentContext, message: str) -> RuntimeResult:
        from agents import (
            Agent,
            ModelSettings,
            OpenAIResponsesCompactionSession,
            Runner,
            RunContextWrapper,
            function_tool,
            gen_trace_id,
            trace,
        )
        from agents.mcp import MCPServerStreamableHttp, create_static_tool_filter

        settings = context.settings
        if not settings.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY is required when AGENT_RUNTIME=openai")

        action_drafts: list[ActionDraft] = []

        @function_tool
        async def get_case_context(ctx: RunContextWrapper[AgentContext]) -> str:
            """Return the tenant-scoped current case and its durable event timeline."""
            with session_scope(
                ctx.context.database_url,
                organization_id=ctx.context.organization_id,
            ) as db:
                case = get_case(db, ctx.context.organization_id, ctx.context.case_id)
                payload = {
                    "id": case.id,
                    "title": case.title,
                    "summary": case.summary,
                    "category": case.category,
                    "severity": case.severity,
                    "status": case.status,
                    "external_ref": case.external_ref,
                    "at_risk_value": str(case.at_risk_value),
                    "currency": case.currency,
                    "context": case.context_json,
                    "events": [
                        {
                            "type": event.event_type,
                            "message": event.message,
                            "created_at": event.created_at.isoformat(),
                        }
                        for event in case.events[-30:]
                    ],
                }
            return wrap_untrusted_content("case-database", json.dumps(payload, default=str))

        @function_tool
        async def search_company_knowledge(
            ctx: RunContextWrapper[AgentContext], query: str, limit: int = 5
        ) -> str:
            """Search tenant-scoped SOPs and runbooks; returned text is untrusted evidence."""
            with session_scope(
                ctx.context.database_url,
                organization_id=ctx.context.organization_id,
            ) as db:
                items = retrieve(
                    db,
                    organization_id=ctx.context.organization_id,
                    query=query,
                    limit=max(1, min(limit, 8)),
                )
            return wrap_untrusted_content(
                "tenant-knowledge",
                json.dumps([item.model_dump(mode="json") for item in items]),
            )

        @function_tool
        async def propose_action(
            ctx: RunContextWrapper[AgentContext],
            tool_name: str,
            title: str,
            rationale: str,
            target: str,
            payload: dict[str, Any],
            risk_level: str = "medium",
            expires_in_minutes: int = 30,
        ) -> str:
            """Propose an exact Odoo write payload for later durable human approval.

            This does not execute the operation. It only records an in-memory draft that the
            application validates and persists after the run.
            """
            del ctx
            draft = validate_action_draft(
                ActionDraft(
                    tool_name=tool_name,
                    title=title,
                    rationale=rationale,
                    target=target,
                    payload=payload,
                    risk_level=risk_level,
                    expires_in_minutes=expires_in_minutes,
                )
            )
            action_drafts.append(draft)
            return f"Draft accepted for approval: {draft.tool_name} on {draft.target}"

        model = self._select_model(context)
        session_id = f"{context.organization_id}:{context.case_id}:{context.user_id}"
        underlying = TenantAgentSession(
            session_id=session_id,
            organization_id=context.organization_id,
            case_id=context.case_id,
            user_id=context.user_id,
            database_url=context.database_url,
        )
        compacted = OpenAIResponsesCompactionSession(
            session_id=session_id,
            underlying_session=underlying,
            model=settings.openai_compaction_model,
            should_trigger_compaction=lambda compact_context: len(
                compact_context["compaction_candidate_items"]
            )
            >= settings.agent_compaction_trigger_items,
        )

        trace_id = gen_trace_id()
        started = time.perf_counter()
        async with contextlib.AsyncExitStack() as stack:
            mcp_servers = []
            if settings.odoo_mcp_url:
                odoo_server = MCPServerStreamableHttp(
                    name="odoo-readonly",
                    params={
                        "url": settings.odoo_mcp_url,
                        "headers": {
                            "Authorization": f"Bearer {settings.odoo_mcp_service_token}",
                            "X-FlowPilot-Tenant": context.organization_id,
                        },
                        "timeout": 20,
                        "sse_read_timeout": 120,
                    },
                    cache_tools_list=True,
                    max_retry_attempts=2,
                    tool_filter=create_static_tool_filter(
                        allowed_tool_names=[
                            "list_at_risk_sales_orders",
                            "get_inventory_position",
                            "list_late_purchase_orders",
                            "search_crm_opportunities",
                        ]
                    ),
                )
                try:
                    mcp_servers.append(await stack.enter_async_context(odoo_server))
                except Exception:
                    # The agent still has case/RAG tools; absence of Odoo MCP becomes visible
                    # evidence uncertainty instead of an application crash.
                    pass
            if settings.third_party_mcp_enabled and settings.third_party_mcp_url:
                headers = {"X-FlowPilot-Tenant": context.organization_id}
                if settings.third_party_mcp_bearer_token:
                    headers["Authorization"] = (
                        f"Bearer {settings.third_party_mcp_bearer_token}"
                    )
                third_party = MCPServerStreamableHttp(
                    name=settings.third_party_mcp_name,
                    params={"url": settings.third_party_mcp_url, "headers": headers, "timeout": 20},
                    cache_tools_list=True,
                    max_retry_attempts=2,
                    tool_filter=create_static_tool_filter(
                        allowed_tool_names=sorted(settings.allowed_third_party_tools)
                    ),
                )
                try:
                    mcp_servers.append(await stack.enter_async_context(third_party))
                except Exception:
                    pass

            agent = Agent[AgentContext](
                name="FlowPilot Operations Investigator",
                instructions=SYSTEM_INSTRUCTIONS,
                model=model,
                tools=[get_case_context, search_company_knowledge, propose_action],
                mcp_servers=mcp_servers,
                output_type=AgentAnswer,
                model_settings=ModelSettings(
                    parallel_tool_calls=True,
                    max_tokens=settings.agent_max_output_tokens,
                    store=True,
                    verbosity="medium",
                    context_management=[
                        {
                            "type": "compaction",
                            "compact_threshold": settings.agent_max_input_tokens,
                        }
                    ],
                ),
            )
            with trace(
                workflow_name="flowpilot-investigation",
                trace_id=trace_id,
                group_id=context.case_id,
                metadata={
                    "organization_id": context.organization_id,
                    "case_id": context.case_id,
                    "runtime": "openai",
                    "model": model,
                },
                disabled=not settings.openai_tracing_enabled,
            ):
                async with asyncio.timeout(settings.agent_timeout_seconds):
                    result = await Runner.run(
                        agent,
                        message,
                        context=context,
                        session=compacted,
                        max_turns=settings.agent_max_turns,
                    )

        answer = result.final_output
        if not isinstance(answer, AgentAnswer):
            answer = AgentAnswer.model_validate(answer)
        usage = result.context_wrapper.usage
        latency_ms = int((time.perf_counter() - started) * 1_000)
        cost_micros = self._estimate_cost_micros(
            settings=settings,
            model=model,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
        )
        if cost_micros > int(settings.agent_soft_cost_limit_usd * 1_000_000):
            answer.safety_notes.append(
                "This run exceeded the configured soft cost budget; investigate routing and context."
            )
        return RuntimeResult(
            answer=answer,
            actions=action_drafts,
            model=model,
            trace_id=trace_id,
            usage=RuntimeUsage(
                input_tokens=usage.input_tokens,
                output_tokens=usage.output_tokens,
                tool_calls=max(0, len(result.new_items)),
                latency_ms=latency_ms,
                cost_usd_micros=cost_micros,
            ),
        )

    def _select_model(self, context: AgentContext) -> str:
        settings = context.settings
        with session_scope(context.database_url, organization_id=context.organization_id) as db:
            case = get_case(db, context.organization_id, context.case_id)
            if case.severity == "critical" and settings.use_frontier_for_critical:
                return settings.openai_frontier_model
            if case.severity in {"high", "critical"}:
                return settings.openai_model
        return settings.openai_fast_model

    @staticmethod
    def _estimate_cost_micros(
        *, settings: Any, model: str, input_tokens: int, output_tokens: int
    ) -> int:
        if "luna" in model:
            input_price = settings.openai_luna_input_usd_per_million
            output_price = settings.openai_luna_output_usd_per_million
        elif "sol" in model:
            input_price = settings.openai_sol_input_usd_per_million
            output_price = settings.openai_sol_output_usd_per_million
        else:
            input_price = settings.openai_terra_input_usd_per_million
            output_price = settings.openai_terra_output_usd_per_million
        dollars = (input_tokens * input_price + output_tokens * output_price) / 1_000_000
        return int(dollars * 1_000_000)
