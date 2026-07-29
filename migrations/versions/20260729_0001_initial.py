"""Create the FlowPilot product schema and PostgreSQL tenant policies.

Revision ID: 20260729_0001
Revises: None
Create Date: 2026-07-29
"""
from __future__ import annotations

from alembic import op

from flowpilot.db.base import Base
from flowpilot.db import models  # noqa: F401

revision = "20260729_0001"
down_revision = None
branch_labels = None
depends_on = None

TENANT_TABLES = [
    "memberships",
    "integrations",
    "cases",
    "case_events",
    "agent_runs",
    "action_proposals",
    "approval_decisions",
    "documents",
    "document_chunks",
    "inbox_events",
    "outbox_events",
    "jobs",
    "usage_records",
    "agent_memory_sessions",
    "agent_memory_items",
]


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    Base.metadata.create_all(bind=bind)
    if bind.dialect.name == "postgresql":
        for table in TENANT_TABLES:
            op.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY')
            op.execute(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY')
            op.execute(
                f'''CREATE POLICY tenant_isolation ON "{table}"
                USING (organization_id = current_setting('app.current_organization_id', true))
                WITH CHECK (organization_id = current_setting('app.current_organization_id', true))'''
            )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        for table in TENANT_TABLES:
            op.execute(f'DROP POLICY IF EXISTS tenant_isolation ON "{table}"')
    Base.metadata.drop_all(bind=bind)
