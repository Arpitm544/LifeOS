# LifeOS end-to-end and load tests

Kept outside `frontend/` so the app's lockfile is untouched.

## Playwright (PRD Appendix B workflows)

1. Start the API with demo auth (development only): `cd ../backend && set -a && source .env.demo && set +a && .venv/bin/python -m uvicorn app.main:app`
2. Optionally start the frontend (`cd ../frontend && npm run dev`) for `ui.spec.ts`.
3. Run:

```bash
npm install && npx playwright install chromium
E2E_API_URL=http://127.0.0.1:8000 npx playwright test
```

`workflows.spec.ts` creates a throwaway demo user (`E2E_DEMO_USER_ID`, default `user_e2e_<timestamp>`) and deletes its account at the end.

## k6 load test

```bash
k6 run -e API_URL=http://127.0.0.1:8000 k6/chat-load.js
```

100 virtual users for 5 minutes against `/api/chat` and `/api/today`. Run it with no LLM key so it measures LifeOS logic (target p95 ≤ 300 ms).

## Golden NLU set

Lives with the backend: `backend/tests/golden.yaml`, run with `cd ../backend && .venv/bin/python scripts/run_golden.py` (needs an LLM key).
