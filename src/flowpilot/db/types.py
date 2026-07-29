from __future__ import annotations

from typing import Any

from sqlalchemy import JSON
from sqlalchemy.engine import Dialect
from sqlalchemy.types import TypeDecorator, TypeEngine


class VectorType(TypeDecorator[list[float]]):
    """Use pgvector on PostgreSQL and JSON elsewhere for a zero-infrastructure demo."""

    impl = JSON
    cache_ok = True

    def __init__(self, dimensions: int) -> None:
        super().__init__()
        self.dimensions = dimensions

    def load_dialect_impl(self, dialect: Dialect) -> TypeEngine[Any]:
        if dialect.name == "postgresql":
            try:
                from pgvector.sqlalchemy import Vector

                return dialect.type_descriptor(Vector(self.dimensions))
            except ImportError:  # pragma: no cover - dependency is installed in production
                return dialect.type_descriptor(JSON())
        return dialect.type_descriptor(JSON())
