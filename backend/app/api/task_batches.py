from uuid import UUID, uuid4
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from ..auth import current_user_id
from ..db import get_session
from ..schemas import TaskPatch
from ..services.domain_service import audit, snapshot, lock_tasks

router = APIRouter(prefix='/api/task-batches', tags=['tasks'])


class BatchEdit(BaseModel):
    task_ids: list[UUID] = Field(min_length=1, max_length=100)
    changes: TaskPatch
    confirmed: bool = False


@router.patch('')
async def edit_batch(payload: BatchEdit, session: AsyncSession = Depends(get_session), owner=Depends(current_user_id)):
    ids = set(payload.task_ids)
    if len(ids) > 3 and not payload.confirmed:
        raise HTTPException(status_code=409, detail={'confirmation_required': True, 'count': len(ids)})
    owned = {task.id: task for task in await lock_tasks(session, owner)}
    if not ids.issubset(owned):
        raise HTTPException(status_code=404, detail='Task not found')
    if not payload.changes.model_fields_set:
        raise HTTPException(status_code=422, detail='No changes supplied')
    batch_id, actions = uuid4(), []
    for identity in sorted(ids):
        task = owned[identity]
        before = snapshot(task)
        for key in payload.changes.model_fields_set:
            setattr(task, key, getattr(payload.changes, key))
        log = await audit(session, owner, task, before, 'update')
        log.batch_id = batch_id
        actions.append(str(log.id))
    await session.commit()
    return {'batch_id': str(batch_id), 'action_ids': actions}
