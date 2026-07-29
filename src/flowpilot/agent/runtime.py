from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from flowpilot.agent.context import AgentContext
from flowpilot.schemas import ActionDraft, AgentAnswer


@dataclass(slots=True)
class RuntimeUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    tool_calls: int = 0
    latency_ms: int = 0
    cost_usd_micros: int = 0


@dataclass(slots=True)
class RuntimeResult:
    answer: AgentAnswer
    actions: list[ActionDraft] = field(default_factory=list)
    model: str = "deterministic-policy-engine"
    trace_id: str | None = None
    corpus_version: str | None = None
    usage: RuntimeUsage = field(default_factory=RuntimeUsage)


class AgentRuntime(Protocol):
    name: str

    async def run(self, context: AgentContext, message: str) -> RuntimeResult: ...
