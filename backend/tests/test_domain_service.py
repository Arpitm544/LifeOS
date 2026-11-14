from datetime import datetime, timezone
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.models import Task
from app.services.domain_service import assert_acyclic, snapshot


def test_dependency_dag_allows_shared_prerequisites():
    assert_acyclic([('a', 'b'), ('a', 'c'), ('c', 'b')])


@pytest.mark.parametrize('edges', [[('a','a')], [('a','b'),('b','a')],
    [('a','b'),('b','c'),('c','a')]])
def test_dependency_cycles_rejected(edges):
    with pytest.raises(HTTPException) as error:
        assert_acyclic(edges)
    assert error.value.status_code == 409


def test_snapshot_retains_restorable_values():
    owner, identity = uuid4(), uuid4()
    task = Task(id=identity, user_id=owner, title='Report', created_at=datetime(2026,1,1,tzinfo=timezone.utc))
    result = snapshot(task)
    assert result['id'] == str(identity) and result['user_id'] == str(owner)
    assert result['created_at'] == '2026-01-01T00:00:00+00:00'
    assert result['title'] == 'Report'
