"""The golden NLU set itself (PRD Appendix B): shape, mix, and the scorer. The live run is scripts/run_golden.py."""
import importlib.util
from pathlib import Path

from app.services.nlu_validator import TOOL_SCHEMAS

spec = importlib.util.spec_from_file_location('run_golden', Path(__file__).resolve().parents[1] / 'scripts' / 'run_golden.py')
golden = importlib.util.module_from_spec(spec)
spec.loader.exec_module(golden)


def test_golden_set_has_the_prd_mix():
    cases = golden.load_golden()['cases']
    assert len(cases) == 50
    assert len({case['id'] for case in cases}) == 50
    groups = [case['group'] for case in cases]
    assert (groups.count('simple'), groups.count('multi'), groups.count('ambiguous')) == (25, 15, 10)


def test_golden_expectations_use_real_tools_and_fields():
    data = golden.load_golden()
    task_ids = {task['id'] for task in data['context']['open_tasks']}
    for case in data['cases']:
        if case['expect'] == 'clarify':
            assert case['group'] == 'ambiguous'
            continue
        for item in case['expect']:
            assert item['tool'] in TOOL_SCHEMAS, case['id']
            fields = TOOL_SCHEMAS[item['tool']].model_fields
            for field in [*item.get('required', []), *(item.get('match') or {})]:
                assert field in fields, (case['id'], field)
            if 'ref' in item:
                assert item['ref'] in task_ids, case['id']
        if case['group'] == 'multi':
            assert len(case['expect']) >= 2, case['id']


def test_scorer_checks_intents_fields_and_references():
    case = {'expect': [{'tool': 'create_task', 'required': ['title', 'deadline_iso'], 'match': {'effort_min': 120}},
                       {'tool': 'complete_task', 'ref': 'abc'}]}
    good = [{'name': 'complete_task', 'arguments': {'task_id': 'abc'}},
            {'name': 'create_task', 'arguments': {'title': 'x', 'deadline_iso': '2026-11-19T23:59:00+05:30', 'effort_min': 120}}]
    assert golden.score_case(case, good)
    assert not golden.score_case(case, good[:1])                                   # missing intent
    assert not golden.score_case(case, [good[0], {'name': 'create_task', 'arguments': {'title': 'x'}}])  # missing field
    assert golden.score_case(case, [{'name': 'complete_task', 'arguments': {'task_ref': 'the report'}}, good[1]])
    assert not golden.score_case(case, [{'name': 'complete_task', 'arguments': {'task_id': 'other'}}, good[1]])
    assert golden.score_case({'expect': []}, [])                                    # out of scope: no tool call


def test_scorer_requires_asking_on_ambiguous_cases():
    case = {'expect': 'clarify'}
    assert golden.score_case(case, [])
    assert golden.score_case(case, [{'name': 'update_task', 'arguments': {'confidence': 'low'}}])
    assert golden.score_case(case, [{'name': 'update_task', 'arguments': {'confidence': 'high', 'missing_fields': ['task_ref']}}])
    assert not golden.score_case(case, [{'name': 'update_task', 'arguments': {'confidence': 'high', 'task_ref': 'it'}}])
