from __future__ import annotations

import asyncio
import json
import logging
import time
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated, Any

from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import ORJSONResponse, StreamingResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from flowpilot.api.deps import actor_dependency, db_dependency, settings_dependency
from flowpilot.config import Settings, get_settings
from flowpilot.db.base import create_schema, session_scope
from flowpilot.db.models import (
    ActionProposal,
    AgentRun,
    Case,
    CaseEvent,
    InboxEvent,
    Integration,
    Job,
    UsageRecord,
)
from flowpilot.schemas import (
    ActionProposalView,
    Actor,
    AgentAnswer,
    AgentRunResponse,
    ApprovalDecisionRequest,
    ApprovalDecisionResponse,
    CaseCreate,
    CaseEventView,
    CaseView,
    DashboardSummary,
    IntegrationView,
    InvestigationRequest,
    JobView,
    KnowledgeDocumentCreate,
    KnowledgeDocumentView,
    OdooWebhookEnvelope,
    UsageSummary,
    WebhookAccepted,
)
from flowpilot.security import verify_webhook
from flowpilot.services.agent_runs import AgentRunNotFoundError, get_agent_run
from flowpilot.services.approvals import ApprovalError, decide_action, list_pending_actions
from flowpilot.services.cases import (
    CaseNotFoundError,
    create_case,
    dashboard_counts,
    get_case,
    list_cases,
)
from flowpilot.services.jobs import JobNotFoundError, enqueue_job, get_job
from flowpilot.services.rag import ingest_document, retrieve
from flowpilot.scripts.seed_demo import seed_demo
from flowpilot.telemetry.metrics import HTTP_LATENCY, HTTP_REQUESTS
from flowpilot.worker.main import run_once

LOGGER = logging.getLogger("flowpilot.api")
DB = Annotated[Session, Depends(db_dependency)]
CURRENT_ACTOR = Annotated[Actor, Depends(actor_dependency)]
APP_SETTINGS = Annotated[Settings, Depends(settings_dependency)]


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings = get_settings()
    logging.basicConfig(level=settings.log_level)
    if settings.auto_create_schema:
        create_schema(settings.database_url)
    if settings.seed_demo_data:
        seed_demo(settings)
    yield


app = FastAPI(
    title="FlowPilot API",
    version="0.1.0",
    default_response_class=ORJSONResponse,
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[get_settings().public_app_url, "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def metrics_middleware(request: Request, call_next: Any) -> Response:
    started = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        HTTP_REQUESTS.labels(request.method, request.url.path, "500").inc()
        HTTP_LATENCY.labels(request.method, request.url.path).observe(time.perf_counter() - started)
        raise
    HTTP_REQUESTS.labels(request.method, request.url.path, str(response.status_code)).inc()
    HTTP_LATENCY.labels(request.method, request.url.path).observe(time.perf_counter() - started)
    response.headers["X-Request-Duration-Ms"] = str(int((time.perf_counter() - started) * 1_000))
    return response


@app.exception_handler(CaseNotFoundError)
async def case_not_found(_: Request, exc: CaseNotFoundError) -> ORJSONResponse:
    return ORJSONResponse(status_code=404, content={"detail": f"Case not found: {exc}"})


@app.exception_handler(JobNotFoundError)
async def job_not_found(_: Request, exc: JobNotFoundError) -> ORJSONResponse:
    return ORJSONResponse(status_code=404, content={"detail": f"Job not found: {exc}"})


@app.exception_handler(AgentRunNotFoundError)
async def run_not_found(_: Request, exc: AgentRunNotFoundError) -> ORJSONResponse:
    return ORJSONResponse(status_code=404, content={"detail": f"Agent run not found: {exc}"})


@app.exception_handler(ApprovalError)
async def approval_error(_: Request, exc: ApprovalError) -> ORJSONResponse:
    return ORJSONResponse(status_code=409, content={"detail": str(exc)})


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/ready")
def ready(settings: APP_SETTINGS) -> dict[str, str]:
    with session_scope(settings.database_url) as session:
        session.execute(text("SELECT 1"))
    return {"status": "ready"}


@app.get("/metrics", include_in_schema=False)
def metrics(settings: APP_SETTINGS) -> Response:
    if not settings.prometheus_enabled:
        raise HTTPException(status_code=404)
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.get("/v1/dashboard", response_model=DashboardSummary)
def dashboard(db: DB, actor: CURRENT_ACTOR) -> DashboardSummary:
    open_cases, critical, at_risk = dashboard_counts(db, actor.tenant_id)
    pending = int(
        db.scalar(
            select(func.count()).select_from(ActionProposal).where(
                ActionProposal.organization_id == actor.tenant_id,
                ActionProposal.approval_status == "pending",
            )
        )
        or 0
    )
    return DashboardSummary(
        open_cases=open_cases,
        critical_cases=critical,
        pending_approvals=pending,
        at_risk_value=at_risk,
    )


@app.get("/v1/cases", response_model=list[CaseView])
def cases(db: DB, actor: CURRENT_ACTOR, include_closed: bool = False) -> list[Case]:
    return list_cases(db, actor.tenant_id, include_closed=include_closed)


@app.post("/v1/cases", response_model=CaseView, status_code=201)
def add_case(request: CaseCreate, db: DB, actor: CURRENT_ACTOR) -> Case:
    return create_case(db, organization_id=actor.tenant_id, request=request)


@app.get("/v1/cases/{case_id}", response_model=CaseView)
def case_detail(case_id: str, db: DB, actor: CURRENT_ACTOR) -> Case:
    return get_case(db, actor.tenant_id, case_id)


@app.get("/v1/cases/{case_id}/events", response_model=list[CaseEventView])
def case_events(case_id: str, db: DB, actor: CURRENT_ACTOR) -> list[CaseEvent]:
    get_case(db, actor.tenant_id, case_id)
    return list(
        db.scalars(
            select(CaseEvent)
            .where(
                CaseEvent.organization_id == actor.tenant_id,
                CaseEvent.case_id == case_id,
            )
            .order_by(CaseEvent.created_at.asc(), CaseEvent.id.asc())
        )
    )


@app.get("/v1/cases/{case_id}/events/stream")
async def case_event_stream(
    case_id: str,
    actor: CURRENT_ACTOR,
    settings: APP_SETTINGS,
    last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
) -> StreamingResponse:
    with session_scope(settings.database_url, organization_id=actor.tenant_id) as session:
        get_case(session, actor.tenant_id, case_id)

    async def generate():
        cursor = last_event_id
        for _ in range(300):
            with session_scope(settings.database_url, organization_id=actor.tenant_id) as session:
                statement = select(CaseEvent).where(
                    CaseEvent.organization_id == actor.tenant_id,
                    CaseEvent.case_id == case_id,
                )
                if cursor:
                    cursor_event = session.get(CaseEvent, cursor)
                    if cursor_event:
                        statement = statement.where(CaseEvent.created_at > cursor_event.created_at)
                events = list(session.scalars(statement.order_by(CaseEvent.created_at.asc())))
            for event in events:
                cursor = event.id
                payload = CaseEventView.model_validate(event).model_dump_json()
                yield f"id: {event.id}\nevent: {event.event_type}\ndata: {payload}\n\n"
            yield ": keepalive\n\n"
            await asyncio.sleep(1)

    return StreamingResponse(generate(), media_type="text/event-stream")


@app.post("/v1/cases/{case_id}/investigations", response_model=JobView, status_code=202)
async def investigate(
    case_id: str,
    request: InvestigationRequest,
    background_tasks: BackgroundTasks,
    db: DB,
    actor: CURRENT_ACTOR,
    settings: APP_SETTINGS,
) -> Job:
    get_case(db, actor.tenant_id, case_id)
    job = enqueue_job(
        db,
        organization_id=actor.tenant_id,
        job_type="run_agent_investigation",
        payload={
            "case_id": case_id,
            "message": request.message,
            "actor": actor.model_dump(),
        },
        idempotency_key=f"investigate:{actor.tenant_id}:{case_id}:{request.client_request_id}",
        priority=50,
        max_attempts=settings.worker_max_attempts,
    )
    if settings.inline_worker:
        background_tasks.add_task(run_once, "api-inline-worker")
    return job


@app.get("/v1/jobs/{job_id}", response_model=JobView)
def job_detail(job_id: str, db: DB, actor: CURRENT_ACTOR) -> Job:
    return get_job(db, actor.tenant_id, job_id)


@app.get("/v1/cases/{case_id}/agent-runs/{run_id}", response_model=AgentRunResponse)
def agent_run(case_id: str, run_id: str, db: DB, actor: CURRENT_ACTOR) -> AgentRunResponse:
    run, actions = get_agent_run(
        db,
        organization_id=actor.tenant_id,
        case_id=case_id,
        run_id=run_id,
    )
    tool_calls = int(
        db.scalar(
            select(func.coalesce(func.sum(UsageRecord.quantity), 0)).where(
                UsageRecord.organization_id == actor.tenant_id,
                UsageRecord.agent_run_id == run_id,
                UsageRecord.meter == "tool_calls",
            )
        )
        or 0
    )
    return AgentRunResponse(
        id=run.id,
        case_id=run.case_id,
        status=run.status,
        runtime=run.runtime,
        model=run.model,
        trace_id=run.trace_id,
        output=AgentAnswer.model_validate(run.output_json),
        actions=[ActionProposalView.model_validate(item) for item in actions],
        usage={
            "input_tokens": run.input_tokens,
            "output_tokens": run.output_tokens,
            "tool_calls": tool_calls,
            "latency_ms": run.latency_ms,
            "cost_usd": run.cost_usd_micros / 1_000_000,
        },
        created_at=run.created_at,
    )


@app.get("/v1/approvals", response_model=list[ActionProposalView])
def approvals(db: DB, actor: CURRENT_ACTOR) -> list[ActionProposal]:
    return list_pending_actions(db, actor.tenant_id)


@app.post("/v1/actions/{action_id}/decision", response_model=ApprovalDecisionResponse)
def action_decision(
    action_id: str,
    request: ApprovalDecisionRequest,
    db: DB,
    actor: CURRENT_ACTOR,
    settings: APP_SETTINGS,
) -> ApprovalDecisionResponse:
    action, job_id = decide_action(
        db,
        settings=settings,
        actor=actor,
        action_id=action_id,
        request=request,
    )
    return ApprovalDecisionResponse(
        action=ActionProposalView.model_validate(action),
        execution_job_id=job_id,
    )


@app.get("/v1/integrations", response_model=list[IntegrationView])
def integrations(db: DB, actor: CURRENT_ACTOR) -> list[Integration]:
    return list(
        db.scalars(
            select(Integration)
            .where(Integration.organization_id == actor.tenant_id)
            .order_by(Integration.kind.asc())
        )
    )


@app.get("/v1/usage", response_model=UsageSummary)
def usage(db: DB, actor: CURRENT_ACTOR) -> UsageSummary:
    runs = int(
        db.scalar(
            select(func.count()).select_from(AgentRun).where(
                AgentRun.organization_id == actor.tenant_id,
                AgentRun.status == "completed",
            )
        )
        or 0
    )
    totals = {
        meter: int(
            db.scalar(
                select(func.coalesce(func.sum(UsageRecord.quantity), 0)).where(
                    UsageRecord.organization_id == actor.tenant_id,
                    UsageRecord.meter == meter,
                )
            )
            or 0
        )
        for meter in ("input_tokens", "output_tokens", "tool_calls")
    }
    cost = int(
        db.scalar(
            select(func.coalesce(func.sum(UsageRecord.cost_usd_micros), 0)).where(
                UsageRecord.organization_id == actor.tenant_id
            )
        )
        or 0
    )
    return UsageSummary(
        agent_runs=runs,
        input_tokens=totals["input_tokens"],
        output_tokens=totals["output_tokens"],
        tool_calls=totals["tool_calls"],
        cost_usd=cost / 1_000_000,
    )


@app.post("/v1/knowledge/documents", response_model=KnowledgeDocumentView, status_code=201)
def add_document(
    request: KnowledgeDocumentCreate,
    db: DB,
    actor: CURRENT_ACTOR,
) -> KnowledgeDocumentView:
    result = ingest_document(db, organization_id=actor.tenant_id, request=request)
    return KnowledgeDocumentView(
        id=result.document.id,
        title=result.document.title,
        checksum=result.document.checksum,
        corpus_version=result.document.corpus_version,
        chunks=result.chunk_count,
    )


@app.get("/v1/knowledge/search")
def search_knowledge(
    q: Annotated[str, Query(min_length=2, max_length=2_000)],
    db: DB,
    actor: CURRENT_ACTOR,
    limit: int = Query(default=5, ge=1, le=20),
) -> list[dict[str, Any]]:
    return [
        item.model_dump(mode="json")
        for item in retrieve(db, organization_id=actor.tenant_id, query=q, limit=limit)
    ]


@app.post("/v1/webhooks/odoo", response_model=WebhookAccepted, status_code=202)
async def odoo_webhook(
    request: Request,
    settings: APP_SETTINGS,
    tenant_id: str = Header(alias="X-FlowPilot-Tenant"),
    timestamp: str | None = Header(default=None, alias="X-FlowPilot-Timestamp"),
    signature: str | None = Header(default=None, alias="X-FlowPilot-Signature"),
) -> WebhookAccepted:
    body = await request.body()
    if not verify_webhook(
        secret=settings.odoo_bridge_webhook_secret,
        body=body,
        timestamp_header=timestamp,
        signature_header=signature,
        max_age_seconds=settings.webhook_max_age_seconds,
    ):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")
    envelope = OdooWebhookEnvelope.model_validate_json(body)
    with session_scope(settings.database_url, organization_id=tenant_id) as db:
        existing = db.scalar(
            select(InboxEvent).where(
                InboxEvent.organization_id == tenant_id,
                InboxEvent.provider == "odoo",
                InboxEvent.external_event_id == envelope.event_id,
            )
        )
        if existing:
            return WebhookAccepted(
                accepted=True,
                duplicate=True,
                inbox_event_id=existing.id,
                case_id=existing.payload_json.get("case_id"),
                investigation_job_id=existing.payload_json.get("investigation_job_id"),
            )
        inbox = InboxEvent(
            organization_id=tenant_id,
            provider="odoo",
            external_event_id=envelope.event_id,
            event_type=envelope.event_type,
            payload_json=envelope.model_dump(mode="json"),
        )
        db.add(inbox)
        db.flush()
        payload = envelope.payload
        case = create_case(
            db,
            organization_id=tenant_id,
            request=CaseCreate(
                title=str(payload.get("title", envelope.event_type.replace("_", " ").title())),
                summary=str(payload.get("summary", "Odoo emitted an operational exception.")),
                category=str(payload.get("category", "operations_exception")),
                severity=str(payload.get("severity", "medium")),
                source="odoo",
                external_ref=str(payload.get("external_ref", envelope.event_id)),
                at_risk_value=Decimal(str(payload.get("at_risk_value", 0))),
                currency=str(payload.get("currency", "USD")),
                context_json=payload,
            ),
        )
        job: Job | None = None
        if settings.auto_investigate_odoo_events:
            system_actor = Actor(
                tenant_id=tenant_id,
                user_id="odoo-webhook",
                email=None,
                role="operator",
            )
            job = enqueue_job(
                db,
                organization_id=tenant_id,
                job_type="run_agent_investigation",
                payload={
                    "case_id": case.id,
                    "message": "Investigate the new Odoo exception and identify a safe next action.",
                    "actor": system_actor.model_dump(),
                },
                idempotency_key=f"webhook-investigation:{tenant_id}:{envelope.event_id}",
                max_attempts=settings.worker_max_attempts,
            )
        inbox.status = "processed"
        inbox.processed_at = datetime.now(UTC)
        inbox.payload_json = {
            **inbox.payload_json,
            "case_id": case.id,
            "investigation_job_id": job.id if job else None,
        }
        return WebhookAccepted(
            accepted=True,
            duplicate=False,
            inbox_event_id=inbox.id,
            case_id=case.id,
            investigation_job_id=job.id if job else None,
        )


def run() -> None:
    import uvicorn

    settings = get_settings()
    uvicorn.run("flowpilot.api.main:app", host="0.0.0.0", port=8000, reload=False)


if __name__ == "__main__":
    run()
