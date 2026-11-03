-- Sasha 333 · THE TRAVELLER VAULT. ADDITIVE: two optional columns on group_members — where a member's vault invite goes (their email)
-- and the WhatsApp number their "delete my passport" may come from. Their numbers themselves are NOT here: they live only in the Keep
-- (keep_keys / keep_items, 037), under the member's id, encrypted. Needs 048 first.
-- preview (read-only)
select column_name from information_schema.columns where table_name = 'group_members' and column_name in ('email', 'phone');

begin;
alter table public.group_members add column if not exists email text check (email is null or (char_length(email) <= 254 and email ~ '^[^@\s]+@[^@\s]+\.[a-z]{2,}$'));
alter table public.group_members add column if not exists phone text check (phone is null or phone ~ '^\+[0-9]{8,15}$');
create index if not exists group_members_phone on public.group_members (phone) where phone is not null;
commit;

-- verify
select column_name from information_schema.columns where table_name = 'group_members' and column_name in ('email', 'phone');
