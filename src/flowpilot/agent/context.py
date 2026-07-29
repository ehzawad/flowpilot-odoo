from __future__ import annotations

from dataclasses import dataclass

from flowpilot.config import Settings


@dataclass(slots=True)
class AgentContext:
    organization_id: str
    case_id: str
    user_id: str
    database_url: str
    settings: Settings
