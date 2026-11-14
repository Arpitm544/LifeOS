"""Read-only database connection test; never print credentials."""
import asyncio
import ssl
from pathlib import Path

import asyncpg
from app.database_tls import database_ssl_context
from dotenv import dotenv_values


async def main():
    values = dotenv_values(Path(__file__).parent / ".env")
    url = values.get("DATABASE_URL", "").replace("postgresql+asyncpg://", "postgresql://", 1)
    if not url:
        print("DATABASE_URL is missing from backend/.env")
        return 1
    try:
        context = database_ssl_context()
        connection = await asyncpg.connect(url, ssl=context, timeout=15)
        try:
            await connection.fetchval("SELECT 1")
            print("SUCCESS: database connected over verified TLS.")
        finally:
            await connection.close()
        return 0
    except ssl.SSLCertVerificationError as exc:
        print("Certificate verification failed:", exc.verify_message)
        print("A project-specific CA may be needed from Supabase's database SSL settings.")
        return 1
    except Exception as exc:
        print("Connection failed:", type(exc).__name__)
        print("Share this error type; do not share your .env or password.")
        return 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
