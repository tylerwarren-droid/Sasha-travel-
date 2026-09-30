-- ── S-54 · VENUE OPT-INS — ONE BLOCK, FOR SASHA'S SUPABASE (xlqtveusyfpffaejegiq) ─────────────────────────────
--
-- S-49 §1: one row per venue, per channel, per scope, APPEND-ONLY. An opt-in is a row; a withdrawal is a NEW row
-- (status 'withdrawn'), never an edit. The latest row for (venue_id, channel, scope) is the state.
--
-- ⛔ Enforced here, not by convention: a trigger refuses every UPDATE, and every DELETE unless the session has set
-- `booking.retention = 'on'` — which only the retention job does, and only for a chain whose latest row is a withdrawal
-- older than RETENTION_CONSENT_YEARS_AFTER_WITHDRAWAL (retention.py).
--
-- Run ONCE, whole, AFTER 007. It refuses if already applied.

do $$
begin
  if to_regclass('public.venue_optins') is not null then
    raise exception 'STOP: venue_optins already exists — nothing was changed.';
  end if;
  if to_regclass('public.retention_log') is null then
    raise exception 'STOP: 007_retention_log.sql has not been applied — nothing was changed.';
  end if;
end $$;

create table public.venue_optins (
  id                  bigint      generated always as identity primary key,
  venue_id            text        not null,
  channel             text        not null check (channel in ('whatsapp','web_submit','email_confirm')),
  scope               text        not null,
  status              text        not null check (status in ('active','withdrawn')),
  recorded_at         timestamptz not null default now(),
  agreed_by_name      text        null,
  agreed_by_role      text        null,
  agreed_at           timestamptz null,
  method              text        null check (method in ('whatsapp_inbound','form','email_reply','qr')),
  wording_version     text        null,
  wording_sha256      text        null check (wording_sha256 is null or wording_sha256 ~ '^[0-9a-f]{64}$'),
  wording_text        text        null,
  evidence            jsonb       null,
  withdrawn_at        timestamptz null,
  withdrawn_how       text        null,
  withdrawn_evidence  jsonb       null,
  check (status <> 'active' or (agreed_at is not null and method is not null and wording_version is not null
                                and wording_sha256 is not null and wording_text is not null and evidence is not null)),
  check (status <> 'withdrawn' or (withdrawn_at is not null and withdrawn_how is not null))
);
create index venue_optins_latest on public.venue_optins (venue_id, channel, scope, recorded_at desc, id desc);
alter table public.venue_optins enable row level security;

create function public.venue_optins_append_only() returns trigger language plpgsql as $f$
begin
  if tg_op = 'UPDATE' then
    raise exception 'venue_optins is append-only: a change is a new row, never an edit';
  end if;
  if coalesce(current_setting('booking.retention', true), '') <> 'on' then
    raise exception 'venue_optins is append-only: only the retention job may delete, and only withdrawn chains past their period';
  end if;
  return old;
end $f$;
create trigger venue_optins_append_only before update or delete on public.venue_optins
  for each row execute function public.venue_optins_append_only();

select 'venue_optins exists, append-only, with row level security on' as check,
       (select relrowsecurity from pg_class where oid = 'public.venue_optins'::regclass)
       and exists (select 1 from pg_trigger where tgname = 'venue_optins_append_only') as ok;
