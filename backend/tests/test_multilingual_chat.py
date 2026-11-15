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


class TranslatingLLM(RecordedLLM):
    """Answers like the model, then translates template text through `write`."""
    def __init__(self, response, translation):
        super().__init__(response)
        self.translation, self.translated = translation, []

    async def write(self, *, system, payload):
        self.translated.append((system, payload['reply']))
        return self.translation


def test_template_replies_are_translated_into_the_reply_language():
    from app.services.chat_orchestrator import translate_reply

    async def check():
        class Model:
            async def write(self, *, system, payload):
                assert 'language with code hi' in system
                return 'आज 1 घटना है: 10:00 पर Standup।'
        assert await translate_reply('You have 1 event today: Standup at 10:00.', 'hi', Model()) == 'आज 1 घटना है: 10:00 पर Standup।'

        class WrongNumbers:
            async def write(self, *, system, payload):
                return 'आज 2 घटनाएँ हैं: 11:00 पर Standup।'
        assert await translate_reply('You have 1 event today: Standup at 10:00.', 'hi', WrongNumbers()) == 'You have 1 event today: Standup at 10:00.'

        class Down:
            async def write(self, *, system, payload):
                raise RuntimeError('outage')
        assert await translate_reply('Done.', 'es', Down()) == 'Done.'

        class EmptyOnce:
            calls = 0
            async def write(self, *, system, payload):
                EmptyOnce.calls += 1
                return '' if EmptyOnce.calls == 1 else 'अगला: 09:00 पर Hi।'
        assert await translate_reply('Next up: Hi at 09:00.', 'hi', EmptyOnce()) == 'अगला: 09:00 पर Hi।'
        assert EmptyOnce.calls == 2
    asyncio.run(check())


def test_the_models_own_words_skip_translation_but_tool_results_do_not():
    async def body(session):
        tomorrow = (datetime.now(timezone.utc) + timedelta(days=1)).replace(hour=23, minute=59, second=0, microsecond=0)
        llm = TranslatingLLM(LLMResponse('आज आपके पास कुछ बाकी नहीं है।', []), 'unused')
        chat = await handle_chat(session, user_id='user_hi', text='आज मेरे पास क्या है?', client_tz='UTC', llm=llm, language='hi')
        assert chat['reply'] == 'आज आपके पास कुछ बाकी नहीं है।'
        assert llm.translated == []
        assert '_templated' not in chat

        tool = TranslatingLLM(LLMResponse('', [ToolCall(name='create_task', arguments={
            'title': 'Essay', 'deadline_iso': tomorrow.isoformat(), 'deadline_phrase': 'tomorrow night',
            'category': 'study', 'confidence': 'high'})]), 'हो गया: काम जोड़ दिया।')
        made = await handle_chat(session, user_id='user_hi', text='कल रात तक essay', client_tz='UTC', llm=tool, language='hi')
        assert [a['type'] for a in made['actions']] == ['task_created']
        assert len(tool.translated) == 1
    run_with_session(body)


def test_spoken_confirmations_work_in_hindi_too():
    from app.services.chat_orchestrator import NO, YES
    for word in ['yes', 'हाँ', 'हां।', 'जी हाँ', 'haan', 'Haan ji', 'theek hai', 'कर दो']:
        assert YES.match(word), word
    for word in ['no', 'नहीं', 'nahi', 'mat karo', 'रहने दो']:
        assert NO.match(word), word
    assert not YES.match('sí')  # only English and Hindi
    assert not YES.match('हाँ, और एक मीटिंग जोड़ दो')  # a longer request is not a bare confirmation


class Unavailable:
    """An AI provider that is down or rate-limited, so chat falls back to quick add."""
    async def parse(self, *, text, context, history=None):
        from app.services.llm_client import LLMUnavailable
        raise LLMUnavailable('429 Too Many Requests')


def test_when_the_model_is_down_questions_are_answered_not_saved_as_tasks():
    from sqlalchemy import func, select
    from app.models import Task

    async def body(session):
        async def tasks():
            return (await session.execute(select(func.count()).select_from(Task).where(Task.user_id == 'user_offline'))).scalar_one()

        english = await handle_chat(session, user_id='user_offline', text="What's on my schedule today?", client_tz='UTC', llm=Unavailable())
        assert english['actions'] == [] and english['fallback'] is True
        assert english['reply'].startswith("I can't reach the assistant")
        hindi = await handle_chat(session, user_id='user_offline', text='क्या मेरे पास शुक्रवार तक 2 घंटे का समय है?', client_tz='UTC',
                                  llm=Unavailable(), language='hi')
        assert hindi['actions'] == []
        assert hindi['reply'].startswith('अभी सहायक से संपर्क नहीं')
        assert await tasks() == 0

        saved = await handle_chat(session, user_id='user_offline', text='Call mom tomorrow', client_tz='UTC', llm=Unavailable())
        assert [a['type'] for a in saved['actions']] == ['task_created']  # real tasks are still captured offline
        assert await tasks() == 1
    run_with_session(body)


def test_question_detection_in_english_and_hindi():
    from app.services.chat_orchestrator import looks_like_question
    for text in ["What's on my schedule today?", 'Do I have time for 2 hours by Friday', 'Show me my week', 'Is the report due Friday',
                 'आज मेरा शेड्यूल क्या है', 'मेरा शेड्यूल दिखाओ', 'kal kya hai', 'meeting kab hai']:
        assert looks_like_question(text), text
    for text in ['Call mom tomorrow at 5', 'Do laundry tonight', 'Finish DBMS report by Friday, 3 hours', 'Buy milk',
                 'कल शाम तक रिपोर्ट खत्म करनी है', 'kal shaam tak report', 'Review what changed in the PR']:
        assert not looks_like_question(text), text
