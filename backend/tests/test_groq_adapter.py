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


def _settings(**values):
    return SimpleNamespace(llm_timeout_seconds=8, **values)


@pytest.mark.parametrize('values,provider,url_part,model', [
    ({'xai_api_key': 'k'}, 'XAI', 'api.x.ai', 'grok-4'),
    ({'openai_api_key': 'k', 'openai_model': 'gpt-x'}, 'Openai', 'api.openai.com', 'gpt-x'),
    ({'gemini_api_key': 'k'}, 'Gemini', 'generativelanguage.googleapis.com', 'gemini-3.5-flash'),
    ({'openrouter_api_key': 'k'}, 'Openrouter', 'openrouter.ai', 'openai/gpt-4o-mini'),
    ({'llm_api_key': 'k', 'llm_base_url': 'http://localhost:11434/v1', 'llm_model': 'llama3'}, 'Custom',
     'localhost:11434/v1/chat/completions', 'llama3'),
])
def test_any_provider_key_selects_a_chat_client(monkeypatch, values, provider, url_part, model):
    from app import config
    monkeypatch.setattr(config, 'get_settings', lambda: _settings(**values))
    client = llm_client.configured_llm()
    assert isinstance(client, llm_client.OpenAICompatibleLLMClient)
    assert client.provider == provider and url_part in client.url and client.model == model


def test_anthropic_key_and_no_key(monkeypatch):
    from app import config
    monkeypatch.setattr(config, 'get_settings', lambda: _settings(anthropic_api_key='k'))
    assert type(llm_client.configured_llm()) is llm_client.AnthropicLLMClient
    monkeypatch.setattr(config, 'get_settings', lambda: _settings())
    assert isinstance(llm_client.configured_llm(), llm_client.FallbackLLMClient)
    # A custom key without an endpoint and model is not usable.
    monkeypatch.setattr(config, 'get_settings', lambda: _settings(llm_api_key='k'))
    assert isinstance(llm_client.configured_llm(), llm_client.FallbackLLMClient)


def test_llm_provider_overrides_auto_order(monkeypatch):
    from app import config
    both = dict(groq_api_key='g', xai_api_key='x')
    monkeypatch.setattr(config, 'get_settings', lambda: _settings(**both))
    assert llm_client.configured_llm().provider == 'Groq'
    monkeypatch.setattr(config, 'get_settings', lambda: _settings(llm_provider='grok', **both))
    assert llm_client.configured_llm().provider == 'XAI'
    monkeypatch.setattr(config, 'get_settings', lambda: _settings(llm_provider='nope', **both))
    with pytest.raises(ValueError, match='Unknown LLM_PROVIDER'):
        llm_client.configured_llm()


@pytest.mark.parametrize('raw,expected', [('{"title":"A"}', {'title': 'A'}), ('', {}), (None, {}), ({'title': 'B'}, {'title': 'B'})])
def test_tool_arguments_are_normalised(raw, expected):
    assert llm_client.GroqLLMClient('k', 'm')._arguments(raw) == expected
