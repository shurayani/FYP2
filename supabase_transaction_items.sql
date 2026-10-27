-- Run ONCE in the Supabase SQL editor (after the main schema).
create table if not exists transaction_items (
  id text primary key, user_id text not null references users(id),
  transaction_id text not null references transactions(id), receipt_id text references receipts(id),
  item_name text not null, amount double precision not null, category_id text not null references categories(id),
  created_at text not null, updated_at text not null, is_deleted integer not null default 0);
alter table transaction_items enable row level security;
create policy "ipecs_all_transaction_items" on transaction_items for all to anon, authenticated using (true) with check (true);
