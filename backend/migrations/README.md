# Step 2 database rollout

SQL migrations are authoritative for constraints and RLS. ORM mappings do not replace migration execution.

Apply in order as an administrator in Supabase SQL Editor:

- `001_initial.sql`: already executed by the user. Do not rerun: CREATE POLICY statements are not repeatable.
- `002_idempotency_scope.sql`: apply once if not already applied. Adds per-user key scope and request hashing.
- `003_integrity_and_rls.sql`: required Supabase Auth baseline for fresh bootstrap and pre-Clerk upgrades; apply once after 002. It rejects pre-existing roles with memberships, ownership or explicit grants.
- `004_routine_instances.sql`: adds routine anchor/override fields and audit batch ids.
- `005_clerk_identity.sql`: required Clerk cutover. Converts LifeOS tenant ids from UUID to text, removes Supabase Auth ownership links, creates local Clerk-user FKs and rewrites RLS policies around the transaction-scoped Clerk subject.
- `006_runtime_safety.sql`: shared atomic rate-limit storage, expiry cleanup and current-date routine default.
- `007_backend_enhancements.sql`: task priority `why`/breakdown columns, reminder kind check and indexes, `suggestions` table (RLS, `lifeos_api` grants), `worker_status` heartbeat table (admin only), analytics indexes and the `prune_lifeos_history()` retention function (scheduled with pg_cron when that extension is installed).
- `008_google_calendar.sql`: `google_connections` (one row per user, Fernet-encrypted refresh token, RLS, `lifeos_api` grants) for read-only Google Calendar sync.

Each of 002 and 003 is atomic. Invalid/orphaned existing data aborts 003 and rolls back; diagnose the failing constraint rather than deleting data. Avoid other applications sharing these public table names. Record successful migration execution before rerunning scripts.

## Runtime role

API transactions use `SET LOCAL ROLE lifeos_api` and transaction-local JWT subject/claims, including transactions after endpoint commits. The NOLOGIN role has DML grants only on LifeOS tables and no BYPASSRLS, role/database creation or superuser rights. Migration 003 grants membership to postgres for the current development connection. Switching role protects ordinary application queries but does not make the administrator credentials least privileged.

For production, provision a separate database login through the project administrator, grant it only `lifeos_api` membership and put its connection string in server `.env`. Do not grant ownership, superuser, BYPASSRLS or unrelated roles. Never grant membership to frontend roles or expose administrator credentials in the frontend.

Migration/demo scripts intentionally use unscoped administrative sessions. The reminder worker (`python -m app.worker`) needs cross-user access, so it uses an administrative connection (`WORKER_DATABASE_URL`, defaulting to `DATABASE_URL`); the API role stays tenant scoped. In production give the worker its own login rather than reusing the migration administrator.

## Clerk authentication configuration

Set `CLERK_ISSUER` to the Clerk Frontend API issuer and either set `CLERK_JWKS_URL` or use its default `/.well-known/jwks.json` endpoint. Token-provided URLs are ignored. RS256 verification checks kid/type/algorithm, signature, issuer, expiry, a `user_…` subject, optional configured audience, and optional authorized-party allowlist. Keys are cached up to five minutes. Fetch failures return 503; invalid tokens return 401. Logout/revocation is not checked live per request; JWT expiry applies.

The API intentionally does not accept legacy HS256 or Supabase Auth tokens. Clerk publishable/secret keys are not JWT verification keys and must never be committed. Demo-header auth stays disabled by default and cannot work in production mode.

## Real database acceptance

Use a disposable migrated Supabase test project. Configure `TEST_DATABASE_URL` privately in the terminal environment, then run from backend:

```bash
RUN_POSTGRES_TESTS=1 .venv/bin/python -m pytest tests/test_postgres_security.py -v
```

The test inserts two synthetic local Clerk users/tasks inside a transaction, switches to the API role, verifies isolated reads/writes and cross-owner FK rejection, then rolls back all inserted rows. Without both opt-in and URL it skips. It neither installs migrations nor proves fresh/upgrade compatibility. Test 001→…→007 on a fresh project and the unapplied files on an existing migrated project before rollout.

The isolated PostgreSQL repair suite verifies fresh/upgrade migrations, rollback, role validation, RLS and concurrency on a disposable cluster. It does not validate a hosted Supabase project or provision its production login.

## Fresh bootstrap and existing upgrades

A fresh database needs the Supabase `auth.users`/`auth.uid()` baseline before 001–006. An existing database runs only unapplied files in numeric order. Record each successful migration; 001 and 003 are not repeatable. Apply 005 only during a maintenance window after verifying a complete identity mapping and taking a backup.

For existing UUID owners, prepare an explicit mapping in the **same SQL session** as migration 005, outside a transaction (005 starts its own):

```sql
create temporary table lifeos_identity_map (
  legacy_id uuid primary key,
  clerk_id text not null unique check (clerk_id like 'user\_%' escape '\')
);
-- Supply verified identities, never infer accounts from unverified email addresses.
insert into lifeos_identity_map values ('11111111-1111-4111-8111-111111111111', 'user_REPLACE_ME');
-- Execute 005_clerk_identity.sql in this same session, then 006.
```

005 refuses missing mappings, rewrites every tenant reference, preserves local user profiles and inserts missing local users before validating the new FKs. Empty databases need no mapping entries. The mapping must be one-to-one; account merges need a separate reviewed data migration. Retry a failed 005 after repairing the mapping; the transaction rolls back all schema/data changes.

New routine anchors use explicit input or the user's local creation date. Existing routines created under the old `2026-01-01` default have no stored creation date: do not blindly reset these anchors, which could restart completed COUNT rules. Before rollout, identify affected routines and backfill their verified first-occurrence date (YYYY-MM-DD) per routine ID. This requires operator input; the application cannot reconstruct it.

For the repair acceptance suite, point `REPAIR_TEST_DATABASE_URL` at an **isolated disposable PostgreSQL cluster without a lifeos_api role**, then from the `backend` directory run `python -m pytest tests/test_postgres_repairs.py -q`. It creates/drops test databases and the test role; never point it at a shared or production cluster.
