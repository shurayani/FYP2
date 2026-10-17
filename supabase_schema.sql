-- IPECS remote sync database (Supabase / PostgreSQL). Mirrors the local SQLite schema (Chapter 4).
-- Run once in: Supabase dashboard > SQL Editor. SYNC_LOG stays local only (it is per-device state).
create table if not exists users (
  id text primary key, username text not null unique, email text not null unique, password text not null,
  role text not null default 'user', is_active integer not null default 1, created_at text not null, updated_at text not null);
create table if not exists categories (
  id text primary key, category_name text not null, is_system integer not null default 0,
  user_id text references users(id), updated_at text not null, is_deleted integer not null default 0);
create table if not exists receipts (
  id text primary key, user_id text not null references users(id), file_path text not null, original_filename text,
  upload_date text not null, ocr_raw_text text, ocr_engine text, created_at text not null, updated_at text not null,
  is_deleted integer not null default 0);
create table if not exists transactions (
  id text primary key, user_id text not null references users(id), receipt_id text references receipts(id),
  merchant text not null, date text not null, amount double precision not null,
  category_id text not null references categories(id), is_manual integer not null default 1,
  z_score double precision, is_anomaly integer not null default 0, created_at text not null, updated_at text not null,
  is_deleted integer not null default 0);
create table if not exists budgets (
  id text primary key, user_id text not null references users(id), category_id text not null references categories(id),
  budget_month text not null, budget_amount double precision not null, created_at text not null, updated_at text not null,
  is_deleted integer not null default 0);
create table if not exists reports (
  id text primary key, user_id text not null references users(id), report_month text not null, report_data text not null,
  generated_at text not null, updated_at text not null, is_deleted integer not null default 0);
create table if not exists anomaly_alerts (
  id text primary key, user_id text not null references users(id), transaction_id text not null references transactions(id),
  z_score double precision not null, status text not null default 'active', created_at text not null, resolved_at text,
  updated_at text not null, is_deleted integer not null default 0);
create table if not exists forecasts (
  id text primary key, user_id text not null references users(id), category_id text not null references categories(id),
  forecast_month text not null, forecast_amount double precision not null, confidence_lower double precision,
  confidence_upper double precision, generated_at text not null, updated_at text not null,
  is_deleted integer not null default 0);

-- The seven fixed system categories (same IDs on every device) must exist remotely for foreign keys.
insert into categories (id, category_name, is_system, user_id, updated_at, is_deleted) values
  ('fa6a54e9-541b-5b9b-82d5-664439b88b66','Food and Beverage',1,null,now()::text,0),
  ('a00655d4-a6c6-5fa2-a7f9-2bd4a9adbb73','Groceries',1,null,now()::text,0),
  ('d5510ff6-b230-5363-9980-bb92c22be164','Transport',1,null,now()::text,0),
  ('830eb2a5-4fd7-5283-80e5-421694ce008f','Utilities',1,null,now()::text,0),
  ('31b63273-ef56-5b37-86a7-160570541802','Education',1,null,now()::text,0),
  ('58898cf2-d6e9-51b3-b855-2e0ac8bb1dc3','Health',1,null,now()::text,0),
  ('32e478a8-7c5d-545a-b4cc-a5e05aff12a0','Entertainment',1,null,now()::text,0)
on conflict (id) do nothing;

-- Row Level Security: enable it so the public anon key cannot read anything.
-- IPECS (app level) filters every query by user_id and uses the key from your local .env.
alter table users enable row level security;       alter table categories enable row level security;
alter table receipts enable row level security;    alter table transactions enable row level security;
alter table budgets enable row level security;     alter table reports enable row level security;
alter table anomaly_alerts enable row level security; alter table forecasts enable row level security;
-- With the service_role key (kept ONLY in your private .env) RLS is bypassed, which is what the sync client uses.
