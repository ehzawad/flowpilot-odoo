from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select

from flowpilot.config import Settings, get_settings
from flowpilot.db.base import create_schema, session_scope
from flowpilot.db.models import Integration, Membership, Organization, User
from flowpilot.schemas import CaseCreate, KnowledgeDocumentCreate
from flowpilot.services.cases import create_case
from flowpilot.services.rag import ingest_document


def seed_demo(settings: Settings | None = None) -> dict[str, int]:
    active = settings or get_settings()
    if active.auto_create_schema:
        create_schema(active.database_url)
    counts = {"organizations": 0, "users": 0, "cases": 0, "documents": 0}
    with session_scope(active.database_url, organization_id=active.demo_tenant_id) as session:
        organization = session.get(Organization, active.demo_tenant_id)
        if not organization:
            organization = Organization(
                id=active.demo_tenant_id,
                slug="northstar-distribution",
                name="Northstar Distribution",
                plan="pilot",
                settings_json={"currency": "USD", "timezone": "America/Denver"},
            )
            session.add(organization)
            counts["organizations"] += 1
        user = session.get(User, active.demo_user_id)
        if not user:
            user = User(
                id=active.demo_user_id,
                external_subject=active.demo_user_id,
                email=active.demo_user_email,
                display_name="Maya Chen",
            )
            session.add(user)
            counts["users"] += 1
            session.flush()
        membership = session.scalar(
            select(Membership).where(
                Membership.organization_id == active.demo_tenant_id,
                Membership.user_id == active.demo_user_id,
            )
        )
        if not membership:
            session.add(
                Membership(
                    organization_id=active.demo_tenant_id,
                    user_id=active.demo_user_id,
                    role="approver",
                )
            )
        integrations = [
            ("odoo", "Odoo 19 ERP", "configured"),
            ("supplier_mcp", "Acme supplier portal", "configured"),
            ("knowledge", "Operations SOP corpus", "healthy"),
        ]
        for kind, name, status in integrations:
            existing = session.scalar(
                select(Integration).where(
                    Integration.organization_id == active.demo_tenant_id,
                    Integration.kind == kind,
                    Integration.external_account_id == "default",
                )
            )
            if not existing:
                session.add(
                    Integration(
                        organization_id=active.demo_tenant_id,
                        kind=kind,
                        display_name=name,
                        external_account_id="default",
                        status=status,
                        last_synced_at=datetime.now(UTC),
                    )
                )

        cases = [
            CaseCreate(
                title="Sensor X9 stockout threatens order S042",
                summary=(
                    "Odoo shows only four free units while the committed order requires 22 units "
                    "before the next confirmed supplier receipt."
                ),
                category="inventory_shortage",
                severity="high",
                source="odoo",
                external_ref="sale.order:1042",
                at_risk_value=Decimal("48500"),
                context_json={
                    "sale_order_id": 1042,
                    "sku": "SENSOR-X9",
                    "required_quantity": 22,
                    "available_quantity": 4,
                    "recommended_quantity": 25,
                    "vendor_id": 77,
                },
            ),
            CaseCreate(
                title="Late supplier receipt for purchase order P00801",
                summary="The promised receipt date passed two days ago and no carrier ETA is recorded.",
                category="late_supplier",
                severity="medium",
                source="odoo",
                external_ref="purchase.order:801",
                at_risk_value=Decimal("21700"),
                context_json={
                    "purchase_order_id": 801,
                    "sku": "SENSOR-X9",
                    "vendor_id": 77,
                    "recommended_quantity": 25,
                },
            ),
            CaseCreate(
                title="Northstar renewal needs an owner follow-up",
                summary="A high-value CRM opportunity has no next activity after a customer-risk signal.",
                category="customer_risk",
                severity="medium",
                source="odoo",
                external_ref="crm.lead:42",
                at_risk_value=Decimal("75000"),
                context_json={"lead_id": 42, "crm_model_id": 1, "activity_type_id": 4},
            ),
        ]
        for item in cases:
            before = session.scalar(
                select(Organization.id).where(Organization.id == active.demo_tenant_id)
            )
            del before
            existing_case = create_case(
                session,
                organization_id=active.demo_tenant_id,
                request=item,
            )
            if existing_case.created_at == existing_case.updated_at:
                counts["cases"] += 1

        documents = [
            KnowledgeDocumentCreate(
                title="Inventory shortage response SOP",
                source="seed",
                external_ref="sop:inventory-shortage:v1",
                content="""
When free stock cannot satisfy a committed sale order, verify the current reservation, inbound
receipts, and substitute products. Do not confirm a new purchase order automatically. The system
may create a draft request for quotation after a human validates the preferred vendor, quantity,
and customer commitment. Customer communication must state uncertainty rather than promise an
unverified delivery date.
""".strip(),
            ),
            KnowledgeDocumentCreate(
                title="Supplier delay escalation runbook",
                source="seed",
                external_ref="runbook:supplier-delay:v1",
                content="""
For a late purchase order, obtain a carrier or supplier ETA and compare it with customer
commitments. Escalate to procurement when value at risk exceeds USD 10,000 or when no credible ETA
exists. Preserve the original purchase order; remediation begins with evidence gathering and a
draft plan.
""".strip(),
            ),
            KnowledgeDocumentCreate(
                title="CRM customer-risk policy",
                source="seed",
                external_ref="policy:crm-risk:v1",
                content="""
Customer-risk signals require an assigned human owner. The safest first action is a scheduled CRM
activity with a clear due date and context. An AI system must not change opportunity stage,
probability, discount, or contractual commitments without explicit human approval.
""".strip(),
            ),
        ]
        for document in documents:
            result = ingest_document(
                session,
                organization_id=active.demo_tenant_id,
                request=document,
            )
            if result.chunk_count:
                counts["documents"] += 1
    return counts


def main() -> None:
    print(seed_demo())


if __name__ == "__main__":
    main()
