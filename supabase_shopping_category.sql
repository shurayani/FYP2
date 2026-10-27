-- Patch #21: 8th system category. IPECS adds it automatically at the next sync; this file is a backup.
insert into categories (id, category_name, is_system, user_id, updated_at, is_deleted) values
  ('a0edc229-7b46-5163-a862-82f681375435','Shopping',1,null,now()::text,0)
on conflict (id) do nothing;
