# LifeOS backend — developer handoff

## Branch purpose

`Backend` contains the FastAPI/PostgreSQL backend for LifeOS. It follows the PRD architecture: **Clerk owns authentication**, Supabase supplies PostgreSQL, and FastAPI derives the tenant only from a verified Clerk session token.

## What is implemented locally

| Area | Available now | Important notes |
| --- | --- | --- |
| Authentication and tenant boundaries | Clerk RS256 JWT verification, pinned issuer/JWKS, optional audience and authorized-party checks, transaction-scoped tenant context and RLS migration | Configure `CLERK_ISSUER`; never send Clerk secret keys to the API. Migration `005_clerk_identity.sql` is required after `001`–`004`. |
| Data model | Tasks, events, routines, preferences, reminders, plan blocks, conflicts, audit logs, messages, subscriptions and worker heartbeat | User IDs are Clerk text subjects; all domain item IDs remain UUIDs. |
| Task and event lifecycle | Create/list/filter/edit/complete/drop task; event create/edit/cancel; ownership checks | Deletes are intentional state transitions, not destructive row removal in normal flows. |
| Domain safety | Dependency graph/cycle detection, blocked/unblocked refresh, typed preferences, recurrence instance overrides, audit trail and 10-second Undo | Batch changes must be undone as a whole. |
| Planning foundation | Calendar-aware priority recalculation, event/routine busy time, work/focus windows, plan rebuild, persisted conflicts and timezone-aware Today endpoint | Step 4 is still in progress: apply/Undo and concurrency behavior are not finished. |
| Reminder foundation | Task/event reminder generation and quiet-hour adjustment during mutations | Web Push, durable polling, retries and scheduled workers are not implemented. |

## Verified evidence

Run from `backend/`:

```bash
.venv/bin/python -m pytest tests -q
```

Current local result: **81 passed, 1 skipped**. The skip is intentional: `test_postgres_security.py` requires an explicitly configured, migrated PostgreSQL database.

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
2. For a fresh Supabase-compatible database, apply migrations `001` through `006` in order. For an existing database, apply only unapplied migrations according to `backend/migrations/README.md`; never rerun `001`. For an existing Supabase-auth UUID dataset, decide how legacy IDs map to Clerk IDs before applying `005`; it deliberately does not invent identity mappings.
3. Run the opt-in PostgreSQL/RLS test with a disposable or approved test database.
4. Configure the API service with a non-admin database role that can assume `lifeos_api`.
5. Send a Clerk session token in `Authorization: Bearer <token>` from the frontend.

## Remaining engineering work

- Finish Step 4: schedule preview/confirmed apply/Undo, priority configuration, concurrency serialization and performance fixtures.
- Step 5: provider-backed AI chat/tool calling and golden conversation tests.
- Step 6: Web Push, worker delivery, retry/dedupe and scheduled jobs.
- Step 7: real insights, export/deletion/retention and deployment security hardening.
- Step 8: CI, integration/performance verification and release handoff.

## Working conventions

- All timestamps crossing the API boundary are timezone-aware UTC values; derive local-day behavior from the user preference.
- Never trust `user_id` supplied by a request, a chat tool argument or the browser. Use the Clerk token subject and ownership-scoped queries.
- Use additive migrations only. Do not rewrite an applied migration.
- Keep unfinished API behavior explicit (`501`) rather than returning fabricated success data.
