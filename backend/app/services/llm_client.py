from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .nlu_validator import ToolCall


@dataclass(frozen=True)
class LLMResponse:
    reply: str
    spoken_reply: str
    tool_calls: list[ToolCall]


class LLMClient(Protocol):
    async def parse(self, *, text: str, context: dict) -> LLMResponse: ...


class FallbackLLMClient:
    """Deterministic adapter used when Anthropic is unavailable."""

    async def parse(self, *, text: str, context: dict) -> LLMResponse:
        return LLMResponse(
            reply="I could not interpret that fully, so I kept it in quick-add mode.",
            spoken_reply="I kept that in quick add mode.",
            tool_calls=[],
        )

