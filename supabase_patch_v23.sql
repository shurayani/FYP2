-- Patch #23: run ONCE in the Supabase SQL editor.
-- 1. the category IPECS suggested for a transaction (for the real-use accuracy on the Admin dashboard)
alter table transactions add column if not exists predicted_category_id text;
-- 2. recurring bills (reminders)
create table if not exists recurring_bills (
  id text primary key, user_id text not null references users(id), name text not null,
  amount double precision not null, category_id text not null references categories(id),
  day_of_month integer not null, status text not null default 'active', last_handled_month text,
  created_at text not null, updated_at text not null, is_deleted integer not null default 0);
alter table recurring_bills enable row level security;
