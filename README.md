# CheckBalance

Серверный сервис учёта занятий и баланса учеников онлайн-школы: администратор зачисляет оплату, преподаватель отчитывается о занятии, стоимость списывается с баланса ровно один раз, родитель видит остаток и историю.

Командный проект курса «Разработка безопасного программного обеспечения», команда EdTechBrothers.

[Паспорт](PROJECT.md) · [Требования](docs/requirements.md) · [Модель угроз](docs/threat-model.md) · [Решения](docs/design-decisions.md) · [Вклад](CONTRIBUTIONS.md) · [Учёт ИИ](AI_USAGE.md)

## Локальный запуск

**Требования к окружению:** Docker с Compose v2 — либо Python 3.12+ и PostgreSQL 16.

### Вариант 1. Docker Compose

```sh
cp .env.example .env          # задайте свои пароли
docker compose up --build -d
docker compose exec api python -m app.cli create-admin --login admin
curl http://127.0.0.1:8000/health
```

Команда `create-admin` берёт пароль из `BOOTSTRAP_ADMIN_PASSWORD` в `.env` или спрашивает его.

### Вариант 2. Без Docker

```sh
python -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env          # укажите DATABASE_URL своей PostgreSQL
set -a; . ./.env; set +a
python -m app.migrate
python -m app.cli create-admin --login admin
./scripts/run-local.sh
```

### Проверка работоспособности

```sh
curl http://127.0.0.1:8000/health
# {"status":"ok","db":"ok"}

ADMIN_PASSWORD='<пароль администратора>' python scripts/smoke.py
```

**Ожидаемый результат** `scripts/smoke.py`: строки `OK ...` для каждого шага — вход, создание преподавателей, родителя и ученика, оплата 5000 → баланс 5000, преподаватель не видит телефон и баланс, отчёт чужого преподавателя → 404, отчёт → списано 2000, повторный отчёт → 409, родитель видит 3000, после logout токен → 401 — и в конце `SMOKE PASSED`.

Это подтверждение запуска, а не доказательство всех требований безопасности: требования проверяются тестами ниже и планами в [решениях](docs/design-decisions.md).

## Тесты

Нужна **отдельная пустая** база PostgreSQL: тесты пересоздают в ней схему `public`.

```sh
createdb checkbalance_test
TEST_DATABASE_URL=postgresql://<user>@localhost:5432/checkbalance_test python -m pytest
```

| Файл | Что проверяет |
| --- | --- |
| `tests/test_security.py` | argon2id, случайность токенов, хранение только SHA-256 |
| `tests/test_auth_api.py` | SR-01–SR-04: отказ без сессии, отзыв при logout, истечение, единый ответ при неудачном входе |
| `tests/test_input.py` | SR-11: повторные и лишние ключи, типы, размер, кодировка |
| `tests/test_access.py` | SR-05, SR-06, SR-10: область видимости, поля по роли, повтор оплаты |
| `tests/test_lessons.py` | SR-07, SR-08: одно списание при параллельных отчётах, будущее и чужое занятие |

## API

| Метод и путь | Кто | Что делает |
| --- | --- | --- |
| `GET /health` | все | Доступность API и БД |
| `POST /auth/login` | все | Вход, выдаёт токен |
| `POST /auth/logout` | любой с сессией | Отзыв текущего токена |
| `GET /me` | любой с сессией | Текущий пользователь |
| `POST /users` | администратор | Создать преподавателя или родителя |
| `POST /students` | администратор | Создать ученика |
| `GET /students`, `GET /students/{id}` | все роли, в своей области | Ученики; набор полей зависит от роли |
| `POST /students/{id}/payments` | администратор | Зачислить оплату по номеру операции банка |
| `GET /students/{id}/ledger` | администратор, родитель | Баланс и история оплат и списаний |
| `POST /lessons` | преподаватель | Создать занятие своему ученику |
| `GET /lessons?student_id=` | все роли, в своей области | Занятия ученика |
| `POST /lessons/{id}/report` | преподаватель | Отчёт о занятии со списанием |

Пример: `curl -X POST http://127.0.0.1:8000/auth/login -H 'Content-Type: application/json' -d '{"login":"admin","password":"..."}'`, затем заголовок `Authorization: Bearer <token>`.

## Структура

```text
app/          auth.py · access.py · input.py · students.py · lessons.py · security.py · db.py · migrate.py · cli.py · main.py
migrations/   001_users_sessions.sql · 002_students_lessons_ledger.sql
tests/        интеграционные и модульные тесты
scripts/      smoke.py · run-local.sh
docs/         требования, модель угроз, проектные решения
```
