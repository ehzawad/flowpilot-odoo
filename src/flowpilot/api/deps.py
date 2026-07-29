from __future__ import annotations

from collections.abc import Iterator

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from flowpilot.auth import actor_from_request
from flowpilot.config import Settings, get_settings
from flowpilot.db.base import session_scope
from flowpilot.schemas import Actor


def settings_dependency() -> Settings:
    return get_settings()


def actor_dependency(
    request: Request,
    settings: Settings = Depends(settings_dependency),
) -> Actor:
    return actor_from_request(request, settings)


def db_dependency(
    actor: Actor = Depends(actor_dependency),
    settings: Settings = Depends(settings_dependency),
) -> Iterator[Session]:
    with session_scope(settings.database_url, organization_id=actor.tenant_id) as session:
        yield session
