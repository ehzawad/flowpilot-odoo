from __future__ import annotations

import time
import uuid
from decimal import Decimal

from flowpilot.agent.context import AgentContext
from flowpilot.agent.policy import validate_action_draft
from flowpilot.agent.runtime import RuntimeResult, RuntimeUsage
from flowpilot.db.base import session_scope
from flowpilot.schemas import ActionDraft, AgentAnswer, Evidence
from flowpilot.services.cases import get_case
from flowpilot.services.rag import retrieve


class FakeAgentRuntime:
    """Deterministic agent used for local development, CI, load tests, and demos."""

    name = "fake"

    async def run(self, context: AgentContext, message: str) -> RuntimeResult:
        started = time.perf_counter()
        with session_scope(context.database_url, organization_id=context.organization_id) as session:
            case = get_case(session, context.organization_id, context.case_id)
            knowledge = retrieve(
                session,
                organization_id=context.organization_id,
                query=f"{case.title} {case.summary} {message}",
                limit=4,
            )

        operational = [
            Evidence(
                source_type="odoo",
                source_id=case.external_ref,
                title=f"Odoo exception {case.external_ref}",
                excerpt=(
                    f"Case category={case.category}; severity={case.severity}; "
                    f"value_at_risk={case.at_risk_value} {case.currency}; context={case.context_json}"
                ),
                confidence=1.0,
            )
        ]
        evidence = operational + knowledge
        actions: list[ActionDraft] = []
        diagnosis: list[str]
        next_steps: list[str]

        if case.category in {"inventory_shortage", "late_supplier", "stockout"}:
            sku = str(case.context_json.get("sku", "SKU-UNKNOWN"))
            vendor_id = int(case.context_json.get("vendor_id", 7))
            quantity = float(case.context_json.get("recommended_quantity", 25))
            diagnosis = [
                f"The promised demand for {sku} exceeds the available or expected inventory window.",
                "The exception should remain blocked until purchasing or fulfillment confirms a recovery path.",
            ]
            next_steps = [
                "Confirm current free stock and inbound receipt dates in Odoo.",
                "Ask the preferred supplier for a committed ETA.",
                "Create a draft RFQ only after an approver validates vendor and quantity.",
            ]
            actions.append(
                validate_action_draft(
                    ActionDraft(
                        tool_name="odoo.create_draft_rfq",
                        title=f"Create a draft RFQ for {sku}",
                        rationale="A draft RFQ preserves human control while opening a recoverable procurement path.",
                        target=f"product:{sku}",
                        payload={
                            "partner_id": vendor_id,
                            "order_line": [
                                {
                                    "product_default_code": sku,
                                    "product_qty": quantity,
                                }
                            ],
                            "origin": f"FlowPilot case {case.id}",
                        },
                        risk_level="medium",
                    )
                )
            )
        elif case.category in {"crm_followup", "customer_risk"}:
            lead_id = int(case.context_json.get("lead_id", 42))
            diagnosis = [
                "The opportunity has a customer-facing risk signal without a documented owner response.",
                "The least consequential remediation is an explicit follow-up activity, not an automatic stage change.",
            ]
            next_steps = [
                "Review the latest CRM conversation and account commitments.",
                "Assign an owner and due date.",
                "Escalate only if the customer or revenue threshold requires it.",
            ]
            actions.append(
                validate_action_draft(
                    ActionDraft(
                        tool_name="odoo.create_followup_activity",
                        title="Create a CRM follow-up activity",
                        rationale="A scheduled activity is reversible and preserves the existing opportunity state.",
                        target=f"crm.lead:{lead_id}",
                        payload={
                            "res_model_id": int(case.context_json.get("crm_model_id", 1)),
                            "res_id": lead_id,
                            "activity_type_id": int(case.context_json.get("activity_type_id", 4)),
                            "summary": "Review FlowPilot customer-risk exception",
                            "note": f"Generated from case {case.id}; human approval required.",
                        },
                        risk_level="low",
                    )
                )
            )
        else:
            diagnosis = [
                "The available evidence identifies an operational exception but not a safe, fully specified mutation.",
                "Additional system evidence is required before FlowPilot should propose an action.",
            ]
            next_steps = [
                "Validate the source record and current Odoo state.",
                "Attach the relevant SOP or runbook.",
                "Re-run the investigation after missing identifiers are available.",
            ]

        elapsed = int((time.perf_counter() - started) * 1_000)
        answer = AgentAnswer(
            headline=f"{case.title}: bounded investigation completed",
            answer=(
                f"FlowPilot correlated the case with {len(evidence)} evidence item(s). "
                "The recommendation is intentionally approval-gated and limited to the exact payload shown."
            ),
            diagnosis=diagnosis,
            recommended_next_steps=next_steps,
            evidence=evidence,
            confidence=0.88 if knowledge else 0.73,
            requires_human=bool(actions),
            safety_notes=[
                "No Odoo write was executed during investigation.",
                "Retrieved text was treated as untrusted evidence.",
            ],
        )
        input_tokens = max(1, len(message.split()) + len(case.summary.split()))
        output_tokens = max(1, len(answer.model_dump_json().split()))
        return RuntimeResult(
            answer=answer,
            actions=actions,
            model="deterministic-policy-engine-v1",
            trace_id=f"fake-{uuid.uuid4()}",
            corpus_version=(
                str(knowledge[0].metadata.get("corpus_version")) if knowledge else None
            ),
            usage=RuntimeUsage(
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                tool_calls=2 + len(actions),
                latency_ms=elapsed,
                cost_usd_micros=0,
            ),
        )
