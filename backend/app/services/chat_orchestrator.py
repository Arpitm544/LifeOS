"""Chat pipeline: context -> LLM tool calls -> validation -> deterministic services.

The LLM only proposes tool calls. Every write goes through the same services as
the REST API, inside the request's transaction.
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from datetime import date, datetime, time as clock, timedelta, timezone
from typing import Optional
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

import httpx
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import select

from ..models import Event, Message, PlanBlock, Preference, Task
from ..schemas import Category, TaskCreate, TaskRead
from .domain_service import audit, snapshot
from .llm_client import FallbackLLMClient, LLMClient, LLMResponse, LLMUnavailable, configured_llm
from .nlu_validator import (TOOL_SCHEMAS, WRITE_TOOLS, CheckCapacityCall, CompleteTaskCall, CreateEventCall,
                            CreateTaskCall, DeleteTaskCall, PlanDayCall, QueryScheduleCall, SetPreferenceCall,
                            ToolCall, UpdateTaskCall, check_phrase, format_local, validate_create_task,
                            validate_deadline, validate_reminder)
from .planning_service import CATEGORY_DEFAULT_EFFORT, active_preferences, calendar_slots, detect_conflicts, \
    evaluate, load_state, minutes_until, rebuild_plan, recalculate_priorities
from .quick_add import parse_quick_add
from .scheduler import BusyBlock
from .task_service import complete_task_row, create_task, drop_task, latest_action, set_custom_reminder
from .text_match import is_pronoun, rank, similarity

# The whole message must be the answer; "yes, and also..." goes to the LLM.
YES = re.compile(r"^\s*(yes|y|yeah|yep|sure|ok|okay|go ahead|do it|confirm|create anyway|please do)\s*[.!]*\s*$", re.I)
NO = re.compile(r"^\s*(no|nope|cancel|stop|don'?t|never mind|nevermind)\s*[.!]*\s*$", re.I)
UNDO_SECONDS = 10
MAX_OPEN_TASKS_IN_CONTEXT = 30
MAX_CAPACITY_DAYS = 30  # routine expansion is bounded to 31 days


class CapacityInputError(ValueError):
    """A hypothetical deadline the check cannot answer (past, or too far ahead)."""


@dataclass
class ChatContext:
    now: datetime
    zone: ZoneInfo
    timezone_name: str
    preferences: dict
    open_tasks: list[Task]
    history: list[dict]
    last_touched: Optional[UUID] = None
    pending: Optional[dict] = None


@dataclass
class Outcome:
    actions: list[dict] = field(default_factory=list)
    replies: list[str] = field(default_factory=list)
    clarification: Optional[dict] = None
    confirmation: Optional[dict] = None
    pending_calls: list[dict] = field(default_factory=list)
    wrote: bool = False
    planned: bool = False
    last_touched: Optional[UUID] = None
    # What the agent did, in order, for the "How LifeOS handled this" panel.
    steps: list[dict] = field(default_factory=list)

    def step(self, kind: str, label: str, status: str = 'done', detail: str = '', **extra) -> None:
        self.steps.append({'kind': kind, 'label': label, 'status': status, 'detail': detail[:200], **extra})

    def clarify(self, question: str, options: Optional[list[str]] = None) -> None:
        # At most one clarification per message (PRD F1.4).
        if self.clarification is None:
            self.clarification = {'question': question, 'options': options or []}


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def task_card(task: Task, zone: ZoneInfo) -> dict:
    card = TaskRead.model_validate(task).model_dump(mode='json')
    card['deadline_label'] = _utc(task.deadline_at).astimezone(zone).strftime('%a %d %b, %H:%M') if task.deadline_at else None
    return card


async def build_context(session, user_id, text: str, client_tz: str, now: datetime) -> ChatContext:
    values = await active_preferences(session, user_id)
    tz_name = values.get('timezone', {}).get('name') or client_tz
    zone = ZoneInfo(tz_name)
    tasks = list((await session.execute(select(Task).where(Task.user_id == user_id,
        Task.status.in_(['open', 'blocked'])).order_by(Task.pinned.desc(), Task.priority_score.desc(),
        Task.deadline_at))).scalars())
    rows = list((await session.execute(select(Message).where(Message.user_id == user_id)
        .order_by(Message.created_at.desc()).limit(6))).scalars())
    rows.reverse()
    history = [{'role': row.role, 'text': row.text} for row in rows]
    last_touched = pending = None
    for row in reversed(rows):
        if row.role == 'assistant' and isinstance(row.tool_calls, dict):
            if row.tool_calls.get('last_touched_item_id'):
                last_touched = UUID(row.tool_calls['last_touched_item_id'])
            pending = row.tool_calls.get('pending')
            break
    summary = {key: values[key] for key in ('work_hours', 'quiet_hours', 'focus_windows', 'reminder_lead') if key in values}
    return ChatContext(now, zone, tz_name, summary, tasks, history, last_touched, pending)


def llm_context(ctx: ChatContext, text: str, events: list[Event], language: Optional[str] = None) -> dict:
    # Trigram matches for words in the message go first so "the report" resolves.
    matches = [identity for identity, _, score in rank(text, [(str(t.id), t.title) for t in ctx.open_tasks])[:5] if score >= 0.3]
    by_id = {str(task.id): task for task in ctx.open_tasks}
    ordered = [by_id[i] for i in matches] + [t for t in ctx.open_tasks if str(t.id) not in matches]
    local_now = ctx.now.astimezone(ctx.zone)
    return {
        'now_local': local_now.strftime('%A %Y-%m-%d %H:%M (UTC%z)'),
        'timezone': ctx.timezone_name,
        'reply_language': language,
        'preferences': ctx.preferences,
        'last_touched_item_id': str(ctx.last_touched) if ctx.last_touched else None,
        'open_tasks': [{'id': str(task.id), 'title': task.title,
                        'deadline': _utc(task.deadline_at).astimezone(ctx.zone).strftime('%a %Y-%m-%d %H:%M') if task.deadline_at else None}
                       for task in ordered[:MAX_OPEN_TASKS_IN_CONTEXT]],
        'events_today': [{'title': event.title,
                          'start': _utc(event.start_at).astimezone(ctx.zone).strftime('%H:%M'),
                          'end': _utc(event.end_at).astimezone(ctx.zone).strftime('%H:%M')} for event in events],
    }


SPOKEN_MAX_WORDS = 25


def spoken_version(reply: str) -> str:
    """The short spoken reply (PRD 4.7 / F5): at most 25 words, no lists, symbols or ISO dates.

    Built by code from the full reply so it never says a number the reply does not.
    """
    text = re.sub(r'\d{4}-\d{2}-\d{2}T[\d:.+\-Z]+', '', reply or '')      # raw ISO timestamps
    text = re.sub(r'^\s*(?:[-*•]|\d+[.)])\s+', '', text, flags=re.M)          # list markers
    text = re.sub(r'[*_`#>|~\[\]{}<>]', '', text).replace('→', ' to ').replace('&', ' and ')
    text = re.sub(r'\s+', ' ', text).strip()
    if not text:
        return 'Okay.'
    sentences = re.split(r'(?<=[.!?])\s+', text)
    spoken, count = [], 0
    for sentence in sentences:
        words = sentence.split()
        if count + len(words) > SPOKEN_MAX_WORDS:
            if not spoken:  # one long sentence: cut on a word boundary
                spoken.append(' '.join(words[:SPOKEN_MAX_WORDS]).rstrip(',;:') + '.')
            break
        spoken.append(sentence)
        count += len(words)
    return ' '.join(spoken)


async def handle_chat(session, *, user_id, text: str, client_tz: str,
                      llm: Optional[LLMClient] = None, now: Optional[datetime] = None,
                      language: Optional[str] = None) -> dict:
    result = await _handle_chat(session, user_id=user_id, text=text, client_tz=client_tz, llm=llm, now=now,
                                language=language)
    result.setdefault('spoken_reply', spoken_version(result.get('reply', '')))
    return result


async def _handle_chat(session, *, user_id, text: str, client_tz: str,
                       llm: Optional[LLMClient] = None, now: Optional[datetime] = None,
                       language: Optional[str] = None) -> dict:
    started = time.monotonic()
    now = _utc(now or datetime.now(timezone.utc))
    ctx = await build_context(session, user_id, text, client_tz, now)
    outcome = Outcome()
    fallback = False
    response: Optional[LLMResponse] = None

    if ctx.pending and YES.match(text):
        outcome.step('confirm', 'You confirmed the held changes', detail='Running them now.')
        await execute_calls(session, user_id, ctx, [ToolCall(**call) for call in ctx.pending['calls']],
                            outcome, confirmed=True)
        reply = 'Done.' if outcome.actions else 'Nothing changed.'
    elif ctx.pending and NO.match(text):
        outcome.step('confirm', 'You declined the held changes', 'skipped', 'Nothing was changed.')
        reply = 'Okay, I left everything as it was.'
    else:
        client = llm if llm is not None else configured_llm()
        fallback = isinstance(client, FallbackLLMClient)
        if not fallback:
            day_start = datetime.combine(now.astimezone(ctx.zone).date(), clock.min, tzinfo=ctx.zone)
            events = list((await session.execute(select(Event).where(Event.user_id == user_id,
                Event.cancelled == False, Event.start_at < day_start + timedelta(days=1),
                Event.end_at > day_start).order_by(Event.start_at))).scalars())
            outcome.step('context', 'Read your workspace', 'done',
                         f"{len(ctx.open_tasks)} open task{'s' if len(ctx.open_tasks) != 1 else ''}, "
                         f"{len(events)} event{'s' if len(events) != 1 else ''} today, your working hours"
                         + (f', reply in {language}' if language else ''))
            try:
                response = await client.parse(text=text, context=llm_context(ctx, text, events, language), history=ctx.history)
            except (LLMUnavailable, httpx.HTTPError, TimeoutError, OSError, ValueError, KeyError, TypeError):
                fallback = True
        if fallback:
            return await quick_add_reply(session, user_id, text, ctx, started, outcome.steps)
        count = len(response.tool_calls)
        outcome.step('understand', 'Understood your message', 'done',
                     (f"Planned {count} step{'s' if count != 1 else ''}" if count else 'No changes needed, just a reply')
                     + (f' with {response.model}' if response.model else ''), ms=response.latency_ms)
        await execute_calls(session, user_id, ctx, response.tool_calls, outcome)
        reply = response.reply or ('Done.' if outcome.wrote else '')

    conflicts = []
    if outcome.wrote and not outcome.planned:
        conflicts = await detect_conflicts(session, user_id, now=now)
    elif outcome.planned:
        from ..models import Conflict
        conflicts = list((await session.execute(select(Conflict).where(Conflict.user_id == user_id,
            Conflict.status == 'open').order_by(Conflict.deadline_at))).scalars())
    if outcome.wrote:
        outcome.step('check', 'Checked your deadlines still fit', 'warning' if conflicts else 'done',
                     f"{len(conflicts)} deadline{'s' if len(conflicts) != 1 else ''} at risk" if conflicts else 'All deadlines fit')
    reply_parts = [part for part in [reply, *outcome.replies] if part]
    if outcome.clarification and not outcome.actions:
        reply_parts = [outcome.clarification['question']]
    if outcome.confirmation:
        reply_parts.append(outcome.confirmation['prompt'])
    if conflicts and outcome.wrote:
        worst = max(conflicts, key=lambda row: row.needed_min - row.free_min)
        reply_parts.append(f"Heads up: {(worst.needed_min - worst.free_min) / 60:.1f} h short before "
                           f"{format_local(_utc(worst.deadline_at), ctx.timezone_name)}.")
    final_reply = ' '.join(reply_parts).strip() or 'Okay.'
    message_id = await record_messages(session, user_id, text, final_reply, ctx, outcome, response, started)
    return {'message_id': str(message_id), 'reply': final_reply, 'actions': outcome.actions,
            'conflicts': [conflict_card(row) for row in conflicts],
            'clarification': outcome.clarification, 'confirmation': outcome.confirmation,
            'fallback': False, 'steps': outcome.steps}


def conflict_card(row) -> dict:
    return {'id': str(row.id), 'deadline_at': _utc(row.deadline_at).isoformat(), 'needed_min': row.needed_min,
            'free_min': row.free_min, 'shortfall_min': max(0, row.needed_min - row.free_min),
            'task_ids': row.task_ids, 'options': [option.get('type') for option in row.options]}


async def record_messages(session, user_id, text, reply, ctx, outcome, response, started) -> UUID:
    latency = int((time.monotonic() - started) * 1000)
    tool_state = {'calls': [], 'last_touched_item_id': str(outcome.last_touched or ctx.last_touched or '') or None}
    if response is not None:
        tool_state['calls'] = [call.model_dump() for call in response.tool_calls]
    if outcome.pending_calls:
        tool_state['pending'] = {'calls': outcome.pending_calls}
    if outcome.steps:
        tool_state['steps'] = outcome.steps
    user_row = Message(id=uuid4(), user_id=user_id, role='user', text=text, created_at=ctx.now)
    assistant = Message(id=uuid4(), user_id=user_id, role='assistant', text=reply, tool_calls=tool_state,
                        latency_ms=latency, input_tokens=response.input_tokens if response else None,
                        output_tokens=response.output_tokens if response else None,
                        created_at=ctx.now + timedelta(microseconds=1))
    session.add_all([user_row, assistant])
    return assistant.id


FALLBACK_STEP = {'kind': 'fallback', 'label': 'AI model unavailable', 'status': 'warning',
                 'detail': 'Used quick add, which reads a title and a date without the model.'}


async def quick_add_reply(session, user_id, text, ctx: ChatContext, started, prior_steps: Optional[list] = None) -> dict:
    """LLM outage path (PRD F1.6 / NFR-R1): regex quick-add, else an Inbox task."""
    try:
        parsed = parse_quick_add(text, now=ctx.now, timezone=ctx.timezone_name)
    except ValueError as exc:
        message_id = await record_messages(session, user_id, text, str(exc), ctx, Outcome(), None, started)
        return {'message_id': str(message_id), 'reply': str(exc), 'actions': [], 'conflicts': [],
                'clarification': {'question': str(exc), 'options': []}, 'confirmation': None, 'fallback': True,
                'steps': [*(prior_steps or []), FALLBACK_STEP, {'kind': 'tool', 'label': 'Quick add', 'status': 'asked', 'detail': str(exc)[:200]}]}
    task = await create_task(session, user_id, TaskCreate(title=parsed['title'][:120], deadline_at=parsed['deadline_at']))
    await session.flush()
    action = await latest_action(session, user_id, task.id)
    conflicts = await detect_conflicts(session, user_id, now=ctx.now)
    outcome = Outcome(last_touched=task.id)
    reply = f"Saved to Inbox: {task.title}"
    message_id = await record_messages(session, user_id, text, reply, ctx, outcome, None, started)
    return {'message_id': str(message_id), 'reply': reply,
            'actions': [action_card('task_created', action, task, ctx)],
            'conflicts': [conflict_card(row) for row in conflicts], 'clarification': None,
            'confirmation': None, 'fallback': True,
            'steps': [*(prior_steps or []), FALLBACK_STEP, {'kind': 'tool', 'label': 'Quick add', 'status': 'done', 'detail': task.title, 'tool': 'create_task'},
                      {'kind': 'check', 'label': 'Checked your deadlines still fit', 'status': 'warning' if conflicts else 'done',
                       'detail': f"{len(conflicts)} deadline{'s' if len(conflicts) != 1 else ''} at risk" if conflicts else 'All deadlines fit'}]}


def action_card(kind: str, log, task: Optional[Task], ctx: ChatContext, **extra) -> dict:
    card = {'action_id': str(log.id) if log else None, 'type': kind}
    if task is not None:
        card.update(task_id=str(task.id), title=task.title, task=task_card(task, ctx.zone))
    if log is not None:
        card['undo_until'] = (_utc(log.created_at) + timedelta(seconds=UNDO_SECONDS)).isoformat()
    card.update(extra)
    return card


async def execute_calls(session, user_id, ctx: ChatContext, calls: list[ToolCall], outcome: Outcome,
                        *, confirmed: bool = False) -> None:
    parsed: list[tuple[ToolCall, object]] = []
    for call in calls:
        model = TOOL_SCHEMAS.get(call.name)
        if model is None:
            continue
        try:
            parsed.append((call, model.model_validate(call.arguments)))
        except ValidationError:
            outcome.clarify(f'Could you rephrase that? I could not read the details for {call.name.replace("_", " ")}.')
            outcome.step('tool', tool_label(call.name), 'failed', 'The details did not pass validation, so nothing was changed.', tool=call.name)
    writes = [call for call, _ in parsed if call.name in WRITE_TOOLS]
    needs_confirmation = any(call.name == 'delete_task' for call, _ in parsed) or len(writes) > 3
    if needs_confirmation and not confirmed:
        names = []
        for call, args in parsed:
            if call.name in WRITE_TOOLS:
                names.append(describe_call(call, args, ctx))
        outcome.pending_calls = [call.model_dump() for call in calls]
        outcome.confirmation = {'prompt': f"That changes {len(writes)} item{'s' if len(writes) != 1 else ''}: "
                                          + '; '.join(names) + '. Go ahead?', 'options': ['Yes', 'No']}
        for call, args in parsed:
            outcome.step('tool', tool_label(call.name, args), 'waiting' if call.name in WRITE_TOOLS else 'skipped',
                         'Held until you confirm.', tool=call.name)
        return
    for call, args in parsed:
        if call.name in WRITE_TOOLS and (args.confidence == 'low' or args.missing_fields):
            missing = ', '.join(args.missing_fields) if args.missing_fields else 'the details'
            outcome.clarify(f'Could you tell me {missing}?')
            outcome.step('tool', tool_label(call.name, args), 'asked', f'Not sure about {missing}, so I asked instead of guessing.', tool=call.name)
            continue
        handler = HANDLERS[call.name]
        before = (len(outcome.actions), len(outcome.replies), outcome.clarification is not None)
        started = time.monotonic()
        try:
            await handler(session, user_id, ctx, args, outcome, confirmed)
        except HTTPException as exc:
            outcome.clarify(str(exc.detail))
        status, detail = _step_result(outcome, before)
        outcome.step('tool', tool_label(call.name, args), status, detail, tool=call.name,
                     ms=int((time.monotonic() - started) * 1000))


TOOL_LABELS = {
    'create_task': 'Create task', 'update_task': 'Update task', 'complete_task': 'Complete task',
    'delete_task': 'Delete task', 'create_event': 'Add event', 'query_schedule': 'Check your schedule',
    'plan_day': 'Plan your day', 'check_capacity': 'Check if it fits', 'set_preference': 'Save a preference',
}


def tool_label(name: str, args=None) -> str:
    base = TOOL_LABELS.get(name, name.replace('_', ' ').capitalize())
    subject = (getattr(args, 'title', None) or getattr(args, 'task_ref', None)) if args is not None else None
    if subject and name not in ('check_capacity',):
        return f'{base} "{str(subject).strip()[:60]}"'
    return base


def _step_result(outcome: Outcome, before: tuple[int, int, bool]) -> tuple[str, str]:
    """Status and a short result for one tool call, from what it added to the outcome."""
    actions, replies, asked = before
    new_actions = outcome.actions[actions:]
    if outcome.clarification is not None and not asked and not new_actions:
        return 'asked', outcome.clarification['question']
    if outcome.confirmation is not None and not new_actions:
        return 'waiting', outcome.confirmation['prompt']
    if new_actions:
        first = new_actions[0]
        if first.get('title'):
            return 'done', first['title']
        return 'done', (outcome.replies[replies] if len(outcome.replies) > replies else '')
    if len(outcome.replies) > replies:
        return 'done', outcome.replies[replies]
    return 'skipped', 'Nothing needed to change.'


def describe_call(call: ToolCall, args, ctx: ChatContext) -> str:
    if call.name == 'delete_task':
        task, _ = resolve_task(args, ctx)
        return f"delete '{task.title}'" if task else 'delete a task'
    title = getattr(args, 'title', None) or getattr(args, 'task_ref', None) or call.name.replace('_', ' ')
    return f"{call.name.split('_')[0]} '{title}'"


def resolve_task(args, ctx: ChatContext) -> tuple[Optional[Task], Optional[dict]]:
    """Map task_id / task_ref to one open task, or explain what to ask (PRD F1.3)."""
    by_id = {task.id: task for task in ctx.open_tasks}
    if args.task_id and args.task_id in by_id:
        return by_id[args.task_id], None
    reference = (args.task_ref or '').strip()
    if (not reference or is_pronoun(reference)) and ctx.last_touched in by_id:
        return by_id[ctx.last_touched], None
    if not reference:
        return None, {'question': 'Which task do you mean?', 'options': [t.title for t in ctx.open_tasks[:4]]}
    ranked = rank(reference, [(str(t.id), t.title) for t in ctx.open_tasks])
    if not ranked or ranked[0][2] < 0.3:
        return None, {'question': f"I couldn't find '{reference}'. Which task do you mean?",
                      'options': [title for _, title, _ in ranked[:3]]}
    if len(ranked) > 1 and ranked[1][2] >= 0.3 and ranked[0][2] - ranked[1][2] < 0.1:
        return None, {'question': f'Which one: {ranked[0][1]} or {ranked[1][1]}?',
                      'options': [ranked[0][1], ranked[1][1]]}
    return by_id[UUID(ranked[0][0])], None


async def handle_create_task(session, user_id, ctx, args: CreateTaskCall, outcome, confirmed):
    problem = validate_create_task(args, now=ctx.now, timezone=ctx.timezone_name)
    if problem:
        outcome.clarify(problem)
        return
    open_ids = {task.id for task in ctx.open_tasks}
    if any(identity not in open_ids for identity in args.depends_on):
        outcome.clarify('Which existing task must happen first?')
        return
    if not confirmed:
        for task in ctx.open_tasks:
            close = (task.deadline_at is None and args.deadline_iso is None) or (
                task.deadline_at is not None and args.deadline_iso is not None
                and abs((_utc(task.deadline_at) - args.deadline_iso).total_seconds()) <= 86400)
            if close and similarity(task.title, args.title) >= 0.8:
                outcome.pending_calls.append({'name': 'create_task', 'arguments': args.model_dump(mode='json')})
                outcome.confirmation = {'prompt': f"Looks like you already have '{task.title}'. Add another anyway?",
                                        'options': ['Yes', 'No']}
                return
    task = await create_task(session, user_id, TaskCreate(
        title=args.title.strip(), deadline_at=args.deadline_iso,
        effort_est_min=args.effort_min or CATEGORY_DEFAULT_EFFORT[args.category.value],
        importance=args.importance or 3, category=args.category, depends_on=args.depends_on,
        recurrence_rrule=args.recurrence_rrule))
    if args.remind_at_iso:
        await set_custom_reminder(session, user_id, task, args.remind_at_iso)
    ctx.open_tasks.append(task)
    log = await latest_action(session, user_id, task.id)
    outcome.actions.append(action_card('task_created', log, task, ctx))
    outcome.wrote, outcome.last_touched = True, task.id


async def handle_update_task(session, user_id, ctx, args: UpdateTaskCall, outcome, confirmed):
    task, question = resolve_task(args, ctx)
    if task is None:
        outcome.clarify(question['question'], question['options'])
        return
    # Validate everything before touching the task, so a rejected part writes nothing.
    problem = validate_deadline(args.deadline_iso, args.deadline_phrase, now=ctx.now, timezone=ctx.timezone_name) \
        or validate_reminder(args.remind_at_iso, args.remind_at_phrase, now=ctx.now, timezone=ctx.timezone_name)
    if problem:
        outcome.clarify(problem)
        return
    changes = {'title': args.title, 'deadline_at': args.deadline_iso, 'effort_est_min': args.effort_min,
               'importance': args.importance, 'category': args.category.value if args.category else None,
               'pinned': args.pinned}
    changes = {key: value for key, value in changes.items() if value is not None}
    if not changes and not args.remind_at_iso:
        outcome.clarify(f'What should I change about {task.title}?')
        return
    before = snapshot(task)
    for key, value in changes.items():
        setattr(task, key, value.strip() if isinstance(value, str) and key == 'title' else value)
    if changes:
        await recalculate_priorities(session, user_id, ctx.now)
    reminder = None
    if args.remind_at_iso:
        reminder = await set_custom_reminder(session, user_id, task, args.remind_at_iso)
        outcome.replies.append(f"I'll remind you {format_local(args.remind_at_iso, ctx.timezone_name)}.")
    # One undoable action covers both the field edits and the custom reminder.
    log = await audit(session, user_id, task, before, 'update')
    if reminder is not None:
        log.after = {**log.after, '_custom_reminder_id': str(reminder.id)}
    outcome.actions.append(action_card('task_updated', log, task, ctx))
    outcome.wrote, outcome.last_touched = True, task.id


async def handle_complete_task(session, user_id, ctx, args: CompleteTaskCall, outcome, confirmed):
    task, question = resolve_task(args, ctx)
    if task is None:
        outcome.clarify(question['question'], question['options'])
        return
    log = await complete_task_row(session, user_id, task, args.actual_effort_min)
    ctx.open_tasks = [item for item in ctx.open_tasks if item.id != task.id]
    outcome.actions.append(action_card('task_completed', log, task, ctx,
                                       ask_actual_effort=args.actual_effort_min is None))
    outcome.wrote, outcome.last_touched = True, task.id


async def handle_delete_task(session, user_id, ctx, args: DeleteTaskCall, outcome, confirmed):
    task, question = resolve_task(args, ctx)
    if task is None:
        outcome.clarify(question['question'], question['options'])
        return
    batch_id = await drop_task(session, user_id, task)
    ctx.open_tasks = [item for item in ctx.open_tasks if item.id != task.id]
    log = await latest_action(session, user_id, task.id)
    outcome.actions.append(action_card('task_deleted', log, task, ctx, batch_id=str(batch_id)))
    outcome.wrote = True


async def handle_create_event(session, user_id, ctx, args: CreateEventCall, outcome, confirmed):
    from ..schemas_events import EventCreate
    problem = check_phrase(args.start_iso, args.start_phrase, now=ctx.now, timezone=ctx.timezone_name)
    if problem:
        outcome.clarify(problem)
        return
    if args.start_iso < ctx.now and not args.recurrence_rrule:
        outcome.clarify('That time has already passed. When is it?')
        return
    end = args.end_iso or args.start_iso + timedelta(minutes=args.duration_min or 60)
    try:
        payload = EventCreate(title=args.title.strip(), start_at=args.start_iso, end_at=end,
                              location=args.location, rrule=args.recurrence_rrule, source='chat')
    except ValidationError:
        outcome.clarify(f'When does {args.title} end?')
        return
    event = Event(user_id=user_id, **payload.model_dump())
    session.add(event)
    await session.flush()
    log = await audit(session, user_id, event, None, 'create')
    outcome.actions.append(action_card('event_created', log, None, ctx, event={
        'id': str(event.id), 'title': event.title, 'start_at': _utc(event.start_at).isoformat(),
        'end_at': _utc(event.end_at).isoformat(), 'location': event.location,
        'label': format_local(_utc(event.start_at), ctx.timezone_name)}))
    outcome.wrote = True


def _local_day_bounds(ctx: ChatContext, day: date) -> tuple[datetime, datetime]:
    start = datetime.combine(day, clock.min, tzinfo=ctx.zone).astimezone(timezone.utc)
    return start, start + timedelta(days=1)


async def handle_query_schedule(session, user_id, ctx, args: QueryScheduleCall, outcome, confirmed):
    start, end = _local_day_bounds(ctx, ctx.now.astimezone(ctx.zone).date())
    start = _utc(args.range_start_iso) if args.range_start_iso else max(start, ctx.now)
    end = _utc(args.range_end_iso) if args.range_end_iso else end
    if args.filter == 'due' and not args.range_end_iso:
        end = start + timedelta(days=7)
    if end <= start:
        outcome.clarify('Which time range do you mean?')
        return
    result: dict = {'range_start': start.isoformat(), 'range_end': end.isoformat()}
    titles = {task.id: task.title for task in ctx.open_tasks}
    if args.filter in {'due', 'all'}:
        due = [task for task in ctx.open_tasks if task.deadline_at and start <= _utc(task.deadline_at) < end]
        result['due'] = [task_card(task, ctx.zone) for task in due]
        outcome.replies.append('Due: ' + '; '.join(f"{t.title} ({format_local(_utc(t.deadline_at), ctx.timezone_name)})" for t in due)
                               + '.' if due else 'Nothing is due in that range.')
    if args.filter in {'plan', 'next', 'all'}:
        blocks = list((await session.execute(select(PlanBlock).where(PlanBlock.user_id == user_id,
            PlanBlock.status == 'planned', PlanBlock.end_at > start, PlanBlock.start_at < end)
            .order_by(PlanBlock.start_at))).scalars())
        if args.filter == 'next':
            blocks = blocks[:1]
        result['plan_blocks'] = [{'task_id': str(b.task_id), 'title': titles.get(b.task_id, 'Task'),
                                  'start_at': _utc(b.start_at).isoformat(), 'end_at': _utc(b.end_at).isoformat()} for b in blocks]
        if blocks:
            first = blocks[0]
            outcome.replies.append(f"Next up: {titles.get(first.task_id, 'a task')}, "
                                   f"{_utc(first.start_at).astimezone(ctx.zone):%H:%M} to {_utc(first.end_at).astimezone(ctx.zone):%H:%M}.")
        elif args.filter == 'next' and ctx.open_tasks:
            top = ctx.open_tasks[0]
            outcome.replies.append(f'Next up: {top.title} ({top.priority_band}).')
        elif args.filter == 'next':
            outcome.replies.append('Your list is clear.')
    if args.filter == 'free':
        state = await load_state(session, user_id, now=max(start, ctx.now), days=max(1, (end - start).days + 1))
        slots = [slot for slot in state.slots if slot.start < end]
        slots = [BusyBlock(max(slot.start, start), min(slot.end, end)) for slot in slots if slot.end > start]
        free_min = sum(int((slot.end - slot.start).total_seconds() / 60) for slot in slots if slot.end > slot.start)
        result['free_slots'] = [{'start_at': slot.start.isoformat(), 'end_at': slot.end.isoformat()} for slot in slots if slot.end > slot.start]
        result['free_min'] = free_min
        outcome.replies.append(f'You have {free_min / 60:.1f} h free in that window.' if free_min else 'You are fully booked then.')
    outcome.actions.append({'action_id': None, 'type': 'schedule', 'filter': args.filter, 'result': result})


async def handle_plan_day(session, user_id, ctx, args: PlanDayCall, outcome, confirmed):
    try:
        day = date.fromisoformat(args.date) if args.date else ctx.now.astimezone(ctx.zone).date()
    except ValueError:
        outcome.clarify('Which day should I plan?')
        return
    extra = []
    if args.not_after:
        stop = datetime.combine(day, clock.fromisoformat(args.not_after), tzinfo=ctx.zone).astimezone(timezone.utc)
        extra.append(BusyBlock(stop, _local_day_bounds(ctx, day)[1]))
    result = await rebuild_plan(session, user_id, now=ctx.now, days=7, extra_busy=extra)
    start, end = _local_day_bounds(ctx, day)
    titles = {task.id: task.title for task in ctx.open_tasks}
    today = [block for block in result['blocks'] if start <= block.start_at < end]
    planned_min = sum(int((b.end_at - b.start_at).total_seconds() / 60) for b in today)
    if today:
        first = today[0]
        summary = (f"{len({b.task_id for b in today})} task(s), {planned_min / 60:.1f} h of focus. First up: "
                   f"{titles.get(first.task_id, 'a task')} at {_utc(first.start_at).astimezone(ctx.zone):%H:%M}.")
    else:
        summary = 'Nothing needs planning that day.'
    outcome.replies.append(summary)
    outcome.actions.append({'action_id': None, 'type': 'plan_generated', 'date': day.isoformat(),
        'plan_blocks': [{'id': str(b.id), 'task_id': str(b.task_id), 'title': titles.get(b.task_id, 'Task'),
                         'start_at': _utc(b.start_at).isoformat(), 'end_at': _utc(b.end_at).isoformat()} for b in today],
        'unplaced_task_ids': result['unplaced_task_ids']})
    outcome.wrote = outcome.planned = True


async def handle_check_capacity(session, user_id, ctx, args: CheckCapacityCall, outcome, confirmed):
    problem = check_phrase(args.deadline_iso, args.deadline_phrase, now=ctx.now, timezone=ctx.timezone_name)
    if problem:
        outcome.clarify(problem)
        return
    try:
        result = await hypothetical_capacity(session, user_id, title=args.title, effort_min=args.effort_min,
                                             deadline=args.deadline_iso, now=ctx.now)
    except CapacityInputError as exc:
        outcome.clarify(str(exc))
        return
    when = format_local(args.deadline_iso, ctx.timezone_name)
    if result['fits']:
        outcome.replies.append(f"Yes, it fits: {result['free_min'] / 60:.1f} h free before {when}, "
                               f"{result['needed_min'] / 60:.1f} h needed including what is already due.")
    else:
        outcome.replies.append(f"Not without changes: {result['shortfall_min'] / 60:.1f} h short before {when}. "
                               "You could extend your hours, move a flexible item, or renegotiate a deadline.")
    outcome.actions.append({'action_id': None, 'type': 'capacity_check', 'result': result})


async def hypothetical_capacity(session, user_id, *, title: str, effort_min: int, deadline: datetime,
                                now: datetime, category: str = 'other') -> dict:
    """'Can I take this on?' using real free time; nothing is saved (PRD 5.4)."""
    if deadline <= now:
        raise CapacityInputError('That deadline has already passed. Which future date do you mean?')
    if deadline - now > timedelta(days=MAX_CAPACITY_DAYS):
        raise CapacityInputError(f'I can check up to {MAX_CAPACITY_DAYS} days ahead. Is there an earlier date?')
    # The checked window must reach the deadline, or the work would look like it fits.
    days = max(1, (deadline - now).days + 1)
    state = await load_state(session, user_id, now=now, days=days)
    ghost = Task(id=uuid4(), user_id=user_id, title=title, deadline_at=deadline, effort_est_min=min(effort_min, 600),
                 importance=3, category=category, status='open', priority_score=50, pinned=False, created_at=now)
    state.tasks = [*state.tasks, ghost]
    state.efforts[ghost.id] = round(effort_min * state.factors.get(category, 1.0))
    _, _, conflicts = evaluate(state)
    relevant = [item for item in conflicts if str(ghost.id) in item.task_ids]
    needed = sum(state.efforts[t.id] for t in state.tasks if t.deadline_at and now < _utc(t.deadline_at) <= _utc(deadline))
    free = minutes_until(state.slots, deadline)
    worst = max(relevant, key=lambda item: item.shortfall_min) if relevant else None
    return {'fits': worst is None, 'needed_min': worst.needed_min if worst else needed,
            'free_min': worst.free_min if worst else free,
            'shortfall_min': worst.shortfall_min if worst else 0,
            'deadline_at': _utc(worst.deadline).isoformat() if worst else _utc(deadline).isoformat(),
            'options': [option['type'] for option in worst.options] if worst else []}


async def handle_set_preference(session, user_id, ctx, args: SetPreferenceCall, outcome, confirmed):
    from ..schemas_preferences import PreferenceUpdate
    row = (await session.execute(select(Preference).where(Preference.user_id == user_id,
        Preference.key == args.key).with_for_update())).scalar_one_or_none()
    value = dict(args.value)
    if row is not None and args.key in {'work_hours', 'quiet_hours'}:
        value = {**row.value, **value}  # "I never work after 9 pm" changes only the end
    elif row is None and args.key == 'work_hours':
        value = {'start': '09:00', 'end': '18:00', **value}
    elif row is None and args.key == 'quiet_hours':
        value = {'start': '22:30', 'end': '07:30', **value}
    try:
        payload = PreferenceUpdate(key=args.key, value=value, source='stated', confidence=1.0, status='active')
    except ValidationError:
        outcome.clarify('I could not save that preference. Could you say it another way?')
        return
    before = snapshot(row) if row else None
    if row is None:
        row = Preference(user_id=user_id, **payload.model_dump())
        session.add(row)
    else:
        for key, item in payload.model_dump().items():
            setattr(row, key, item)
    await session.flush()
    log = await audit(session, user_id, row, before, 'create' if before is None else 'update')
    outcome.actions.append(action_card('preference_set', log, None, ctx, preference={'key': row.key, 'value': row.value, 'source': row.source}))
    outcome.wrote = True


HANDLERS = {
    'create_task': handle_create_task,
    'update_task': handle_update_task,
    'complete_task': handle_complete_task,
    'delete_task': handle_delete_task,
    'create_event': handle_create_event,
    'query_schedule': handle_query_schedule,
    'plan_day': handle_plan_day,
    'check_capacity': handle_check_capacity,
    'set_preference': handle_set_preference,
}
