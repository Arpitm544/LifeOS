# Step 2 database rollout

SQL migrations are authoritative for constraints and RLS. ORM mappings do not replace migration execution.

Apply in order as an administrator in Supabase SQL Editor:

- `001_initial.sql`: already executed by the user. Do not rerun: CREATE POLICY statements are not repeatable.
- `002_idempotency_scope.sql`: apply once if not already applied. Adds per-user key scope and request hashing.
- `003_integrity_and_rls.sql`: historical Supabase Auth baseline. Apply once after 002 only for an existing pre-Clerk database.
- `004_routine_instances.sql`: adds routine anchor/override fields and audit batch ids.
- `005_clerk_identity.sql`: required Clerk cutover. Converts LifeOS tenant ids from UUID to text, removes Supabase Auth ownership links, creates local Clerk-user FKs and rewrites RLS policies around the transaction-scoped Clerk subject.

Each of 002 and 003 is atomic. Invalid/orphaned existing data aborts 003 and rolls back; diagnose the failing constraint rather than deleting data. Avoid other applications sharing these public table names. Record successful migration execution before rerunning scripts.

## Runtime role

API transactions use `SET LOCAL ROLE lifeos_api` and transaction-local JWT subject/claims, including transactions after endpoint commits. The NOLOGIN role has DML grants only on LifeOS tables and no BYPASSRLS, role/database creation or superuser rights. Migration 003 grants membership to postgres for the current development connection. Switching role protects ordinary application queries but does not make the administrator credentials least privileged.

For production, provision a separate database login through the project administrator, grant it only `lifeos_api` membership and put its connection string in server `.env`. Do not grant ownership, superuser, BYPASSRLS or unrelated roles. Never grant membership to frontend roles or expose administrator credentials in the frontend.

Migration/demo scripts intentionally use unscoped administrative sessions. A worker needing cross-user access requires a separate worker credential design; the API role is tenant scoped.

## Clerk authentication configuration

Set `CLERK_ISSUER` to the Clerk Frontend API issuer and either set `CLERK_JWKS_URL` or use its default `/.well-known/jwks.json` endpoint. Token-provided URLs are ignored. RS256 verification checks kid/type/algorithm, signature, issuer, expiry, a `user_…` subject, optional configured audience, and optional authorized-party allowlist. Keys are cached up to five minutes. Fetch failures return 503; invalid tokens return 401. Logout/revocation is not checked live per request; JWT expiry applies.

The API intentionally does not accept legacy HS256 or Supabase Auth tokens. Clerk publishable/secret keys are not JWT verification keys and must never be committed. Demo-header auth stays disabled by default and cannot work in production mode.

## Real database acceptance

Use a disposable migrated Supabase test project. Configure `TEST_DATABASE_URL` privately in the terminal environment, then run from backend:

```bash
RUN_POSTGRES_TESTS=1 .venv/bin/python -m pytest tests/test_postgres_security.py -v
```

The test inserts two synthetic local Clerk users/tasks inside a transaction, switches to the API role, verifies isolated reads/writes and cross-owner FK rejection, then rolls back all inserted rows. Without both opt-in and URL it skips. It neither installs migrations nor proves fresh/upgrade compatibility. Test 001→002→003→004→005 on a fresh project and 004→005 on an existing migrated project before marking Step 2 complete.

No live migration, role grant, login provisioning or database integration test was executed automatically.
