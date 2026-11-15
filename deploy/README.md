# Deploying LifeOS on one server

Runs the Next.js site, the FastAPI API, the reminder worker and Caddy (automatic HTTPS) with Docker Compose on a single Linux server. The database stays on Supabase.

## Server setup

1. Create an Ubuntu 24.04 server (2 vCPU / 4 GB works) and open ports 80 and 443.
2. Install Docker: `curl -fsSL https://get.docker.com | sh`.
3. Copy this repository to the server, e.g. `/opt/lifeos`.

## Configuration

Create three files on the server (never commit them):

- `backend/.env`: copy `backend/.env.example` and fill it in. For production set:
  - `ENVIRONMENT=production`, `DATABASE_SSL=true`
  - `CORS_ORIGINS` and `CLERK_AUTHORIZED_PARTIES` = `https://<APP_HOST>`
  - `FRONTEND_URL=https://<APP_HOST>`, `PUBLIC_API_URL=https://<API_HOST>`
  - `GOOGLE_REDIRECT_URI=https://<API_HOST>/api/google/callback` (also add it to the Google OAuth client)
- `frontend/.env.local`: copy `frontend/.env.example`, with `NEXT_PUBLIC_API_URL=https://<API_HOST>`.
- `deploy/.env`:

  ```
  APP_HOST=app.example.com
  API_HOST=api.example.com
  NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=pk_...
  ```

Both hosts must point at the server's IP. Without a domain, `app.<ip-with-dashes>.sslip.io` and `api.<ip-with-dashes>.sslip.io` work.

Apply the SQL migrations in `backend/migrations` to the database before the first start (see `backend/migrations/README.md`).

## Start / update

```bash
cd /opt/lifeos/deploy
docker compose up -d --build
docker compose ps
docker compose logs -f api worker
```

Check `https://<API_HOST>/health` and `https://<API_HOST>/health/worker`.
