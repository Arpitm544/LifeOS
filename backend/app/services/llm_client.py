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



class AnthropicLLMClient:
    def __init__(self, api_key: str, model: str):
        self.api_key, self.model = api_key, model

    async def parse(self, *, text: str, context: dict) -> LLMResponse:
        import json
        import httpx
        from .nlu_validator import CreateTaskCall
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post('https://api.anthropic.com/v1/messages',
                headers={'x-api-key': self.api_key, 'anthropic-version': '2023-06-01'},
                json={'model': self.model, 'max_tokens': 1024,
                    'system': 'Help manage tasks. Use create_task only for an explicit task request. '
                              'Ask for clarification when needed. Context: ' + json.dumps(context),
                    'messages': [{'role': 'user', 'content': text}],
                    'tools': [{'name': 'create_task', 'description': 'Create a requested task',
                               'input_schema': CreateTaskCall.model_json_schema()}]})
            response.raise_for_status()
            content = response.json()['content']
        reply = '\n'.join(item['text'] for item in content if item['type'] == 'text')
        calls = [ToolCall(name=item['name'], arguments=item['input'])
                 for item in content if item['type'] == 'tool_use']
        return LLMResponse(reply, reply, calls)


def configured_llm():
    from ..config import get_settings
    settings = get_settings()
    return (AnthropicLLMClient(settings.anthropic_api_key, settings.anthropic_model)
            if settings.anthropic_api_key else FallbackLLMClient())
