"""Multilingual chat: the reply language reaches the model, and English date words still validate."""
import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.ext.compiler import compiles

from app.models import Base
from app.schemas import ChatRequest
from app.services.chat_orchestrator import handle_chat
from app.services.llm_client import SYSTEM_PROMPT, LLMResponse, render_context
from app.services.nlu_validator import ToolCall, check_phrase


@compiles(JSONB, 'sqlite')
def sqlite_json(element, compiler, **kwargs):
    return 'JSON'


class RecordedLLM:
    def __init__(self, response):
        self.response, self.contexts = response, []

    async def parse(self, *, text, context, history=None):
        self.contexts.append(context)
        return self.response


def run_with_session(body):
    async def run():
        engine = create_async_engine('sqlite+aiosqlite:///:memory:')
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        try:
            async with async_sessionmaker(engine, expire_on_commit=False)() as session:
                await body(session)
        finally:
            await engine.dispose()
    asyncio.run(run())


def test_reply_language_reaches_the_model_and_hinglish_task_is_created():
    async def body(session):
        tomorrow = (datetime.now(timezone.utc) + timedelta(days=1)).replace(hour=23, minute=59, second=0, microsecond=0)
        llm = RecordedLLM(LLMResponse('Theek hai, report kal shaam tak ki list mein daal di.', [ToolCall(name='create_task', arguments={
            'title': 'Report khatam karni hai', 'deadline_iso': tomorrow.isoformat(), 'deadline_phrase': 'tomorrow evening',
            'category': 'work', 'confidence': 'high'})]))
        result = await handle_chat(session, user_id='user_lang', text='Kal shaam tak report khatam karni hai',
                                   client_tz='UTC', llm=llm, language='hi')
        assert llm.contexts[0]['reply_language'] == 'hi'
        assert [a['type'] for a in result['actions']] == ['task_created']
        assert result['actions'][0]['task']['title'] == 'Report khatam karni hai'
        assert result['reply'].startswith('Theek hai')
    run_with_session(body)


def test_context_and_prompt_carry_the_language_rules():
    assert 'reply_language: hi' in render_context({'timezone': 'UTC', 'reply_language': 'hi'})
    assert 'reply_language' not in render_context({'timezone': 'UTC'})
    assert 'ALWAYS short English date words' in SYSTEM_PROMPT


def test_chat_request_language_is_a_language_code():
    assert ChatRequest(text='hi', language='pt-BR').language == 'pt-BR'
    assert ChatRequest(text='hi').language is None
    for bad in ['Hindi please', 'h', 'hi; drop', '']:
        with pytest.raises(ValidationError):
            ChatRequest(text='hi', language=bad)


def test_translated_date_words_pass_the_dual_check():
    now = datetime(2026, 11, 15, 12, tzinfo=timezone.utc)
    tomorrow = datetime(2026, 11, 16, 23, 59, tzinfo=timezone.utc)
    assert check_phrase(tomorrow, 'tomorrow evening', now=now, timezone='UTC') is None
    assert check_phrase(tomorrow, 'kal shaam tak', now=now, timezone='UTC') is not None  # why English phrases are required
