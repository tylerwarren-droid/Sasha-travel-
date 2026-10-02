# S-80 · "Book dinner with Jon this week": two guests, one booking, consent on both sides

> ✅ **Founder defaults (EU 120):** A-1 to A-3 as recommended (dinner 20:30–22:30, lunch 13:30–15:30; Jon tells Ana and Ana decides; the invitation expires at the window's end, max 7 days). **020 is applied** (chat, EU 120). 022 and 023 are still drafts.

*EU session, 2 Oct 2026 (EU 119), spec ahead of the Sasha tab. Code at **`22ccc0e`**. It builds on S-75 (guest
WhatsApp, built in the sandbox), S-78 (vault, built) and S-79 (calendar, specced).*

## 0. The rules that shape it (not optional)

1. **Sasha never writes first to someone who hasn't opted in to Kanoe.**
   - Meta's opt-in rule (read at source for S-75): *"Businesses must clearly state that a person is opting in to
     receive communication from the business… [and] the business's name."*
   - S-75 §8: *"No first contact to a guest who hasn't linked."*
   - **So if Jon isn't a linked Sasha guest, Sasha doesn't message Jon.** The **inviting guest** sends Jon an
     invitation **from their own WhatsApp** (Mode A, the same pattern as S-48's venue Mode A). Jon opts in by opening it.
2. **Jon's consent is his own and per invitation.** Agreeing to a slot isn't consent for anything else. No standing
   link between two guests is created without both saying so.
3. **Data minimisation between the two:**
   - each side sees **only**: the other's first name (as the inviter typed it, or as Jon gives it), the venue, the
     proposed slots, and the outcome;
   - **never** the other's calendar, events, phone number, email, other bookings, or chat;
   - free/busy is combined **server-side** into candidate slots, and **only the slots** are shown.
4. **The booking is the inviter's.** It's made under the inviter's name with **the inviter's yes** (the existing hash-bound
   read-back). Jon's choice picks the slot; it doesn't approve a booking in his name.

---

## 1. Facts from the code

- **No relation between guests exists** in SQL; only Pydantic `TravellerRelation` (`app/models/user.py:7`).
- **Guest WhatsApp (S-75) is built for the sandbox:**
  - `booking_signer/guest_whatsapp.py`: `dispatch` `:432`, `turn` `:494`, `deliver(ch, frm, out, last_inbound_at)`
    `:343` (respects opt-out and the 24 h window), `Sender.send` `:289`, `Sender.quick_reply` `:267`;
  - `guest_channels` (`sql/020_guest_channels.sql`) holds `number_e164` and `wa_id_sha256` per linked account. **020 is
    not applied** (its header).
- **Identity:** `account_for` (`account.py:16`); the email via `ladder_store.account_email` (`:424`).
- **The booking flow** is unchanged: `booking_handoff` (`handoff.py:206`) → `booking_turn` → prepare → a yes bound to
  `read_back_sha256` (`call_routes.py:497–503`) → status writes → receipts (`guest_receipt.py:110 / :188`).
- **Calendar free/busy:** S-79 §5.4 `calendar_sync.busy(...)` (specced, not built).

---

## 2. The flow

```
Ana (a linked guest): "book dinner with Jon this week"
  1. Sasha parses: activity=dinner, invitee="Jon", window=this week (Mon–Sun, Ana's local tz), party=2.
  2. Sasha: "What's Jon's mobile, or do you want me to give you a link to send him?"
        - Ana gives a number  → lookup guest_channels by sha256(number):
             a) Jon IS a linked guest  → path L (in-Sasha)
             b) he isn't                → path I (invitation via Ana's WhatsApp)
        - Ana asks for a link  → path I
  3. Candidate slots: Ana's free/busy (S-79, if connected) ∩ Jon's (path L, if connected, and only if Jon allows it for this invitation)
     ∩ venue-agnostic dinner hours (20:30–22:30 local, configurable) → pick 2–3 slots across different days.
     No calendar connected → Sasha proposes 3 sensible slots and says so ("I can't see your calendar").
  4. Path L: Sasha messages Jon (he is linked, so in-window or a utility template, S-75 §6):
        "Ana would like to have dinner with you this week, booked by Sasha. Which suits you?"  [quick-reply: slot1 | slot2 | slot3 | None of these]
     Path I: Sasha gives Ana a wa.me share link with a prefilled message:
        "Ana invited you to dinner — pick a time (booked by Sasha by Kanoe, an AI assistant): {invite_url}"
        Ana sends it herself, from her own WhatsApp. Jon opens invite_url (a web page; no account needed):
        shows Ana's first name, "dinner", the 2–3 slots, and the consent line; Jon taps a slot.
        Optional on that page: "Let Sasha message me about this dinner on WhatsApp" → wa.me/447915914215?text=INVITE%20{code}
        (Jon writes first → his 24 h window opens → he is opted in for THIS invitation's messages only).
  5. Jon's choice → Ana is told: "Jon picked Thursday 21:00." → normal venue discovery (cards) for Thursday 21:00 →
     Ana picks → read-back → ANA's yes → booking (existing flow, party 2, under Ana's name).
  6. Receipts: Ana gets the normal receipt (guest_receipt.py). Jon gets: path L → a WhatsApp message (in-window/template);
     path I → the invite page now shows "Booked: {venue}, Thursday 21:00" + an .ics download; WhatsApp only if he opted in (step 4).
     Both calendars: S-79 writes Ana's; Jon's only if Jon is linked AND connected (path L).
  7. Cancellation by Ana → Jon is told through the same channel he used. Jon can't cancel Ana's booking; he can say
     "I can't make it", which tells Ana, and Ana decides.
```

---

## 3. Data (migration `023_invitations.sql`, DRAFT, not applied; it depends on 020 and 022)

```sql
-- Preview: expect NULL
select to_regclass('public.booking_invitations');
create table public.booking_invitations (
  id uuid primary key default gen_random_uuid(),
  code text not null unique check (code ~ '^[A-Z0-9]{8}$'),     -- in the invite URL and the WhatsApp INVITE text
  inviter_account uuid not null references auth.users(id) on delete cascade,
  inviter_first_name text not null,                               -- what Jon sees; nothing else about Ana
  invitee_first_name text,                                        -- as Ana typed it, then as Jon confirms it
  invitee_account uuid references auth.users(id) on delete set null,   -- path L only
  invitee_wa_sha256 text,                                         -- set only if Jon opted in (path I step 4) or is linked (L)
  activity text not null, party_size int not null check (party_size between 2 and 12),
  slots jsonb not null,                                           -- [{start, end, tz}], 2–3 items; NO calendar data
  chosen_slot int, chosen_at timestamptz,
  invitee_consent_at timestamptz, invitee_consent_text_sha256 text,
  trip_item_id uuid references public.trip_items(id) on delete set null,
  status text not null default 'open' check (status in ('open','chosen','booked','declined','expired','cancelled')),
  expires_at timestamptz not null,                                -- end of the window, max 7 days
  created_at timestamptz not null default now()
);
create index booking_invitations_inviter on public.booking_invitations (inviter_account, created_at desc);
alter table public.booking_invitations enable row level security;   -- backend only, no policies
```

- **Never stored:** Jon's phone number in clear (path I keeps only the hash, and only if he opts in); his calendar; any
  of Ana's details beyond her first name.
- Retention: the S-53 job deletes invitations 30 days after `expires_at`.

---

## 4. Code (new module `backend/booking_signer/invitations.py` + routes)

1. **Intent** in `handoff.py` (`booking_handoff`, `:206`): recognise *"with {Name}"*, *"invite {Name}"*, *"for me and
   {Name}"* + a window → `booking_invite` (a sibling of `booking_find` / `booking_cancel`). Without a window: ask once.
2. **Slots:** pure `invitations.slots(window, busy_a, busy_b, hours, n=3) -> [slot]`, with candidates on different days
   first. `busy_*` come from S-79 `calendar_sync.busy`, or `[]` with an `unseen` flag that makes the message say so.
3. **Path L** (Jon linked): `guest_whatsapp.deliver` (`:343`) with `Out.ask` + quick-reply (`Sender.quick_reply`,
   `:267`), payload `inv:{code}:{i}`. Using Jon's free/busy needs **Jon's per-invitation yes first**: *"Ana wants to find
   a dinner time with you. Can Sasha check when you're free this week? She'll only use it to suggest times."*
   [Yes | No]. With no, the slots use Ana's calendar only.
4. **Path I:**
   - `GET /api/booking/invite/{code}`: a public JSON payload (inviter first name, activity, slots, status), rate-limited
     per IP.
   - The frontend page `frontend/app/invite/[code]/page.tsx` shows the consent text: *"Sasha by Kanoe (an AI
     assistant) is booking a dinner for Ana and you. Picking a time shares only your choice with Ana. Nothing else about
     you is stored unless you ask Sasha to message you."*
   - `POST /api/booking/invite/{code}/choose {slot, first_name?}` → sets `chosen_slot`, `invitee_consent_*`.
   - The share link for Ana: `https://wa.me/?text=` + the prefilled invite text (**Ana's own WhatsApp; no number needed,
     she picks Jon in her contacts**).
5. **Inbound `INVITE {code}`** in `guest_whatsapp.dispatch` (`:432`): after the LINK check and before venue matching,
   an unlinked sender whose body matches `^\s*invite\s+([A-Z0-9]{8})\s*$` → store `invitee_wa_sha256`, reply *"You'll
   hear from Sasha about this dinner only. Reply STOP to stop."* That's per-invitation scope: **no** general chat is
   opened for Jon (he isn't a linked guest; S-75's scope gate applies).
6. **On choose →** notify Ana (her channel) → run the normal discovery turn at the chosen slot (`conduct()` →
   `booking_handoff`, with the slot pre-filled) → Ana's yes → booking. Set `trip_item_id` and `status='booked'` when
   the trip item is `confirmed` (read via S-79's outbox, or a status check in `invitations.watch`).
7. **Receipts:** `guest_receipt.send_for_route` (`:188`) for Ana, unchanged. For Jon, `invitations.notify_invitee(inv,
   kind)` uses path L WhatsApp, or the path I page (+ WhatsApp only if `invitee_wa_sha256`). Jon's message carries
   only: the venue, date, time, the address and "booked under Ana's name". **No reference number** (that's Ana's
   booking), no Ana phone or email.

---

## 5. Tests

1. `test_invite_intent`: "book dinner with Jon this week" → `booking_invite(invitee='Jon', window=…)`;
   "dinner for two" → not an invite.
2. `test_slots`: busy intersections; no free slot → message *"I couldn't find a time you're both free this week"*;
   unseen calendars → the `unseen` flag is set.
3. `test_minimisation`: the invite payload and every Jon-facing message contain no Ana phone, email, other bookings or
   calendar titles. Ana-facing text contains no Jon phone. (Snapshot the dicts; assert key sets.)
4. `test_no_first_contact`: path I never calls `Sender.send` to a number that isn't in `guest_channels` and hasn't sent
   `INVITE`; an `INVITE` with a wrong or expired code → the fixed refusal.
5. `test_jon_scope`: after `INVITE`, Jon's "write me a poem" → the S-75 out-of-scope sentence, and the model isn't
   called. Jon's "STOP" → no further messages for this invitation.
6. `test_booking_is_inviters`: the read-back is Ana's, the yes is Ana's, `trip_items` is under Ana's trip; Jon's choice
   alone never places a call.
7. **Live (sandbox):** the founder (Ana) and a second test phone (Jon, path I then path L) → book a real form-rung venue
   → both get their messages → cancel → both told.

## 6. Build order

020 + 022 applied → §4.1–4.2 (tests 1–2) → path I (§4.4–4.5, tests 3–5) → path L (§4.3) → §4.6–4.7 (test 6) → live
(test 7). **Path I first:** it works for any friend, and needs no second linked account.

## Founder decisions

- **A-1:** dinner-hour defaults per activity (dinner 20:30–22:30; lunch 13:30–15:30 in Spain).
- **A-2:** whether Jon may cancel his own attendance with a reduced party size (default: he tells Ana, and Ana decides).
- **A-3:** the invitation expiry (default: the end of the window, max 7 days).
