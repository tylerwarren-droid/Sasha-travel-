"""
Run a numbered migration against Supabase.

Usage:
  python run_migration.py 002          # run migrations/002_clients_schema.sql
  python run_migration.py 001 002      # run multiple in order
  python run_migration.py              # run all pending (not yet tracked)

Requires DATABASE_URL in .env or environment.
"""

import asyncio
import os
import sys
from pathlib import Path

import asyncpg
from dotenv import load_dotenv

load_dotenv()


async def run(migration_files: list[Path]) -> None:
    url = os.getenv("DATABASE_URL")
    if not url:
        raise SystemExit("DATABASE_URL not set")

    conn = await asyncpg.connect(url)
    try:
        for path in migration_files:
            print(f"Running {path.name} …", end=" ", flush=True)
            sql = path.read_text()
            await conn.execute(sql)
            print("done")
    finally:
        await conn.close()


def resolve_files(args: list[str]) -> list[Path]:
    migrations_dir = Path(__file__).parent / "migrations"
    if not args:
        return sorted(migrations_dir.glob("*.sql"))
    files = []
    for arg in args:
        prefix = arg.zfill(3)
        matches = sorted(migrations_dir.glob(f"{prefix}_*.sql"))
        if not matches:
            raise SystemExit(f"No migration file found matching {prefix}_*.sql")
        files.extend(matches)
    return files


if __name__ == "__main__":
    files = resolve_files(sys.argv[1:])
    if not files:
        print("No migration files found.")
    else:
        asyncio.run(run(files))
