from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from typing import Any, TypeVar

from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from flowpilot.db.base import session_scope
from flowpilot.db.models import AgentMemoryItem, AgentMemorySession, utcnow

try:
    from agents.items import TResponseInputItem
    from agents.memory.session import Session
except ImportError:  # lets the deterministic path run without the optional SDK imported
    TResponseInputItem = dict[str, Any]  # type: ignore[misc,assignment]

    class Session:  # type: ignore[no-redef]
        pass

T = TypeVar("T")


class TenantAgentSession(Session):
    """Agents SDK session whose rows are tenant-owned and protected by product RLS policies."""

    session_settings = None

    def __init__(
        self,
        *,
        session_id: str,
        organization_id: str,
        case_id: str,
        user_id: str,
        database_url: str,
    ) -> None:
        self.session_id = session_id
        self.organization_id = organization_id
        self.case_id = case_id
        self.user_id = user_id
        self.database_url = database_url

    async def get_items(self, limit: int | None = None) -> list[TResponseInputItem]:
        def operation() -> list[TResponseInputItem]:
            with session_scope(self.database_url, organization_id=self.organization_id) as db:
                statement = select(AgentMemoryItem.message_data).where(
                    AgentMemoryItem.organization_id == self.organization_id,
                    AgentMemoryItem.session_id == self.session_id,
                )
                if limit is None:
                    statement = statement.order_by(
                        AgentMemoryItem.created_at.asc(), AgentMemoryItem.id.asc()
                    )
                    rows = list(db.scalars(statement))
                else:
                    statement = statement.order_by(
                        AgentMemoryItem.created_at.desc(), AgentMemoryItem.id.desc()
                    ).limit(max(0, limit))
                    rows = list(db.scalars(statement))
                    rows.reverse()
                items: list[TResponseInputItem] = []
                for value in rows:
                    try:
                        items.append(json.loads(value))
                    except json.JSONDecodeError:
                        continue
                return items

        return await self._run(operation)

    async def add_items(self, items: list[TResponseInputItem]) -> None:
        if not items:
            return
        serialized = [
            json.dumps(item, ensure_ascii=False, separators=(",", ":")) for item in items
        ]

        def operation() -> None:
            with session_scope(self.database_url, organization_id=self.organization_id) as db:
                values = {
                    "session_id": self.session_id,
                    "organization_id": self.organization_id,
                    "case_id": self.case_id,
                    "user_id": self.user_id,
                    "updated_at": utcnow(),
                }
                dialect = db.bind.dialect.name if db.bind else ""
                if dialect == "postgresql":
                    db.execute(
                        postgresql_insert(AgentMemorySession)
                        .values(**values)
                        .on_conflict_do_nothing(index_elements=["session_id"])
                    )
                elif dialect == "sqlite":
                    db.execute(
                        sqlite_insert(AgentMemorySession)
                        .values(**values)
                        .on_conflict_do_nothing(index_elements=["session_id"])
                    )
                elif db.get(AgentMemorySession, self.session_id) is None:
                    db.add(AgentMemorySession(**values))
                db.add_all(
                    AgentMemoryItem(
                        organization_id=self.organization_id,
                        session_id=self.session_id,
                        message_data=value,
                    )
                    for value in serialized
                )
                db.execute(
                    update(AgentMemorySession)
                    .where(
                        AgentMemorySession.session_id == self.session_id,
                        AgentMemorySession.organization_id == self.organization_id,
                    )
                    .values(updated_at=utcnow())
                )

        await self._run(operation)

    async def pop_item(self) -> TResponseInputItem | None:
        def operation() -> TResponseInputItem | None:
            with session_scope(self.database_url, organization_id=self.organization_id) as db:
                statement = (
                    select(AgentMemoryItem)
                    .where(
                        AgentMemoryItem.organization_id == self.organization_id,
                        AgentMemoryItem.session_id == self.session_id,
                    )
                    .order_by(AgentMemoryItem.created_at.desc(), AgentMemoryItem.id.desc())
                    .limit(1)
                )
                if db.bind and db.bind.dialect.name == "postgresql":
                    statement = statement.with_for_update()
                row = db.scalar(statement)
                if row is None:
                    return None
                db.delete(row)
                try:
                    return json.loads(row.message_data)
                except json.JSONDecodeError:
                    return None

        return await self._run(operation)

    async def clear_session(self) -> None:
        def operation() -> None:
            with session_scope(self.database_url, organization_id=self.organization_id) as db:
                db.execute(
                    delete(AgentMemoryItem).where(
                        AgentMemoryItem.organization_id == self.organization_id,
                        AgentMemoryItem.session_id == self.session_id,
                    )
                )
                db.execute(
                    update(AgentMemorySession)
                    .where(
                        AgentMemorySession.organization_id == self.organization_id,
                        AgentMemorySession.session_id == self.session_id,
                    )
                    .values(updated_at=utcnow())
                )

        await self._run(operation)

    async def _run(self, operation: Callable[[], T]) -> T:
        return await asyncio.to_thread(operation)
