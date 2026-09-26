# CheckBalance

Серверный сервис учёта занятий и баланса учеников онлайн-школы. Командный проект курса «Разработка безопасного программного обеспечения», команда EdTechBrothers.

[Паспорт](PROJECT.md)

## Локальный запуск

**Требования к окружению:** Docker с Compose v2 — либо Python 3.12+ и PostgreSQL 16.

```sh
cp .env.example .env          # задайте свои пароли
docker compose up --build -d
curl http://127.0.0.1:8000/health
# {"status":"ok","db":"ok"}
```

Без Docker:

```sh
python -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env          # укажите DATABASE_URL своей PostgreSQL
set -a; . ./.env; set +a
python -m app.migrate
uvicorn app.main:app --host 127.0.0.1 --port 8000
```
