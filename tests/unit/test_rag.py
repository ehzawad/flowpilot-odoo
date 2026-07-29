from __future__ import annotations

from flowpilot.db.base import session_scope
from flowpilot.schemas import KnowledgeDocumentCreate
from flowpilot.services.rag import deterministic_embedding, ingest_document, retrieve


def test_embedding_is_deterministic_and_normalized() -> None:
    first = deterministic_embedding("inventory shortage sensor x9")
    second = deterministic_embedding("inventory shortage sensor x9")
    assert first == second
    assert abs(sum(value * value for value in first) - 1.0) < 1e-6


def test_retrieval_is_tenant_scoped(settings) -> None:
    with session_scope(settings.database_url, organization_id=settings.demo_tenant_id) as session:
        evidence = retrieve(
            session,
            organization_id=settings.demo_tenant_id,
            query="draft RFQ inventory shortage",
            limit=3,
        )
        assert evidence
        assert any("Inventory" in item.title for item in evidence)
        other = retrieve(session, organization_id="different-tenant", query="inventory", limit=3)
        assert other == []


def test_ingest_is_idempotent(settings) -> None:
    request = KnowledgeDocumentCreate(
        title="A policy",
        content="Never execute a destructive action without approval.",
        source="test",
        external_ref="policy:1",
    )
    with session_scope(settings.database_url, organization_id=settings.demo_tenant_id) as session:
        first = ingest_document(session, organization_id=settings.demo_tenant_id, request=request)
        second = ingest_document(session, organization_id=settings.demo_tenant_id, request=request)
        assert first.document.id == second.document.id
        assert second.chunk_count == first.chunk_count
