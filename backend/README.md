# LifeOS backend

Groq Cloud can be used for chat and insight wording by setting `GROQ_API_KEY` and
optionally `GROQ_MODEL` in the server environment. When configured, Groq takes
precedence over Anthropic; the same backend validators execute all tool calls.
Keep API keys out of Git and browser bundles.

This service follows the PRD boundary: the LLM may interpret language and write replies, while backend code owns dates, validation, priorities, schedules, capacity checks, reminders, and state changes.

## What the API does

- **Chat** (`POST /api/chat`): one LLM tool-use call per message for all nine PRD tools (create/update/complete/delete task, create event, query schedule, plan day, check capacity, set preference). Every call is validated (Pydantic, dual date parse, ownership, duplicate guard), references such as "the report" or "it" are resolved with trigram matching plus the last touched item, at most one clarification is asked, and deletes or changes to more than 3 items wait for a "yes". The last 6 messages are sent as working memory and every message is stored. LLM outage (8 s budget, one retry) falls back to regex quick-add.
- **Planning**: priority formula with a stored `why` line and score breakdown, calibrated effort (estimate x measured factor per category), time-blocking scheduler, Today view, Capacity Guard after every change.
- **Capacity Guard**: `GET /api/conflicts/{id}/options` simulates extend hours / move a flexible item / renegotiate (with a draft message) and previews each plan; `POST /api/conflicts/{id}/resolve` applies one as a single undoable batch. `POST /api/capacity/check` with `hypothetical` answers "can I take this on?" without saving.
- **Reminders**: rule-based times with templates, custom "remind me at" overrides, plan-block reminders, Done / Snooze / Reschedule (next 3 free slots, then `POST /api/reminders/{id}/reschedule`), notification centre (`GET /api/reminders`).
- **Worker** (`python -m app.worker`): every 30 s delivers due reminders with Web Push (`FOR UPDATE SKIP LOCKED`, max 1 push per user per 10 min, extras merged), marks reminders older than 2 h as missed, re-scores priorities hourly, queues the daily plan push, applies retention nightly and writes a heartbeat (`GET /health/worker`).
- **Insights** (`GET /api/insights`): calibration factors, focus windows, plan adherence, overdue/snooze rates and a 14-day chart from the database; up to 3 suggestions whose numbers must come from the stats (template fallback), with Apply / Dismiss.
- **Privacy**: `GET /api/export` (JSON of every row) and `DELETE /api/account?confirmed=true`.
- **Browser access**: CORS for the Next.js origins in `CORS_ORIGINS`.

Voice input and spoken replies are handled by authenticated Next.js routes in the frontend; the backend chat API remains text-only and does not expose `spoken_reply`, `source` or transcription endpoints.

## Installation

Use Python 3.9 or newer:

```bash
cd backend
make install
make run
```

Copy `.env.example` to `.env` before connecting PostgreSQL/Supabase. The install command uses the local virtual environment and installs the package in editable mode with its test extra.

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

Fixtures include 14 days of labelled synthetic completions, a study effort factor of 1.6 (tasks store raw estimates; the planner applies the factor, so the 3 h report plans as 4.8 h), classes, café shifts, gym, preferences, upcoming tasks, and a reminder. Same account/date reruns skip existing fixtures; existing preferences are preserved. Changing the reference date creates another fixture set. All rows are inserted in one transaction. This seeds data only; it does not establish that the full demo flow or push delivery works.


The API contract keeps timestamps in UTC and accepts the client timezone for local-date parsing, as required by the PRD.


Local PostgreSQL without TLS: set `DATABASE_SSL=false`. Hosted databases keep the default `true`; the wheel includes the Supabase CA and fails if that packaged asset is missing.

When `GROQ_API_KEY` is set, chat and insight wording use `GROQ_MODEL` (default `openai/gpt-oss-20b`). Otherwise, chat uses `ANTHROPIC_API_KEY` and `ANTHROPIC_MODEL` (default `claude-sonnet-5-5`); insight wording uses `ANTHROPIC_INSIGHT_MODEL` (default `claude-haiku-5-5`). No-action provider replies do not create tasks. Missing credentials, transport failures and malformed provider responses use quick-add; past deadlines ask for clarification.

Apply migrations in numeric order: `006` must already be applied before `007` (see `migrations/README.md`). Run the worker as a second process:

```bash
.venv/bin/python -m app.worker
```

The worker reads due reminders for every user, so it needs an administrative database connection: set `WORKER_DATABASE_URL` (it falls back to `DATABASE_URL` for local development). Never run it on the tenant-scoped API login (`lifeos_api`); RLS would hide other users' reminders.

Web Push needs `VAPID_PUBLIC_KEY` / `VAPID_PRIVATE_KEY`; without them reminders still appear in the notification centre and on Today. Subscriptions are accepted only for the browser push services in `PUSH_ALLOWED_HOSTS`.

Runtime rate limits use PostgreSQL transactions and a per-user/bucket advisory lock across all workers. Expired rows for inactive users are removed on subsequent API traffic by the bounded-permission cleanup function. Development tests may inject the in-memory limiter.
