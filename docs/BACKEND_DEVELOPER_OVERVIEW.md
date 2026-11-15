# LifeOS backend — developer handoff

## Branch purpose

`Backend` contains the FastAPI/PostgreSQL backend for LifeOS. It follows the PRD architecture: **Clerk owns authentication**, Supabase supplies PostgreSQL, and FastAPI derives the tenant only from a verified Clerk session token.

## What is implemented

| Area | Available now | Important notes |
| --- | --- | --- |
| Authentication and tenant boundaries | Clerk RS256 JWT verification, pinned issuer/JWKS, optional audience and authorized-party checks, transaction-scoped tenant context and RLS migration | Configure `CLERK_ISSUER`; never send Clerk secret keys to the API. |
| Browser access | CORS for `CORS_ORIGINS` (default `http://localhost:3000`, `http://127.0.0.1:3000`) | Preflight is answered before auth and rate limiting. |
| Data model | Tasks, events, routines, preferences, reminders, plan blocks, conflicts, audit logs, messages, subscriptions, suggestions, worker status | Migrations `001`–`007`, additive only. |
| Task and event lifecycle | Create/list/filter/edit/complete/drop task, record actual effort (`POST /api/tasks/{id}/actual-effort`); event create/edit/cancel | Deletes are state transitions (`dropped`). |
| Domain safety | Dependency graph/cycle detection, typed preferences, recurrence overrides, audit trail and 10-second Undo | Undo ignores derived priority fields, so later re-scores do not block it. |
| Chat pipeline | All nine PRD tools, context (preferences, top-30 open tasks with trigram matches first, today's events, last 6 messages, last touched item), validation, one clarification, confirmation for deletes and >3 writes, duplicate guard, custom reminders, message history | `POST /api/chat` response: `{message_id, reply, spoken_reply, actions[], conflicts[], clarification: {question, options} or null, confirmation: {prompt, options} or null, fallback}`. Reply "yes"/"no" to a confirmation. |
| Planning and Capacity Guard | Calibrated effort, priority `why` + breakdown, `POST /api/plan/rebuild`, Today with titles and free minutes, conflict detection after every change, option simulation with previews, resolve as one undoable batch, hypothetical capacity check | Working hours are planning supply; focus windows do not shrink it. Extended evenings are stored as `work_hours_overrides`. |
| Reminders | Rule-based reminder templates, `reminder_lead` preference, custom and plan-block reminders, Done/Snooze/Reschedule, notification centre; Done/Snooze from the push notification itself via `POST /api/push-actions/{id}` with a signed per-reminder `X-Push-Token` | Reschedule: action returns 3 slots, then `POST /api/reminders/{id}/reschedule {start_at}`. |
| Worker and push | `python -m app.worker`: reminders are claimed as `sending`, pushed with no row locks held, then marked `sent` (transient failures retry); per-user 10-minute merge serialized across workers; missed marking; per-job and per-user isolation for hourly re-score, once-a-day plan push and nightly retention; heartbeat (`GET /health/worker`) | Needs an administrative DB connection (`WORKER_DATABASE_URL`). Push endpoints are limited to `PUSH_ALLOWED_HOSTS`; one browser endpoint belongs to one user. |
| Insights | DB-backed metrics and 14-day chart, grounded suggestions (numbers must exist in the stats), Apply/Dismiss | LLM wording is optional; template suggestions are used otherwise. |
| Privacy | `GET /api/export`, `DELETE /api/account?confirmed=true` | Push keys are left out of exports. The Clerk account itself is deleted through Clerk. |
| Voice | `spoken_reply` (≤ 25 words, built by code from `reply`); transcription and speech run in the Next.js routes `/api/transcribe` and `/api/speak` with quotas reserved here | No `source` field; audio never reaches this API. |

## Verified evidence

Run from `backend/`:

```bash
.venv/bin/python -m pytest tests -q
```

Current local result: **149 passed, 3 skipped** (SQLite). The skips need PostgreSQL: `test_postgres_repairs.py` (2 tests, passes against a disposable Postgres 16 with `REPAIR_TEST_DATABASE_URL`, including migration 007) and `test_postgres_security.py`.

## Required environment

Copy `backend/.env.example` to a private `.env` and configure:

```dotenv
DATABASE_URL=postgresql+asyncpg://...
CLERK_ISSUER=https://YOUR_INSTANCE.clerk.accounts.dev
CLERK_JWKS_URL=https://YOUR_INSTANCE.clerk.accounts.dev/.well-known/jwks.json
CLERK_AUDIENCE=
CLERK_AUTHORIZED_PARTIES=http://localhost:3000
```

`ALLOW_DEMO_AUTH` must remain false outside a local development fixture. `.env`, database passwords, Clerk keys, virtual environments and generated caches must never be committed.

## Migration and release sequence

1. Back up any non-fixture database data.
2. Ensure the Supabase `auth.users`/`auth.uid()` baseline exists, then for a fresh database apply migrations `001` through `007` in order. For an existing database, apply only unapplied migrations according to `backend/migrations/README.md`; never rerun `001`. For an existing Supabase-auth UUID dataset, decide how legacy IDs map to Clerk IDs before applying `005`; it deliberately does not invent identity mappings.
3. Run the opt-in PostgreSQL/RLS test with a disposable or approved test database.
4. Configure the API service with a non-admin database role that can assume `lifeos_api`.
5. Send a Clerk session token in `Authorization: Bearer <token>` from the frontend.

## Remaining engineering work

- 50-utterance golden NLU set against the live model (the pipeline is tested with recorded tool calls).
- Load and performance checks (k6, p95 targets) and CI.
- Google Calendar import (P1) and the frontend service worker for push actions.

## Working conventions

- All timestamps crossing the API boundary are timezone-aware UTC values; derive local-day behavior from the user preference.
- Never trust `user_id` supplied by a request, a chat tool argument or the browser. Use the Clerk token subject and ownership-scoped queries.
- Use additive migrations only. Do not rewrite an applied migration.
- Keep unfinished API behavior explicit (`501`) rather than returning fabricated success data.
