#!/usr/bin/env bash
# Starts the real backend for browser E2E against a throwaway database.
#
# DESTRUCTIVE to E2E_DATABASE_URL by design (drops and re-migrates `public`),
# so it refuses any database whose name does not end in `_test`.
# Needs the backend virtualenv (override with E2E_PYTHON) and a reachable Postgres.
set -euo pipefail

cd "$(dirname "$0")/../../backend"

export DATABASE_URL="${E2E_DATABASE_URL:-postgresql+psycopg://myvita:myvita@localhost:5432/myvita_e2e_test}"
export MIGRATION_DATABASE_URL="$DATABASE_URL"

database_name="${DATABASE_URL##*/}"
database_name="${database_name%%\?*}"
case "$database_name" in
  *_test) ;;
  *) echo "Refusing to reset '$database_name': E2E database names must end in _test." >&2; exit 1 ;;
esac

PYTHON="${E2E_PYTHON:-.venv/bin/python}"
BACKEND_PORT="${E2E_BACKEND_PORT:-8010}"
FRONTEND_PORT="${E2E_FRONTEND_PORT:-5174}"

# Throwaway values for this local run only; never reuse them anywhere real.
export JWT_SECRET_KEY="e2e-only-not-a-real-secret-do-not-reuse-0123456789abcdef"
export COOKIE_SECURE=false
export CORS_ORIGINS="[\"http://localhost:${FRONTEND_PORT}\"]"
export ALLOWED_HOSTS='["localhost","127.0.0.1"]'
# The suite seeds its own clinic through the public API, exactly like the backend tests do.
export ALLOW_PUBLIC_CLINIC_ONBOARDING=true
export ALLOW_PUBLIC_PATIENT_REGISTRATION=true
export ALLOW_DIRECT_STAFF_CREATION=true
export MFA_REQUIRED_FOR_STAFF=false

"$PYTHON" - <<'PY'
import os

from sqlalchemy import create_engine, text

engine = create_engine(os.environ["DATABASE_URL"])
with engine.begin() as connection:
    connection.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
    connection.execute(text("CREATE SCHEMA public"))
engine.dispose()
PY

"$PYTHON" -m alembic upgrade head
exec "$PYTHON" -m uvicorn app.main:app --host 127.0.0.1 --port "$BACKEND_PORT"
