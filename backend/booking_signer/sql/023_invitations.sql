-- 023 · S-80 · "book dinner with Jon this week": one invitation per such request — the inviter's first name, the
-- slots (no calendar data), the invitee's choice and his per-invitation consent. The booking stays the INVITER's.
-- Verified against the live schema (sasha-prod) on 2 Oct 2026: no booking_invitations table; trip_items.id and
-- auth.users.id are uuid. Depends on 020 (applied).
-- One addition to S-80 §3's draft: invitee_number_e164, set ONLY when Jon opts in by sending "INVITE {code}" — a later
-- WhatsApp (booked / cancelled) can't be sent to a hash. Never logged; erased with the invitation.
-- ⛔ NOT APPLIED by any session: the founder approves, then it is applied by chat (preview, transaction, verify).

-- PREVIEW (read-only): must be NULL
select to_regclass('public.booking_invitations');

begin;
create table booking_invitations (
  id                          uuid        primary key default gen_random_uuid(),
  code                        text        not null unique check (code ~ '^[A-Z0-9]{8}$'),
  inviter_account             uuid        not null references auth.users (id) on delete cascade,
  inviter_first_name          text        not null check (char_length(btrim(inviter_first_name)) between 1 and 40),
  invitee_first_name          text,
  invitee_account             uuid        references auth.users (id) on delete set null,     -- path L only
  invitee_wa_sha256           text,                                                           -- only if Jon opted in (or path L)
  invitee_number_e164         text        check (invitee_number_e164 is null or invitee_number_e164 ~ '^\+[1-9][0-9]{7,14}$'),
  activity                    text        not null,
  area                        text,                                                           -- as the inviter said it, if they did
  party_size                  int         not null check (party_size between 2 and 12),
  slots                       jsonb       not null,                                           -- [{start, end, tz}], 2–3; NO calendar data
  unseen                      boolean     not null default true,                              -- no calendar was read: said so
  chosen_slot                 int,
  chosen_at                   timestamptz,
  invitee_consent_at          timestamptz,
  invitee_consent_text_sha256 text,
  trip_item_id                uuid        references trip_items (id) on delete set null,
  told_status                 text,                                                           -- the last status Jon was told
  status                      text        not null default 'open'
                                          check (status in ('open', 'chosen', 'booked', 'declined', 'expired', 'cancelled')),
  expires_at                  timestamptz not null,                                           -- the window's end, max 7 days (A-3)
  created_at                  timestamptz not null default now()
);
create index booking_invitations_inviter on booking_invitations (inviter_account, created_at desc);
alter table booking_invitations enable row level security;
commit;

-- VERIFY (read-only): rls true, 0 policies
select relrowsecurity, (select count(*) from pg_policies where tablename = 'booking_invitations') as policies
from pg_class where relname = 'booking_invitations';
