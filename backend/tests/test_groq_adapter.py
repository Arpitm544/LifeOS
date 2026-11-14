import asyncio
import json
from types import SimpleNamespace

import httpx
import pytest

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
        groq_model='openai/gpt-oss-20b', anthropic_api_key='anthropic-test-key', llm_timeout_seconds=8))
    assert isinstance(llm_client.configured_llm(), llm_client.GroqLLMClient)


@pytest.mark.parametrize('data', [{}, {'choices': []}, {'choices': [None]},
    {'choices': ['invalid']}, {'choices': [{}]}, {'choices': [{'message': None}]},
    {'choices': [{'message': 'invalid'}]}])
@pytest.mark.parametrize('method', ['parse', 'write'])
def test_groq_rejects_malformed_response(monkeypatch, data, method):
    client = llm_client.GroqLLMClient('test-only-key', 'test-model')

    async def respond(body):
        return data

    monkeypatch.setattr(client, '_post', respond)
    request = client.parse(text='Report', context={}) if method == 'parse' else client.write(system='', payload={})
    with pytest.raises(ValueError, match='Malformed Groq response'):
        asyncio.run(request)


@pytest.mark.parametrize('client_type,status', [
    (llm_client.AnthropicLLMClient, 429), (llm_client.AnthropicLLMClient, 529),
    (llm_client.GroqLLMClient, 429), (llm_client.GroqLLMClient, 503)])
def test_provider_retries_once(monkeypatch, client_type, status):
    requests = []

    def respond(request):
        requests.append(request)
        return httpx.Response(status if len(requests) == 1 else 200, json={'ok': True})

    real_client = httpx.AsyncClient
    monkeypatch.setattr(httpx, 'AsyncClient', lambda **kwargs:
        real_client(transport=httpx.MockTransport(respond), **kwargs))
    client = client_type('test-only-key', 'test-model')
    assert asyncio.run(client._post({})) == {'ok': True}
    assert len(requests) == 2
    if client_type is llm_client.AnthropicLLMClient:
        assert str(requests[0].url) == llm_client.ANTHROPIC_URL
        assert requests[0].headers['x-api-key'] == 'test-only-key'
        assert requests[0].headers['anthropic-version'] == '2023-06-01'
    else:
        assert requests[0].headers['Authorization'] == 'Bearer test-only-key'
