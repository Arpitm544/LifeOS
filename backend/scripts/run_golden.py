"""Run the golden NLU set (tests/golden.yaml) against the configured LLM and score it.

Usage (from backend/):  .venv/bin/python scripts/run_golden.py [--only s01,m03] [--json out.json]
Exit code 1 when accuracy is under the PRD bar (90%).
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from collections import Counter
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
GOLDEN = ROOT / 'tests' / 'golden.yaml'
PASS_BAR = 0.90
VALID_TOOLS = {'create_task', 'update_task', 'complete_task', 'delete_task', 'create_event',
               'query_schedule', 'plan_day', 'check_capacity', 'set_preference'}


def load_golden(path: Path = GOLDEN) -> dict:
    return yaml.safe_load(path.read_text())


def _present(value) -> bool:
    return value not in (None, '', [], {})


def call_matches(expected: dict, call: dict) -> bool:
    if call.get('name') != expected['tool']:
        return False
    args = call.get('arguments') or {}
    if any(not _present(args.get(field)) for field in expected.get('required', [])):
        return False
    if any(args.get(key) != value for key, value in (expected.get('match') or {}).items()):
        return False
    ref = expected.get('ref')
    if ref and str(args.get('task_id') or '') != ref and not _present(args.get('task_ref')):
        return False  # the backend resolves task_ref by trigram; an id must be the right one
    return True


def asked(calls: list[dict]) -> bool:
    if not calls:
        return True
    return any((call.get('arguments') or {}).get('confidence') in ('low', 'medium')
               or _present((call.get('arguments') or {}).get('missing_fields')) for call in calls)


def score_case(case: dict, calls: list[dict]) -> bool:
    """Exact intents (as a multiset) and every required field; 'clarify' means the model must ask."""
    expect = case['expect']
    if expect == 'clarify':
        return asked(calls)
    if Counter(item['tool'] for item in expect) != Counter(call.get('name') for call in calls):
        return False
    remaining = list(calls)
    for expected in expect:
        match = next((call for call in remaining if call_matches(expected, call)), None)
        if match is None:
            return False
        remaining.remove(match)
    return True


async def run(only: set[str] | None) -> dict:
    sys.path.insert(0, str(ROOT))
    from app.services.llm_client import FallbackLLMClient, configured_llm
    data = load_golden()
    client = configured_llm()
    if isinstance(client, FallbackLLMClient):
        raise SystemExit('No LLM configured: set a provider key in backend/.env')
    results = []
    for case in data['cases']:
        if only and case['id'] not in only:
            continue
        started = time.monotonic()
        try:
            response = await client.parse(text=case['text'], context=data['context'])
            calls = [call.model_dump() for call in response.tool_calls]
            error = None
        except Exception as exc:  # a timeout counts as a failure
            calls, error = [], type(exc).__name__
        ok = error is None and score_case(case, calls)
        results.append({'id': case['id'], 'group': case['group'], 'ok': ok, 'ms': int((time.monotonic() - started) * 1000),
                        'calls': calls, 'error': error})
        print(f"{'PASS' if ok else 'FAIL'} {case['id']:4} {case['text'][:60]}" + (f'  [{error}]' if error else ''))
    by_group = {}
    for group in ('simple', 'multi', 'ambiguous'):
        rows = [r for r in results if r['group'] == group]
        if rows:
            by_group[group] = sum(r['ok'] for r in rows) / len(rows)
    latencies = sorted(r['ms'] for r in results)
    accuracy = sum(r['ok'] for r in results) / len(results) if results else 0.0
    return {'accuracy': accuracy, 'by_group': by_group, 'p95_ms': latencies[int(0.95 * (len(latencies) - 1))] if latencies else 0,
            'results': results}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--only', help='comma-separated case ids')
    parser.add_argument('--json', help='write full results to this file')
    args = parser.parse_args()
    report = asyncio.run(run(set(args.only.split(',')) if args.only else None))
    print(f"\naccuracy {report['accuracy']:.0%} (bar {PASS_BAR:.0%})  " +
          '  '.join(f'{g} {v:.0%}' for g, v in report['by_group'].items()) + f"  p95 {report['p95_ms']} ms")
    if args.json:
        Path(args.json).write_text(json.dumps(report, indent=2, default=str))
    raise SystemExit(0 if report['accuracy'] >= PASS_BAR else 1)


if __name__ == '__main__':
    main()
