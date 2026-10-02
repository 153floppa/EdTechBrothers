#!/usr/bin/env sh
# Локальный запуск без Docker для API (PostgreSQL уже запущена, DATABASE_URL задан в окружении или .env).
set -eu
cd "$(dirname "$0")/.."
if [ -f .env ]; then set -a; . ./.env; set +a; fi
python -m app.migrate
exec uvicorn app.main:app --host 127.0.0.1 --port 8000
