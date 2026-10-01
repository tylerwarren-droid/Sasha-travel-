-- 018 · Sasha 89 · THE FORM RUNG, SUBMITTING: one row per venue booking form Sasha fills and sends (form_rung.py).
-- The guest approves a read-back that shows EVERY field and value she will send; the row keeps that read-back, its
-- hash, the approval, and the venue's answer page word for word. Nothing is sent without a yes, and never past a
-- CAPTCHA or a consent box (formfill.py stops first).
-- Verified live on sasha-prod (yjafyzywzbmhlilxhzuz), 1 Oct 2026: trip_items(id uuid), booking_attempts.method allows
-- 'web_form', trip_items.status allows 'requested'/'confirmed'/'proposed'/'declined'. No booking_forms table exists.
-- ⛔ Applied by chat via MCP after review (Sasha 83 route), never by the Sasha tab.

-- PREVIEW (read-only): must be 0
select count(*) as booking_forms_tables from information_schema.tables where table_schema = 'public' and table_name = 'booking_forms';

begin;
create table public.booking_forms (
  form_id          uuid        primary key,
  account_id       uuid        not null,
  trip_item_id     uuid        null references public.trip_items (id) on delete cascade,
  read_id          uuid        null,
  host             text        not null,
  page_url         text        not null,                 -- the page the form is on (their own website)
  action_url       text        not null,                 -- where it is sent
  fields           jsonb       not null,                 -- [{name, label, role, value}] — exactly what the guest approved
  hidden_names     jsonb       not null default '[]',    -- the page's own hidden fields, sent with the page's values
  read_back_lines  jsonb       not null,
  read_back_sha256 text        not null check (read_back_sha256 ~ '^[0-9a-f]{64}$'),
  status           text        not null default 'awaiting_approval'
                   check (status in ('awaiting_approval', 'sending', 'sent', 'not_sent', 'failed')),
  approval         jsonb       null,
  approved_at      timestamptz null,
  sent_at          timestamptz null,
  http_status      integer     null,
  final_url        text        null,
  response_text    text        null,                     -- their answer page's visible text, verbatim (capped)
  response_sha256  text        null,
  reading          jsonb       null,                     -- how their answer was read: confirmed / proposed / none, and why
  not_sent_why     text        null,
  request_sha256   text        null,
  created_at       timestamptz not null
);
create index booking_forms_account on public.booking_forms (account_id, created_at desc);
create index booking_forms_item on public.booking_forms (trip_item_id);
alter table public.booking_forms enable row level security;   -- the backend only, like every booking table
commit;

-- VERIFY (read-only): expect true, 0
select relrowsecurity, (select count(*) from pg_policies where tablename = 'booking_forms') as policies
from pg_class where relname = 'booking_forms';
