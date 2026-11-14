# Backend branch publication plan

## Objective

Publish the audited local LifeOS backend to the existing GitHub branch **`Backend`** using twelve small, reviewable, independently testable commits. This is a publication plan only: it does not authorize rewriting branch history, force-pushing, committing secrets, or claiming unverified production behavior.

## Pre-push gate

1. Clone `Arpitm544/LifeOS` and check out the capitalized `Backend` branch (not a new lowercase `backend` branch).
2. Compare the remote branch against this workspace and preserve the existing README and PRD.
3. Copy only reviewed application, migrations, tests, dependency manifests and documentation. Never copy `.env`, `.venv`, caches, test databases, downloaded private certificates, or user data.
4. Replace any configuration values with placeholders in `.env.example`; rotate the database password that was shared during setup before deployment.
5. Run the unit suite, startup/OpenAPI check, secret scan and staged-diff review before every commit. Run the live PostgreSQL/RLS test only after migrations are applied to a disposable or approved Supabase environment.

## The twelve commits

| # | Commit | Contents | Verification before commit |
| --- | --- | --- | --- |
| 1 | `chore(backend): import reproducible FastAPI scaffold` | Project metadata, dependency constraints, application entry point, configuration, `.gitignore`, `.env.example`, health endpoint. | Dependency install, `pip check`, app imports. |
| 2 | `feat(db): add LifeOS domain schema and additive migrations` | ORM models plus migrations `001`–`004`; migration/readme documentation. | Fresh schema SQL review; migration ordering verified. |
| 3 | `feat(auth): verify Clerk JWTs and scoped database sessions` | Clerk RS256/JWKS verifier, TLS configuration, database role/context integration and safe auth defaults. | Invalid issuer/audience/authorized-party/expiry/token tests; no secrets in staged diff. |
| 4 | `test(security): cover tenant isolation and database acceptance gates` | JWT boundary tests and opt-in PostgreSQL/RLS test suite. | Local security tests pass; live tests remain explicitly opt-in until run. |
| 5 | `feat(tasks): add validated task and event lifecycle APIs` | Task/event schemas, create/read/edit/complete/cancel/delete flows, filters and ownership checks. | Task/event API and validation tests. |
| 6 | `feat(domain): add dependencies audit and transactional undo` | Dependency graph checks, blocked status refresh, audit events, 10-second Undo and safe batch semantics. | Undo, stale-state, expiry and dependency-cycle tests. |
| 7 | `feat(preferences): add typed preferences and recurring routines` | Preference validation/acceptance, routine CRUD, recurrence expansion and instance overrides. | Preference, recurrence and DST-window tests. |
| 8 | `feat(reminders): build deterministic reminder state generation` | Generated task/event reminder calculation, quiet-hours handling and mutation-time recomputation only. Excludes push delivery workers. | Reminder service and lifecycle tests. |
| 9 | `feat(planning): derive priorities and plans from calendar data` | Priority engine, scheduler, planning service, database-backed plan rebuild and routine/event availability. | Planner fixture, no-overlap and deadline tests. |
| 10 | `feat(capacity): expose local Today and capacity views` | Today endpoint timezone behavior, plan block validation and capacity conflict output. | Local-day, event-buffer and capacity-conflict tests. |
| 11 | `refactor(api): remove unsupported placeholder behavior` | Remove or clearly return `501 Not Implemented` for unfinished LLM, insights, worker/push and conflict-resolve features; keep no fabricated results. | Route contract review and full suite. |
| 12 | `docs(backend): add delivery evidence and deployment handoff` | Eight-step roadmap, environment/migration handoff, current test evidence and PR checklist. | Full suite, startup/OpenAPI check, secret scan, staged diff. |

## Pull request discipline

- Push ordinary commits only; never force-push `Backend`.
- Open a PR from `Backend` only if the repository workflow permits it; otherwise request review on the branch with the same checklist.
- PR description must state: migrations to apply, commands run, test counts, intentionally skipped live tests, endpoints still returning `501`, and rollback instructions.
- Do not mark Steps 4–8 complete merely because code is published. Completion requires their listed acceptance gates.

## Current publication blockers

- This workspace has no `.git` directory, so it is not yet attached to the actual GitHub branch.
- The opt-in PostgreSQL RLS/locking suite has not been executed against Supabase.
- Step 4 is in progress; Steps 5–8 contain work that must either be completed or explicitly remain unsupported before release.
