from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from flowpilot.db.models import Case, CaseEvent, utcnow
from flowpilot.schemas import CaseCreate


class CaseNotFoundError(LookupError):
    pass


def create_case(session: Session, *, organization_id: str, request: CaseCreate) -> Case:
    existing = session.scalar(
        select(Case).where(
            Case.organization_id == organization_id,
            Case.source == request.source,
            Case.external_ref == request.external_ref,
        )
    )
    if existing:
        return existing
    case = Case(organization_id=organization_id, **request.model_dump())
    session.add(case)
    session.flush()
    add_case_event(
        session,
        organization_id=organization_id,
        case_id=case.id,
        event_type="case.created",
        actor_type="system",
        message="Operational exception opened",
        payload={"source": case.source, "external_ref": case.external_ref},
    )
    return case


def list_cases(session: Session, organization_id: str, *, include_closed: bool = False) -> list[Case]:
    statement = select(Case).where(Case.organization_id == organization_id)
    if not include_closed:
        statement = statement.where(Case.status.not_in(["resolved", "closed"]))
    return list(session.scalars(statement.order_by(Case.updated_at.desc())))


def get_case(session: Session, organization_id: str, case_id: str) -> Case:
    case = session.scalar(
        select(Case)
        .options(selectinload(Case.events))
        .where(Case.id == case_id, Case.organization_id == organization_id)
    )
    if not case:
        raise CaseNotFoundError(case_id)
    return case


def add_case_event(
    session: Session,
    *,
    organization_id: str,
    case_id: str,
    event_type: str,
    actor_type: str,
    message: str,
    actor_id: str | None = None,
    payload: dict[str, Any] | None = None,
) -> CaseEvent:
    event = CaseEvent(
        organization_id=organization_id,
        case_id=case_id,
        event_type=event_type,
        actor_type=actor_type,
        actor_id=actor_id,
        message=message,
        payload_json=payload or {},
        created_at=utcnow(),
    )
    session.add(event)
    case = session.get(Case, case_id)
    if case:
        case.updated_at = event.created_at
    session.flush()
    return event


def dashboard_counts(session: Session, organization_id: str) -> tuple[int, int, Decimal]:
    rows = session.execute(
        select(Case.severity, Case.at_risk_value).where(
            Case.organization_id == organization_id,
            Case.status.not_in(["resolved", "closed"]),
        )
    ).all()
    open_cases = len(rows)
    critical = sum(1 for severity, _ in rows if severity in {"high", "critical"})
    total = sum((value or Decimal("0") for _, value in rows), Decimal("0"))
    return open_cases, critical, total


def case_event_count(session: Session, organization_id: str, case_id: str) -> int:
    return int(
        session.scalar(
            select(func.count()).select_from(CaseEvent).where(
                CaseEvent.organization_id == organization_id,
                CaseEvent.case_id == case_id,
            )
        )
        or 0
    )
