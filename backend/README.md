# LifeOS backend

This service follows the PRD boundary: the LLM may interpret language and write replies, while backend code owns dates, validation, priorities, schedules, capacity checks, reminders, and state changes.

## Current foundation

- FastAPI service with `/health` and `/api/chat`.
- Pydantic request contracts for chat and task creation.
- Provider-neutral settings for Supabase/Postgres and Anthropic.
- Deterministic priority formula with P1/P2/P3 bands and explainable `why` text.
- Date-aware regex quick-add fallback for LLM outages/timeouts.
- Pytest contract for the priority formula.

## Installation

Use Python 3.9 or newer:

```bash
cd backend
make install
make run
```

Copy `.env.example` to `.env` before connecting PostgreSQL/Supabase. The install command uses the local virtual environment and installs the package in editable mode with its test extra.

## Planned implementation order
### Demo fixtures

Use a dedicated existing Clerk demo account. The seed script does not create an Auth account or apply migrations. Configure `DATABASE_URL` in `.env` and apply migrations first.

Preview without dependencies or a database:

```bash
python3 seed_demo.py --user-id user_demo --date 2026-11-14 --dry-run
```

Load using the actual demo Clerk subject:

```bash
.venv/bin/python seed_demo.py --user-id YOUR_DEMO_CLERK_SUBJECT
```

Fixtures include 14 days of labelled synthetic completions, a study effort factor of 1.6, classes, café shifts, gym, preferences, upcoming tasks, and a reminder. Same account/date reruns skip existing fixtures; existing preferences are preserved. Changing the reference date creates another fixture set. All rows are inserted in one transaction. This seeds data only; it does not establish that the full demo flow or push delivery works.


1. SQLAlchemy models and migrations for tasks, events, plan blocks, conflicts, reminders, preferences, messages, activity events, and action logs.
2. JWT authentication and user-scoped repository methods/RLS policies.
3. NLU tool contracts, date dual-parse validation, ownership checks, idempotent chat orchestration, and 10-second undo.
4. Scheduler, capacity guard, reminders/worker, insights, and remaining API routes.

The API contract keeps timestamps in UTC and accepts the client timezone for local-date parsing, as required by the PRD.


Local PostgreSQL without TLS: set `DATABASE_SSL=false`. Hosted databases keep the default `true`; the wheel includes the Supabase CA and fails if that packaged asset is missing.

Chat uses `ANTHROPIC_API_KEY` and `ANTHROPIC_MODEL` (default `claude-sonnet-4-5`). No-action provider replies do not create tasks. Missing credentials, transport failures and malformed provider responses use quick-add; past deadlines ask for clarification.

Apply migration 006 before starting this version. Runtime rate limits use PostgreSQL transactions and a per-user/bucket advisory lock across all workers. Expired rows for inactive users are removed on subsequent API traffic by the bounded-permission cleanup function. Development tests may inject the in-memory limiter.
