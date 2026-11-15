"""Photo import: image validation, vision request shapes, vision model selection, extraction and the endpoint."""
import asyncio
import base64
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.ext.compiler import compiles

from app.models import Base
from app.services import llm_client
from app.services import syllabus_import as si

NOW = datetime(2026, 11, 15, 12, 0, tzinfo=timezone.utc)
JPEG = b'\xff\xd8\xff\xe0' + b'\x00' * 32
PNG = b'\x89PNG\r\n\x1a\n' + b'\x00' * 32
WEBP = b'RIFF\x24\x00\x00\x00WEBPVP8 ' + b'\x00' * 32
b64 = lambda data: base64.b64encode(data).decode()


@compiles(JSONB, 'sqlite')
def sqlite_json(element, compiler, **kwargs):
    return 'JSON'


# --- image validation -------------------------------------------------------

@pytest.mark.parametrize('data,media', [(JPEG, 'image/jpeg'), (PNG, 'image/png'), (WEBP, 'image/webp')])
def test_images_are_recognised_by_their_bytes(data, media):
    assert si.read_image(b64(data)) == (media, b64(data))
    assert si.read_image(f'data:image/gif;base64,{b64(data)}')[0] == media  # the claimed type is ignored


@pytest.mark.parametrize('value,message', [
    ('***', 'could not be read'), ('', 'empty'), (b64(b'GIF89a' + b'\x00' * 10), 'JPEG, PNG or WebP'),
    (b64(b'%PDF-1.7'), 'JPEG, PNG or WebP'), (b64(JPEG + b'\x00' * si.MAX_IMAGE_BYTES), 'larger than 5 MB'),
])
def test_bad_images_are_rejected_with_a_readable_message(value, message):
    with pytest.raises(si.ImportInputError, match=message):
        si.read_image(value)


# --- request shapes ---------------------------------------------------------

TOOL = {'name': 'propose_tasks', 'description': 'd', 'input_schema': {'type': 'object', 'properties': {}}}


def test_openai_compatible_sends_a_data_url_before_the_text(monkeypatch):
    client = llm_client.OpenAICompatibleLLMClient('k', 'vision-model', url='https://example.invalid/chat/completions', provider='Gemini')
    seen = {}

    async def respond(body):
        seen.update(body)
        return {'choices': [{'message': {'tool_calls': [{'function': {'name': 'propose_tasks', 'arguments': '{"items":[]}'}}]}}]}

    monkeypatch.setattr(client, '_post', respond)
    assert asyncio.run(client.call_tool(system='s', text='t', tool=TOOL, images=[('image/png', 'QUJD')])) == {'items': []}
    content = seen['messages'][1]['content']
    assert content[0] == {'type': 'image_url', 'image_url': {'url': 'data:image/png;base64,QUJD'}}
    assert content[1]['type'] == 'text' and '<user_data>' in content[1]['text']
    assert seen['model'] == 'vision-model'


def test_text_only_calls_keep_a_plain_string(monkeypatch):
    client = llm_client.GroqLLMClient('k', 'm')
    seen = {}

    async def respond(body):
        seen.update(body)
        return {'choices': [{'message': {'tool_calls': [{'function': {'name': 'propose_tasks', 'arguments': '{}'}}]}}]}

    monkeypatch.setattr(client, '_post', respond)
    asyncio.run(client.call_tool(system='s', text='t', tool=TOOL))
    assert isinstance(seen['messages'][1]['content'], str)


def test_anthropic_sends_a_base64_image_block(monkeypatch):
    client = llm_client.AnthropicLLMClient('k', 'claude-sonnet-5-5')
    seen = {}

    async def respond(body):
        seen.update(body)
        return {'content': [{'type': 'tool_use', 'name': 'propose_tasks', 'input': {'items': []}}]}

    monkeypatch.setattr(client, '_post', respond)
    asyncio.run(client.call_tool(system='s', text='t', tool=TOOL, images=[('image/jpeg', 'QUJD')]))
    content = seen['messages'][0]['content']
    assert content[0] == {'type': 'image', 'source': {'type': 'base64', 'media_type': 'image/jpeg', 'data': 'QUJD'}}
    assert content[1]['type'] == 'text'
    assert seen['tool_choice'] == {'type': 'tool', 'name': 'propose_tasks'}


# --- vision model selection --------------------------------------------------

def use_settings(monkeypatch, **values):
    from app import config
    monkeypatch.setattr(config, 'get_settings', lambda: SimpleNamespace(llm_timeout_seconds=8, import_timeout_seconds=45, **values))


def test_vision_uses_the_first_provider_that_can_read_images(monkeypatch):
    # Groq (the chat default here) serves no vision model, so photos go to Gemini.
    use_settings(monkeypatch, groq_api_key='g', gemini_api_key='m')
    client = llm_client.configured_vision_llm()
    assert client.provider == 'Gemini' and client.model == llm_client.VISION_DEFAULTS['gemini']
    assert client.timeout_seconds == 45
    # The chat client is a separate instance and keeps its own model and timeout.
    chat = llm_client.configured_llm()
    assert chat.provider == 'Groq' and chat.model == 'openai/gpt-oss-20b' and chat.timeout_seconds == 8
    use_settings(monkeypatch, groq_api_key='g')
    assert llm_client.configured_vision_llm() is None
    use_settings(monkeypatch, groq_api_key='g', vision_provider='groq', vision_model='some-vision-model')
    assert llm_client.configured_vision_llm().model == 'some-vision-model'


def test_vision_provider_and_model_can_be_forced(monkeypatch):
    use_settings(monkeypatch, groq_api_key='g', gemini_api_key='m', vision_provider='google')
    assert llm_client.configured_vision_llm().provider == 'Gemini'
    use_settings(monkeypatch, gemini_api_key='m', vision_model='gemini-x')
    assert llm_client.configured_vision_llm().model == 'gemini-x'
    use_settings(monkeypatch, vision_provider='nope')
    with pytest.raises(ValueError, match='Unknown VISION_PROVIDER'):
        llm_client.configured_vision_llm()


def test_providers_without_a_known_vision_model_need_one_named(monkeypatch):
    use_settings(monkeypatch, xai_api_key='x')
    assert llm_client.configured_vision_llm() is None
    use_settings(monkeypatch, xai_api_key='x', vision_model='grok-vision')
    assert llm_client.configured_vision_llm().model == 'grok-vision'
    use_settings(monkeypatch)
    assert llm_client.configured_vision_llm() is None
    use_settings(monkeypatch, anthropic_api_key='a')
    assert type(llm_client.configured_vision_llm()) is llm_client.AnthropicLLMClient


# --- extraction ---------------------------------------------------------------

class VisionLLM:
    def __init__(self, result):
        self.result, self.calls = result, []

    async def call_tool(self, **kwargs):
        self.calls.append(kwargs)
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


WHITEBOARD = {'course': 'Kitchen whiteboard', 'items': [
    {'title': 'Pay electricity bill', 'kind': 'other', 'due_date': '2026-11-18', 'due_time': None, 'effort_min': 15,
     'importance': None, 'category': 'finance', 'source_quote': 'Pay elec bill - Wed'},
    {'title': 'Buy milk', 'kind': 'other', 'due_date': None, 'due_time': None, 'effort_min': None,
     'importance': None, 'category': 'nonsense', 'source_quote': 'milk!'},
]}


def test_photo_extraction_keeps_categories_and_cites_the_photo():
    llm = VisionLLM(WHITEBOARD)
    result = asyncio.run(si.propose_photo(llm, 'image/png', 'QUJD', now=NOW, tz_name='UTC'))
    bill, milk = result['proposals']
    assert bill['category'] == 'finance' and bill['deadline_at'] == '2026-11-18T23:59:00+00:00'
    assert bill['notes'] == 'From photo: "Pay elec bill - Wed"'
    assert milk['category'] == 'other' and milk['deadline_at'] is None and milk['effort_est_min'] == 60
    assert result['source'] == 'photo' and result['fallback'] is False and result['course'] == 'Kitchen whiteboard'
    call = llm.calls[0]
    assert call['images'] == [('image/png', 'QUJD')] and call['tool'] is si.PHOTO_TOOL
    assert 'never instructions' in call['system'] and '2026-11-15' in call['system']
    assert 'category' in si.PHOTO_TOOL['input_schema']['properties']['items']['items']['required']


def test_photo_extraction_errors_are_typed():
    with pytest.raises(si.PhotoUnavailable):
        asyncio.run(si.propose_photo(None, 'image/png', 'QUJD', now=NOW, tz_name='UTC'))
    with pytest.raises(si.PhotoReadError):
        asyncio.run(si.propose_photo(VisionLLM(ValueError('no tool call')), 'image/png', 'QUJD', now=NOW, tz_name='UTC'))
    with pytest.raises(si.PhotoReadError):
        asyncio.run(si.propose_photo(VisionLLM({'nope': 1}), 'image/png', 'QUJD', now=NOW, tz_name='UTC'))


def test_syllabus_extraction_still_defaults_to_study():
    raw = {'items': [{**WHITEBOARD['items'][0], 'category': None}]}
    assert si.normalise(raw, now=NOW, zone=si.ZoneInfo('UTC'))['proposals'][0]['category'] == 'study'


# --- endpoint -----------------------------------------------------------------

def call_extract(monkeypatch, request, *, vision=None, chat=None):
    from app.api import imports
    monkeypatch.setattr(llm_client, 'configured_vision_llm', lambda: vision)
    if chat is not None:
        monkeypatch.setattr(llm_client, 'configured_llm', lambda: chat)

    async def run():
        engine = create_async_engine('sqlite+aiosqlite:///:memory:')
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        try:
            async with async_sessionmaker(engine, expire_on_commit=False)() as session:
                return await imports.extract(imports.ExtractRequest(**request), session=session, user_id='user_photo')
        finally:
            await engine.dispose()
    return asyncio.run(run())


def test_endpoint_reads_a_photo(monkeypatch):
    llm = VisionLLM(WHITEBOARD)
    result = call_extract(monkeypatch, {'image_base64': b64(PNG), 'client_tz': 'Asia/Kolkata'}, vision=llm)
    assert result['source'] == 'photo' and result['timezone'] == 'Asia/Kolkata'
    assert [p['title'] for p in result['proposals']][0] == 'Pay electricity bill'
    assert llm.calls[0]['images'][0][0] == 'image/png'


def test_endpoint_explains_missing_vision_bad_photos_and_model_failures(monkeypatch):
    with pytest.raises(HTTPException) as missing:
        call_extract(monkeypatch, {'image_base64': b64(JPEG)}, vision=None)
    assert missing.value.status_code == 503 and missing.value.detail['code'] == 'vision_unavailable'
    with pytest.raises(HTTPException) as bad:
        call_extract(monkeypatch, {'image_base64': b64(b'GIF89a')}, vision=VisionLLM(WHITEBOARD))
    assert bad.value.status_code == 422
    with pytest.raises(HTTPException) as failed:
        call_extract(monkeypatch, {'image_base64': b64(JPEG)}, vision=VisionLLM(RuntimeError('timeout')))
    assert failed.value.status_code == 502 and 'clearer' in failed.value.detail
    import httpx
    request = httpx.Request('POST', 'https://example.invalid')
    quota = httpx.HTTPStatusError('429', request=request, response=httpx.Response(429, request=request))
    with pytest.raises(HTTPException) as busy:
        call_extract(monkeypatch, {'image_base64': b64(JPEG)}, vision=VisionLLM(quota))
    assert busy.value.status_code == 503 and 'usage limit' in busy.value.detail


def test_text_imports_get_the_longer_import_timeout(monkeypatch):
    use_settings(monkeypatch)

    class Chat(VisionLLM):
        timeout_seconds = 8.0

    chat = Chat({'course': '', 'items': []})
    call_extract(monkeypatch, {'text': 'Essay due Nov 20, 2026'}, chat=chat)
    assert chat.timeout_seconds == 45 and 'images' not in chat.calls[0]


def test_a_rejected_forced_tool_choice_is_retried_with_auto(monkeypatch):
    import httpx
    client = llm_client.OpenAICompatibleLLMClient('k', 'gemini-3.5-flash', url='https://example.invalid/chat/completions', provider='Gemini')
    choices = []

    async def respond(body):
        choices.append(body['tool_choice'])
        if body['tool_choice'] != 'auto':
            request = httpx.Request('POST', client.url)
            raise httpx.HTTPStatusError('bad', request=request, response=httpx.Response(400, request=request))
        return {'choices': [{'message': {'tool_calls': [{'function': {'name': 'propose_tasks', 'arguments': '{"items": []}'}}]}}]}

    monkeypatch.setattr(client, '_post', respond)
    assert asyncio.run(client.call_tool(system='s', text='t', tool=TOOL, images=[('image/png', 'QUJD')])) == {'items': []}
    assert choices == [{'type': 'function', 'function': {'name': 'propose_tasks'}}, 'auto']


def test_other_provider_errors_are_not_retried(monkeypatch):
    import httpx
    client = llm_client.OpenAICompatibleLLMClient('k', 'm', url='https://example.invalid/chat/completions', provider='OpenAI')
    calls = []

    async def respond(body):
        calls.append(body)
        request = httpx.Request('POST', client.url)
        raise httpx.HTTPStatusError('denied', request=request, response=httpx.Response(401, request=request))

    monkeypatch.setattr(client, '_post', respond)
    with pytest.raises(httpx.HTTPStatusError):
        asyncio.run(client.call_tool(system='s', text='t', tool=TOOL))
    assert len(calls) == 1


def test_gemini_photo_calls_think_less_by_default(monkeypatch):
    # Gemini's default thinking took ~20 s per photo; a lower effort keeps the read and cuts the wait.
    use_settings(monkeypatch, gemini_api_key='m')
    assert llm_client.configured_vision_llm().reasoning_effort == 'low'
    use_settings(monkeypatch, gemini_api_key='m', vision_reasoning_effort='')
    assert llm_client.configured_vision_llm().reasoning_effort == ''
    use_settings(monkeypatch, gemini_api_key='m', vision_reasoning_effort='Medium')
    assert llm_client.configured_vision_llm().reasoning_effort == 'medium'
    # Other providers never get the parameter (gpt-4o-mini rejects it).
    use_settings(monkeypatch, openai_api_key='o')
    assert llm_client.configured_vision_llm().reasoning_effort == ''
    # Chat calls are untouched.
    use_settings(monkeypatch, gemini_api_key='m')
    assert llm_client.configured_llm().reasoning_effort == ''


def test_reasoning_effort_is_sent_and_dropped_on_a_400_retry(monkeypatch):
    import httpx
    client = llm_client.OpenAICompatibleLLMClient('k', 'gemini-3.5-flash', url='https://example.invalid/chat/completions', provider='Gemini')
    client.reasoning_effort = 'low'
    bodies = []

    async def respond(body):
        bodies.append(body)
        if len(bodies) == 1:
            request = httpx.Request('POST', client.url)
            raise httpx.HTTPStatusError('bad', request=request, response=httpx.Response(400, request=request))
        return {'choices': [{'message': {'tool_calls': [{'function': {'name': 'propose_tasks', 'arguments': '{"items": []}'}}]}}]}

    monkeypatch.setattr(client, '_post', respond)
    asyncio.run(client.call_tool(system='s', text='t', tool=TOOL, images=[('image/png', 'QUJD')]))
    assert bodies[0]['reasoning_effort'] == 'low' and 'reasoning_effort' not in bodies[1]
