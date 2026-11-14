import pytest
from pydantic import ValidationError
from app.schemas import TaskPatch


@pytest.mark.parametrize('data', [{'importance': 6}, {'effort_est_min': 0},
    {'title': ''}, {'pinned': None}, {'user_id': 'someone'}, {'status': 'done'},
    {'deadline_at': '2026-11-20T09:00:00'}])
def test_invalid_task_edits_rejected(data):
    with pytest.raises(ValidationError):
        TaskPatch(**data)


def test_deadline_clear_is_distinct_from_omitted():
    assert TaskPatch().model_dump(exclude_unset=True) == {}
    assert TaskPatch(deadline_at=None).model_dump(exclude_unset=True) == {'deadline_at': None}


def test_valid_partial_edit():
    assert TaskPatch(title='Revised report', pinned=True).model_dump(exclude_unset=True) == {
        'title': 'Revised report', 'pinned': True}
