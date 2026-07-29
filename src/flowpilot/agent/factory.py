from __future__ import annotations

from flowpilot.agent.fake_runtime import FakeAgentRuntime
from flowpilot.agent.openai_runtime import OpenAIAgentRuntime
from flowpilot.agent.runtime import AgentRuntime
from flowpilot.config import Settings


def create_runtime(settings: Settings) -> AgentRuntime:
    if settings.agent_runtime == "openai":
        return OpenAIAgentRuntime()
    return FakeAgentRuntime()
