from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from flowpilot.db.models import Document, DocumentChunk
from flowpilot.schemas import Evidence, KnowledgeDocumentCreate

EMBEDDING_DIMENSIONS = 32


@dataclass(slots=True)
class IngestResult:
    document: Document
    chunk_count: int


def deterministic_embedding(text: str, dimensions: int = EMBEDDING_DIMENSIONS) -> list[float]:
    """Hashing embedding used for tests and the no-key demo.

    It is intentionally simple but deterministic, tenant-safe, and sufficient to exercise
    ingestion, ranking, evaluation, and database scaling paths without paid model calls.
    """

    vector = [0.0] * dimensions
    for token in re.findall(r"[a-z0-9_\-]+", text.lower()):
        digest = hashlib.sha256(token.encode()).digest()
        index = int.from_bytes(digest[:4], "big") % dimensions
        sign = 1.0 if digest[4] % 2 == 0 else -1.0
        vector[index] += sign * (1.0 + min(len(token), 12) / 12)
    norm = math.sqrt(sum(value * value for value in vector)) or 1.0
    return [value / norm for value in vector]


def _cosine(left: list[float], right: list[float]) -> float:
    return sum(a * b for a, b in zip(left, right, strict=False))


def chunk_text(content: str, *, target_chars: int = 900, overlap_chars: int = 120) -> list[str]:
    paragraphs = [item.strip() for item in re.split(r"\n\s*\n", content) if item.strip()]
    chunks: list[str] = []
    current = ""
    for paragraph in paragraphs:
        if len(current) + len(paragraph) + 2 <= target_chars:
            current = f"{current}\n\n{paragraph}".strip()
            continue
        if current:
            chunks.append(current)
        if len(paragraph) <= target_chars:
            current = paragraph
            continue
        start = 0
        while start < len(paragraph):
            chunks.append(paragraph[start : start + target_chars])
            start += max(1, target_chars - overlap_chars)
        current = ""
    if current:
        chunks.append(current)
    return chunks or [content]


def ingest_document(
    session: Session,
    *,
    organization_id: str,
    request: KnowledgeDocumentCreate,
) -> IngestResult:
    checksum = hashlib.sha256(request.content.encode()).hexdigest()
    corpus_version = checksum[:16]
    existing = session.scalar(
        select(Document).where(
            Document.organization_id == organization_id,
            Document.source == request.source,
            Document.external_ref == request.external_ref,
        )
    )
    if existing and existing.checksum == checksum:
        count = len(
            list(session.scalars(select(DocumentChunk.id).where(DocumentChunk.document_id == existing.id)))
        )
        return IngestResult(existing, count)
    if existing:
        for chunk in session.scalars(
            select(DocumentChunk).where(DocumentChunk.document_id == existing.id)
        ):
            session.delete(chunk)
        existing.title = request.title
        existing.checksum = checksum
        existing.corpus_version = corpus_version
        existing.metadata_json = request.metadata
        document = existing
    else:
        document = Document(
            organization_id=organization_id,
            title=request.title,
            source=request.source,
            external_ref=request.external_ref,
            checksum=checksum,
            corpus_version=corpus_version,
            metadata_json=request.metadata,
        )
        session.add(document)
        session.flush()
    chunks = chunk_text(request.content)
    for index, content in enumerate(chunks):
        session.add(
            DocumentChunk(
                organization_id=organization_id,
                document_id=document.id,
                chunk_index=index,
                content=content,
                token_count=max(1, len(content.split())),
                embedding=deterministic_embedding(content),
                search_text=content.lower(),
                metadata_json={"title": request.title, **request.metadata},
            )
        )
    session.flush()
    return IngestResult(document, len(chunks))


def retrieve(
    session: Session,
    *,
    organization_id: str,
    query: str,
    limit: int = 5,
) -> list[Evidence]:
    query_vector = deterministic_embedding(query)
    query_terms = set(re.findall(r"[a-z0-9_\-]+", query.lower()))
    rows = session.execute(
        select(DocumentChunk, Document)
        .join(Document, Document.id == DocumentChunk.document_id)
        .where(DocumentChunk.organization_id == organization_id)
    ).all()
    ranked: list[tuple[float, DocumentChunk, Document]] = []
    for chunk, document in rows:
        semantic = _cosine(query_vector, list(chunk.embedding or []))
        words = set(re.findall(r"[a-z0-9_\-]+", chunk.search_text))
        lexical = len(query_terms & words) / max(1, len(query_terms))
        ranked.append((0.7 * semantic + 0.3 * lexical, chunk, document))
    ranked.sort(key=lambda item: item[0], reverse=True)
    return [
        Evidence(
            source_type="knowledge",
            source_id=chunk.id,
            title=document.title,
            excerpt=chunk.content[:700],
            confidence=max(0.0, min(1.0, (score + 1) / 2)),
            metadata={
                "document_id": document.id,
                "chunk_index": chunk.chunk_index,
                "corpus_version": document.corpus_version,
            },
        )
        for score, chunk, document in ranked[:limit]
        if score > -0.25
    ]
