-- Ученики, занятия и денежный журнал (D-02, D-03).

create table students (
    id           uuid primary key default gen_random_uuid(),
    full_name    text not null check (char_length(full_name) between 1 and 100),
    grade        smallint not null check (grade between 1 and 11),
    tutor_id     uuid not null references users (id),
    parent_id    uuid not null references users (id),
    -- Контакт родителя: видят только администратор и сам родитель (SR-06).
    parent_phone text not null check (parent_phone ~ '^\+7[0-9]{10}$'),
    -- Цена часа занятия в рублях.
    lesson_price integer not null check (lesson_price between 100 and 20000),
    created_at   timestamptz not null default now()
);

create index students_tutor_idx on students (tutor_id);
create index students_parent_idx on students (parent_id);

create table lessons (
    id             uuid primary key default gen_random_uuid(),
    student_id     uuid not null references students (id),
    tutor_id       uuid not null references users (id),
    starts_at      timestamptz not null,
    duration_min   smallint not null check (duration_min in (60, 90, 120)),
    status         text not null default 'planned'
                   check (status in ('planned', 'done', 'no_show_excused', 'no_show_burned')),
    -- Стоимость фиксируется в момент отчёта по цене ученика на этот момент.
    price_snapshot integer check (price_snapshot >= 0),
    reported_at    timestamptz,
    reported_by    uuid references users (id),
    created_at     timestamptz not null default now(),
    -- Отчёт либо отсутствует целиком, либо заполнен целиком.
    check ((status = 'planned') = (reported_at is null and reported_by is null))
);

create index lessons_student_idx on lessons (student_id, starts_at);
create index lessons_tutor_idx on lessons (tutor_id, starts_at);

-- Денежный журнал: баланс ученика = сумма amount его записей. Записи только добавляются.
create table ledger_entries (
    id          bigserial primary key,
    student_id  uuid not null references students (id),
    kind        text not null check (kind in ('payment', 'lesson_charge')),
    amount      integer not null check (amount <> 0),
    -- Не более одного списания на занятие (SR-07): второй барьер после условного перехода статуса.
    lesson_id   uuid unique references lessons (id),
    -- Один платёж банка зачисляется один раз (SR-10).
    external_id text unique,
    comment     text check (char_length(comment) <= 200),
    created_by  uuid not null references users (id),
    created_at  timestamptz not null default now(),
    check (
        (kind = 'payment' and amount > 0 and external_id is not null and lesson_id is null)
        or (kind = 'lesson_charge' and amount < 0 and lesson_id is not null and external_id is null)
    )
);

create index ledger_student_idx on ledger_entries (student_id, created_at);

-- Журнал нельзя исправить задним числом даже ошибкой в коде приложения.
create function ledger_append_only() returns trigger language plpgsql as $$
begin
    raise exception 'ledger_entries is append-only';
end;
$$;

create trigger ledger_no_update_delete
    before update or delete on ledger_entries
    for each row execute function ledger_append_only();
