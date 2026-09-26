-- Пользователи и серверные сессии (D-01).
-- В sessions хранится только SHA-256 токена: утечка таблицы не даёт готовых токенов.

create table users (
    id            uuid primary key default gen_random_uuid(),
    login         text not null unique check (login ~ '^[a-z0-9_.]{3,32}$'),
    password_hash text not null,
    full_name     text not null check (char_length(full_name) between 1 and 100),
    role          text not null check (role in ('admin', 'tutor', 'parent')),
    is_active     boolean not null default true,
    created_at    timestamptz not null default now()
);

create table sessions (
    token_hash bytea primary key check (octet_length(token_hash) = 32),
    user_id    uuid not null references users (id) on delete cascade,
    created_at timestamptz not null default now(),
    expires_at timestamptz not null,
    revoked_at timestamptz
);

create index sessions_user_idx on sessions (user_id);
