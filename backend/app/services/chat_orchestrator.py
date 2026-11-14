from __future__ import annotations
from typing import Optional


from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from ..schemas import TaskCreate
from ..models import ActionLog
from .llm_client import FallbackLLMClient, LLMClient
from .nlu_validator import CreateTaskCall, validate_create_task
from .quick_add import parse_quick_add
from .task_service import create_task


async def handle_chat(session: AsyncSession, *, user_id: UUID, text: str,
                      client_tz: str, llm: Optional[LLMClient] = None) -> dict:
    now = datetime.now(timezone.utc)
    response = await (llm or FallbackLLMClient()).parse(text=text, context={"now": now.isoformat(), "timezone": client_tz})
    actions: list[dict] = []
    clarifications: list[str] = []
    for tool_call in response.tool_calls:
        if tool_call.name != "create_task":
            continue
        call = CreateTaskCall.model_validate(tool_call.arguments)
        problem = validate_create_task(call, now=now, timezone=client_tz)
        if problem:
            clarifications.append(problem)
            continue
        task = await create_task(session, user_id, TaskCreate(
            title=call.title,
            deadline_at=call.deadline_iso,
            effort_est_min=call.effort_min or 30,
            importance=call.importance or 3,
            category=call.category,
            depends_on=call.depends_on,
            recurrence_rrule=call.recurrence_rrule,
        ))
        action_id = (await session.execute(select(ActionLog.id).where(ActionLog.user_id == user_id,
                                                                       ActionLog.entity_id == task.id).order_by(ActionLog.created_at.desc()))).scalar_one()
        actions.append({"type": "task_created", "action_id": str(action_id), "task_id": str(task.id), "title": task.title,
                        "priority_score": task.priority_score, "priority_band": task.priority_band})
    if not response.tool_calls:
        parsed = parse_quick_add(text, now=now, timezone=client_tz)
        task = await create_task(session, user_id, TaskCreate(
            title=parsed['title'][:120], deadline_at=parsed['deadline_at']))
        await session.flush()
        action = (await session.execute(select(ActionLog).where(
            ActionLog.user_id == user_id, ActionLog.entity_id == task.id))).scalar_one()
        from datetime import timedelta
        return {"reply": f"Saved to Inbox: {task.title}", "spoken_reply": "Saved to your inbox.",
                "actions": [{"action_id": str(action.id), "type": "task_created",
                             "task_id": str(task.id), "title": task.title,
                             "undo_until": (action.created_at.replace(tzinfo=timezone.utc) + timedelta(seconds=10)).isoformat()}],
                "conflicts": [], "clarification": None, "fallback": True}
    return {"reply": response.reply, "spoken_reply": response.spoken_reply, "actions": actions,
            "conflicts": [], "clarification": clarifications[0] if clarifications else None, "fallback": False}

