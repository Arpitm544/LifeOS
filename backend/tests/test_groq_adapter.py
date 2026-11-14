import asyncio
import json
from types import SimpleNamespace

import httpx

from app.services import llm_client


def test_groq_tool_request_and_response(monkeypatch):
    seen = {}

    def respond(request):
        seen['url'] = str(request.url)
        seen['authorized'] = request.headers.get('Authorization') == 'Bearer test-only-key'
        body = json.loads(request.content)
        seen['tools'] = {tool['function']['name'] for tool in body['tools']}
        return httpx.Response(200, json={'model': 'openai/gpt-oss-20b',
            'choices': [{'message': {'content': 'I can add that.', 'tool_calls': [
                {'function': {'name': 'create_task', 'arguments': '{"title":"Report"}'}}]}}],
            'usage': {'prompt_tokens': 10, 'completion_tokens': 5}})

    transport = httpx.MockTransport(respond)
    real_client = httpx.AsyncClient
    monkeypatch.setattr(llm_client.httpx if hasattr(llm_client, 'httpx') else httpx,
        'AsyncClient', lambda **kwargs: real_client(transport=transport, **kwargs))
    client = llm_client.GroqLLMClient('test-only-key', 'openai/gpt-oss-20b')
    response = asyncio.run(client.parse(text='Create report', context={'timezone': 'UTC',
        'now': '2026-11-15T00:00:00Z', 'open_tasks': []}))
    assert response.tool_calls[0].name == 'create_task'
    assert response.tool_calls[0].arguments['title'] == 'Report'
    assert response.input_tokens == 10 and response.output_tokens == 5
    assert seen['authorized'] and seen['url'].endswith('/chat/completions')
    assert 'create_task' in seen['tools']


def test_groq_is_preferred_when_configured(monkeypatch):
    from app import config
    monkeypatch.setattr(config, 'get_settings', lambda: SimpleNamespace(groq_api_key='test-only-key',
        groq_model='openai/gpt-oss-20b', llm_timeout_seconds=8))
    assert isinstance(llm_client.configured_llm(), llm_client.GroqLLMClient)
