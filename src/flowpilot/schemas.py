from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Actor(BaseModel):
    tenant_id: str
    user_id: str
    email: str | None = None
    role: Literal["viewer", "operator", "approver", "admin"] = "operator"

    def can_approve(self) -> bool:
        return self.role in {"approver", "admin"}


class Evidence(BaseModel):
    source_type: str
    source_id: str
    title: str
    excerpt: str
    observed_at: datetime | None = None
    confidence: float = Field(default=1.0, ge=0, le=1)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ActionDraft(BaseModel):
    tool_name: str
    title: str
    rationale: str
    target: str
    payload: dict[str, Any]
    risk_level: Literal["low", "medium", "high"] = "medium"
    expires_in_minutes: int = Field(default=30, ge=1, le=1440)


class AgentAnswer(BaseModel):
    headline: str
    answer: str
    diagnosis: list[str] = Field(min_length=1)
    recommended_next_steps: list[str] = Field(min_length=1)
    evidence: list[Evidence] = Field(default_factory=list)
    confidence: float = Field(default=0.5, ge=0, le=1)
    requires_human: bool = True
    safety_notes: list[str] = Field(default_factory=list)


class CaseCreate(BaseModel):
    title: str = Field(min_length=3, max_length=500)
    summary: str = ""
    category: str = "operations_exception"
    severity: Literal["low", "medium", "high", "critical"] = "medium"
    source: str = "manual"
    external_ref: str
    at_risk_value: Decimal = Decimal("0")
    currency: str = "USD"
    context_json: dict[str, Any] = Field(default_factory=dict)


class CaseView(ORMModel):
    id: str
    organization_id: str
    title: str
    summary: str
    category: str
    severity: str
    status: str
    source: str
    external_ref: str
    at_risk_value: Decimal
    currency: str
    context_json: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class CaseEventView(ORMModel):
    id: str
    case_id: str
    event_type: str
    actor_type: str
    actor_id: str | None
    message: str
    payload_json: dict[str, Any]
    created_at: datetime


class IntegrationView(ORMModel):
    id: str
    kind: str
    display_name: str
    status: str
    external_account_id: str
    last_synced_at: datetime | None


class DashboardSummary(BaseModel):
    open_cases: int
    critical_cases: int
    pending_approvals: int
    at_risk_value: Decimal
    currency: str = "USD"


class UsageSummary(BaseModel):
    agent_runs: int
    input_tokens: int
    output_tokens: int
    tool_calls: int
    cost_usd: float


class InvestigationRequest(BaseModel):
    message: str = Field(min_length=3, max_length=20_000)
    client_request_id: str = Field(min_length=1, max_length=255)


class JobView(ORMModel):
    id: str
    organization_id: str
    job_type: str
    state: str
    attempts: int
    max_attempts: int
    available_at: datetime
    last_error: str | None
    result_json: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class ActionProposalView(ORMModel):
    id: str
    organization_id: str
    case_id: str
    agent_run_id: str | None
    tool_name: str
    title: str
    rationale: str
    target: str
    payload_json: dict[str, Any]
    payload_hash: str
    risk_level: str
    approval_status: str
    execution_status: str
    expires_at: datetime
    approved_by: str | None
    approved_at: datetime | None
    executed_at: datetime | None
    execution_result_json: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class ApprovalDecisionRequest(BaseModel):
    decision: Literal["approve", "reject"]
    expected_payload_hash: str = Field(min_length=64, max_length=64)
    reason: str | None = Field(default=None, max_length=2_000)


class ApprovalDecisionResponse(BaseModel):
    action: ActionProposalView
    execution_job_id: str | None = None


class AgentRunResponse(BaseModel):
    id: str
    case_id: str
    status: str
    runtime: str
    model: str
    trace_id: str | None
    output: AgentAnswer
    actions: list[ActionProposalView]
    usage: dict[str, int | float]
    created_at: datetime


class KnowledgeDocumentCreate(BaseModel):
    title: str
    content: str = Field(min_length=1, max_length=1_000_000)
    source: str = "upload"
    external_ref: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class KnowledgeDocumentView(BaseModel):
    id: str
    title: str
    checksum: str
    corpus_version: str
    chunks: int


class WebhookAccepted(BaseModel):
    accepted: bool
    duplicate: bool
    inbox_event_id: str
    case_id: str | None = None
    investigation_job_id: str | None = None


class OdooWebhookEnvelope(BaseModel):
    event_id: str
    event_type: str
    occurred_at: datetime
    database: str | None = None
    payload: dict[str, Any]

    @field_validator("event_id", "event_type")
    @classmethod
    def nonempty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be empty")
        return value
