# S-83 · Proactive Sasha: the day before, the time to leave, "confirmed in writing", and the morning brief

*EU session, 2 Oct 2026 (EU 121), spec ahead of the Sasha tab. Code at **`a8f9b50`**. Nothing built.*

> ✅ **Founder decisions (EU 122):**
> - **Consent v3.** Reminders get their own line in the WhatsApp consent text; they don't rely on v2 (see §3a).
> - **Key.** The Routes API is enabled on the existing "Sasha Places" key, so the code reads `GOOGLE_PLACES_API_KEY`.
>   No new env var.

## 0. What exists (so nothing is duplicated)

- **WhatsApp delivery (S-75, built, sandbox):** `guest_whatsapp.deliver(ch, frm, out, last_inbound_at)`
  (`booking_signer/guest_whatsapp.py:343–364`):
  - it refuses when `opted_out_at` is set (`:346–348`);
  - it refuses outside the 24 h window, *"no template is approved (sandbox)"* (`:349–351`);
  - `Sender.send(frm, to, *, body, media, content_sid)` (`:287–293`) already supports `ContentSid`, so **a template is a
    `content_sid` plus variables**;
  - `guest_wa_state.last_inbound_at` is in `sql/020_guest_channels.sql:42` (**applied**, EU 120).
- **The guest's coming bookings:** `_upcoming(account)` (`guest_whatsapp.py:984–996`) reads `GET
  /api/booking/reservations` (`routes.py:484`), excludes cancelled, declined and failed, and resolves the venue name from
  the receipt. **Reused as is.**
- **Background loops** follow one pattern:
  - `retention.start()` is called from `routes.py:532–534` (`@router.on_event("startup")`), gated by
    `SASHA_RETENTION_LOOP`;
  - `_forever` sleeps, runs, and catches and logs errors (`retention.py:173–199`);
  - `call_routes._sweep_forever` (`:192–206`) is the same.
  - **S-83 adds one more loop in exactly this shape.** (S-79's calendar drainer is specced, not built, and is separate.)
- **Written confirmations land in `booking_inbound`:**
  - `channel` is `sms`, `voicemail`, `whatsapp` or `email` (016 + 017 + 019);
  - `trip_item_id`, and `reading jsonb` (*"confirmed / proposed / none, and why"*, `016:21`);
  - email arrives through `inbound_phone.on_written_email` (`:331–343`) → `_read_sms`.
  - **"Confirmed in writing" = a `booking_inbound` row with `reading->>'result' = 'confirmed'`, a `trip_item_id`, and
    `channel in ('email','sms','whatsapp')`.**
- **Distance today is straight-line only:** `venue_read.haversine_m` (`:533`), with words from `distance_words`
  (`:541`, *"never 'nearby'"*). There's **no route or travel-time code** and **no saved starting point** for a guest.
- **Booking fields:**
  - `trip_items.date_time`, `local_timezone`, `party_size`, `provider_name` (or the receipt's venue name),
    `booking_reference`, `status`;
  - the status vocabulary is in 011's header.

---

## 1. The four messages, and the honest status rule

| Kind | When (venue's local time, `trip_items.local_timezone`) | For which bookings | Text, in session (≤24 h) |
|---|---|---|---|
| **day_before** | 18:00 the day before | `confirmed`, `guest_booked` | *"Tomorrow: {venue}, {HH:MM}, table for {party}, ref {ref}. Reply CANCEL {short} to cancel."* (the `ref` is the venue's reference if any, else Sasha's K-reference) |
| **honest status** (instead of day_before) | 18:00 the day before | `requested`, `attempting`, `unclear`, `proposed`, `quoted`, `waitlisted`, `link_sent` | *"Tomorrow, {HH:MM} at {venue}: **not confirmed yet**. {state words}. I'll tell you as soon as they answer."* `{state words}` come from `routes.py` `STATUS_WORDS` (`:450`) (one owner), e.g. proposed → *"They offered {time}; it's not booked until you say yes."* **Never phrased as a booking** |
| **leave_now** | `date_time − travel − 10 min`, if the guest has a starting point **and** a route was computed | `confirmed`, `guest_booked` only | *"Time to leave for {venue}: {N} min by {mode} from {place label}, for {HH:MM}."* |
| **written_confirmation** | on arrival (deferred if in quiet hours) | any booking that gets one | *"{venue} confirmed in writing ✅: {HH:MM} {day}, {party} people{, ref X}."* The ✅ only when `reading.result == 'confirmed'`. A `proposed` written reply sends *"{venue} replied in writing: they offer {time}. Not booked until you say yes."* |
| **morning_brief** | 09:00 on a day with ≥1 booking | that day's bookings | *"Today: 13:30 Zalacaín (confirmed) · 21:00 Calma (not confirmed yet)."* One line per booking, each with its honest state |

**The rules, enforced in code:**
1. **Nothing for a booking that isn't confirmed except an honest status.** Never a "see you tomorrow" for `unclear`,
   `proposed` or `requested`.
2. **Quiet hours: 22:00–08:00 in the booking's local time zone.** A message due inside them waits until 08:00 (or is
   dropped if it's no longer useful: a `leave_now` is never deferred, only skipped).
3. **A daily cap per guest, N = 4** (`SASHA_PROACTIVE_DAILY_MAX`).
   - Priority when over the cap: `written_confirmation` > `leave_now` > `day_before` / honest status >
     `morning_brief`.
   - The brief is the first dropped, and it merges a day's items rather than adding.
4. **One of each kind per booking, ever** (a unique ledger row; §3).
5. **Opt-out per guest, per kind.**
   - "STOP REMINDERS" or the settings page turns proactive messages off. STOP (S-75 §7) turns **all** WhatsApp off.
   - The `deliver` check at `:346` already covers full opt-out; per-kind is §3's `proactive_prefs`.
6. **No proactive message reveals anything not already in the guest's own booking.** No other guests, no chat content.

---

## 2. Outside the 24-hour window: utility templates (exact wording for Meta approval)

- These are submitted through Twilio's Content Template Builder, category **Utility** (transactional, about a booking
  the guest made; **no promotional content**, or Meta reclassifies it as Marketing).
- Variables are numbered; each template has **no** links or offers.
- Spanish versions are submitted alongside (language `es`).

| Name | Language | Body (variables numbered) |
|---|---|---|
| `sasha_day_before` | en | `Sasha by Kanoe: tomorrow you have {{1}} at {{2}}, for {{3}}. Reference {{4}}. Reply CANCEL to cancel, or STOP to stop messages.` |
| `sasha_day_before` | es | `Sasha by Kanoe: mañana tienes {{1}} a las {{2}}, para {{3}}. Referencia {{4}}. Responde CANCELAR para cancelar, o STOP para no recibir más mensajes.` |
| `sasha_not_confirmed` | en | `Sasha by Kanoe: your booking request at {{1}} for {{2}} is not confirmed yet. Current status: {{3}}. We'll message you when the venue answers.` |
| `sasha_not_confirmed` | es | `Sasha by Kanoe: tu solicitud en {{1}} para {{2}} aún no está confirmada. Estado: {{3}}. Te avisaremos cuando responda el establecimiento.` |
| `sasha_leave_now` | en | `Sasha by Kanoe: to reach {{1}} for {{2}}, leave now. About {{3}} minutes by {{4}} from {{5}}.` |
| `sasha_leave_now` | es | `Sasha by Kanoe: para llegar a {{1}} a las {{2}}, sal ahora. Unos {{3}} minutos {{4}} desde {{5}}.` |
| `sasha_written_confirmation` | en | `Sasha by Kanoe: {{1}} confirmed your booking in writing: {{2}}, {{3}} people. Reference {{4}}.` |
| `sasha_written_confirmation` | es | `Sasha by Kanoe: {{1}} ha confirmado tu reserva por escrito: {{2}}, {{3}} personas. Referencia {{4}}.` |
| `sasha_morning_brief` | en | `Sasha by Kanoe: your bookings today: {{1}}` |
| `sasha_morning_brief` | es | `Sasha by Kanoe: tus reservas de hoy: {{1}}` |

**Notes:**
- `{{4}}` for a missing reference is `"none given"` / `"sin referencia"`, never empty.
- WhatsApp templates don't allow emoji-only meaning. The ✅ is used **only** in-session (§1); the template says
  "confirmed … in writing".
- **Production only** (S-75 steps 11–12, behind F-1 counsel). The sandbox has no custom templates, so in the sandbox
  an out-of-window message is **not sent** and logged, exactly as `deliver` does today.
- **Cost:** a utility template outside the window is **€0.0166 (ES) / €0.0182 (UK) + $0.005** (S-71, read at source).
  In-window it's free + $0.005. The daily cap bounds the spend.

---

## 3. Data (migration `026_proactive.sql`, DRAFT, not applied; 020 is applied, 024 and 025 are drafts)

```sql
-- Preview: expect NULL three times
select to_regclass('public.proactive_sent'), to_regclass('public.proactive_prefs'), to_regclass('public.guest_places');

-- The ledger: one of each kind per booking, ever. Also the daily-cap counter.
create table public.proactive_sent (
  id bigserial primary key,
  account_id uuid not null references auth.users(id) on delete cascade,
  trip_item_id uuid references public.trip_items(id) on delete cascade,      -- null for the morning brief
  kind text not null check (kind in ('day_before','not_confirmed','leave_now','written_confirmation','morning_brief')),
  local_day date not null,                                                   -- the booking's local date (cap and dedupe)
  status_at_send text,                                                       -- trip_items.status when sent — the honesty audit
  channel text not null check (channel in ('whatsapp_session','whatsapp_template','skipped')),
  outcome text not null,                                                     -- "sent" | "not sent: <reason>"
  sent_at timestamptz not null default now()
);
create unique index proactive_once on public.proactive_sent (trip_item_id, kind) where trip_item_id is not null;
create unique index proactive_brief_once on public.proactive_sent (account_id, local_day) where kind = 'morning_brief';
create index proactive_day on public.proactive_sent (account_id, local_day);

-- Per-guest, per-kind opt-out (absence = on, ONLY for a guest whose guest_channels.consent_wording_version is 'v3' or later — §3a).
create table public.proactive_prefs (
  account_id uuid primary key references auth.users(id) on delete cascade,
  off_kinds text[] not null default '{}', all_off boolean not null default false, updated_at timestamptz not null default now()
);

-- A saved starting point ("my hotel", "home"), for leave_now. Never inferred, only what the guest saves.
create table public.guest_places (
  id uuid primary key default gen_random_uuid(),
  account_id uuid not null references auth.users(id) on delete cascade,
  label text not null, address text not null, lat double precision not null, lng double precision not null,
  is_default boolean not null default false, created_at timestamptz not null default now()
);
create unique index guest_places_one_default on public.guest_places (account_id) where is_default;
alter table public.proactive_sent enable row level security;
alter table public.proactive_prefs enable row level security;
alter table public.guest_places enable row level security;
```

- `guest_places` stores coordinates from the guest's own address. That's personal data.
  - **Erasure:** `vault/gdpr.py:72` `delete_everything` erases **per store** (`crypto.STORE`, `GW.STORE`,
    `contacts.STORE`, `:87–90`), not by `auth.users` cascade. So `proactive.STORE.delete_account(account)` must be
    added there, deleting all three tables' rows and returning counts. **Test 11:** after `DELETE /data`, all three
    tables are empty for the account.

---

## 3a. Consent v3 (EU 122): reminders get their own line

- **Today:** `guest_whatsapp.py:45–47`, `CONSENT = {"v2": …}` and `CURRENT = "v2"`. The text is recorded per link as
  `consent_wording_version` and `consent_text_sha256` (`:190–211`). **Add v3; keep v2** (the existing links cite it):

```python
CONSENT = {"v2": (...unchanged...),
           "v3": ("Sasha by Kanoe will message you on WhatsApp about the bookings you ask for: confirmations, progress "
                  "and receipts. Reply STOP at any time to stop.\n"
                  "She will also send you reminders about those bookings: the day before, when it's time to leave, and a "
                  "morning summary — never between 22:00 and 08:00, at most 4 a day. Reply STOP REMINDERS to stop just these.")}
CURRENT = "v3"
```

- **Spanish (shown to `es` guests, recorded under the same version):** *"…También te enviará recordatorios de esas
  reservas: el día anterior, cuando sea hora de salir y un resumen por la mañana — nunca entre las 22:00 y las 08:00,
  como máximo 4 al día. Responde STOP RECORDATORIOS para dejar solo estos."*
- **Gate:** `proactive.tick` sends **only** to guests whose `guest_channels.consent_wording_version` is v3 or later (compare `int(v[1:])`, never as strings: 'v10' < 'v3'). **A v2
  guest gets nothing proactive.** The one exception is `written_confirmation`, which is a confirmation about a booking
  they asked for, covered by v2's "confirmations".
- **Upgrading a v2 guest:**
  - one in-window message, sent only in reply to their next inbound: *"Want reminders about your bookings (day before,
    time to leave, morning summary)? Reply YES REMINDERS."*;
  - YES → record v3 plus the sha256 on their `guest_channels` row;
  - never asked again if declined or ignored (a `proactive_prefs.all_off = true` row records the no).
- **The text matches the rules:** 22:00–08:00 and "at most 4" are §1.2–1.3. If the cap or the hours change, a new
  consent version follows (the sha256 makes the drift visible).
- **Test 12** (`test_consent_gate`):
  - a v2 guest gets no day_before, leave_now or brief, but does get written_confirmation;
  - after YES REMINDERS → v3 is recorded, and the next day_before is sent;
  - the v3 text's sha256 is stored, and the text contains "22:00" and "4" (matching `QUIET` and `DAILY_MAX`).

---

## 4. Travel time (leave_now)

- **Google Routes API, at source** (`developers.google.com/maps/documentation/routes/compute_route_directions`):
  - `POST https://routes.googleapis.com/directions/v2:computeRoutes`;
  - headers `X-Goog-Api-Key` and `X-Goog-FieldMask: routes.duration,routes.distanceMeters`;
  - `travelMode` is one of `DRIVE`, `WALK`, `TRANSIT`, `TWO_WHEELER`;
  - the response is `routes[0].duration` (e.g. `"165s"`).
  - ○ The departure-time field (`departureTime`, RFC 3339) and Routes API enablement are **to confirm** in the console
    (not shown in the page summary).
- **Mode:** `TRANSIT` in Madrid and Lisbon by default, `WALK` if under 1.5 km straight-line (`haversine_m`, `:533`), and
  the guest can change it in settings.
- **Key (EU 122):** the existing "Sasha Places" key, with the Routes API enabled on it. The code reads
  `GOOGLE_PLACES_API_KEY` (as `venue_read` does), with no new env var. If the key's API restrictions list doesn't include
  "Routes API", computeRoutes returns 403. That is logged, and no leave_now is sent (test 8).
- **Honesty:**
  - **No starting point, or no route computed → no leave_now.** The day_before still goes.
  - **Never a straight-line estimate presented as a travel time.** It's the rule-4 trap: haversine underestimates a city
    route.
- **Places terms:** a route **duration** is computed on the fly and not stored beyond the `proactive_sent` row's
  outcome. Store no route geometry (the S-64 / 013 lesson on storing Google content).

---

## 5. The scheduler (new `backend/booking_signer/proactive.py`, the retention pattern)

```python
TICK_S = 60
def start() -> None:   # called from routes.py's startup hook beside retention.start() (routes.py:532–534)
    if os.getenv("SASHA_PROACTIVE_LOOP", "1") == "1" and os.getenv("DATABASE_URL", "").strip(): asyncio.create_task(_forever())

async def _forever():
    while True:
        try: await tick(NOW())
        except Exception as e: log.error("[proactive] tick failed: %s: %s", type(e).__name__, e)   # rule: never silent
        await asyncio.sleep(TICK_S)

async def tick(now):
    # 1. written confirmations since the last tick: booking_inbound where reading->>'result' in ('confirmed','proposed')
    #    and trip_item_id is not null and channel in ('email','sms','whatsapp') and received_at > last_watermark
    # 2. for each linked guest (guest_channels, not opted out, proactive_prefs not all_off):
    #      rows = await _upcoming(account)          # guest_whatsapp.py:984 — the one owner of "coming bookings"
    #      for each due (kind, booking) per §1's clock, in the booking's local tz:
    #         if quiet_hours(now, tz) → defer (leave_now: skip)
    #         if over_cap(account, local_day) → drop by §1.3's priority
    #         msg = render(kind, booking)            # §1 text, honest-status branch by status
    #         out = deliver_or_template(ch, msg)     # in-window: deliver(); else the §2 template (production) or "not sent"
    #         insert proactive_sent(... status_at_send, channel, outcome)  — the unique index makes a re-run a no-op
```

- **Concurrency:** one backend instance today. If it scales out, each `insert … on conflict do nothing returning id`
  claims the send **before** delivering. A lost race means no send.
- **`deliver_or_template`:** a new function beside `deliver`, taking `(ch, kind, variables)`. In-window it sends the §1
  text; out-of-window it sends `content_sid = TEMPLATES[kind][lang]` with `ContentVariables`. With no SID configured
  (the sandbox), it returns `"not sent: outside the 24-hour window"`, the current behaviour.
- **Status re-read at send:** the booking's status is re-read in the same transaction as the ledger insert, so a
  booking cancelled at 17:59 never gets an 18:00 "tomorrow" message.

---

## 6. Tests (`backend/tests/test_proactive_s83.py`; a fake clock and fake delivery)

1. `test_honest_status`: for **every** status in 011's list, `render('day_before', b)` sends the confirmed text **only**
   for `confirmed` and `guest_booked`. `unclear`, `proposed` and `requested` get the not-confirmed text, which contains
   "not confirmed" (or "not booked until you say yes") and **never** "Tomorrow:" alone.
2. `test_quiet_hours`: due 23:30 local → deferred to 08:00. A leave_now due in quiet hours → skipped, not deferred. Time
   zones: a Lisbon booking (UTC+1 in summer) vs Madrid (UTC+2).
3. `test_cap`: six due messages in one local day → exactly 4 sent, in §1.3's priority order; the brief is dropped first.
4. `test_once`: two ticks → one `day_before` per booking (the unique index); a booking re-confirmed later doesn't get a
   second.
5. `test_optout`: `all_off` → nothing; `off_kinds=['morning_brief']` → no brief, the rest sent; S-75 STOP → `deliver`
   refuses (`:346`).
6. `test_cancelled_between`: cancelled after the tick selected it but before the send → no message (the status re-read).
7. `test_written_confirmation`: a `booking_inbound` email row with `reading.result=confirmed` → one "confirmed in writing
   ✅". With `proposed` → the "offer, not booked" text. Unmatched (`trip_item_id null`) → nothing.
8. `test_leave_now`:
   - no `guest_places` → no leave_now;
   - Routes returning 1800 s → sent at `date_time − 40 min`;
   - a Routes error → no leave_now, logged, **never a haversine estimate** (assert the text never contains a duration
     when the route failed).
9. `test_template_selection`: out of window with a SID → the template and variables; without one (the sandbox) → "not
   sent" and logged; a missing reference → "none given".
10. **Live (sandbox, the founder):** a booking for tomorrow 21:00; a fake-clock admin trigger at 18:00 → the
    in-window day_before arrives; save "my hotel" → leave_now on the day; a venue email confirmation → "confirmed in
    writing ✅".

---

## 7. Build order

1. Apply **026** (chat, preview first). Consent v3 (§3a) ships with step 2. Nothing proactive goes to anyone before it.
2. `proactive.py`: `render` + rules (tests 1–6).
3. Written confirmations (test 7).
4. `guest_places` + the settings UI + Routes (the founder enables the API; test 8).
5. The templates (test 9). **Submission waits for production (F-1)**; in the sandbox, in-window only.
6. Live (test 10).

---

## 8. The demo beat (added to `docs/business/investor-demo.md`)

- **"Confirmed in writing ✅" is the live beat.** After the Spanish call (the run of show, 1:30–2:45), the friendly
  venue's follow-up **email** confirmation arrives (Sasha asks for it in writing, `followup.py:138–152`). Within a
  minute, WhatsApp shows *"Casa X confirmed in writing ✅: 21:00 tomorrow, 2 people, ref …"*. **Live, no trigger
  needed**, if the venue replies by email during the demo (pre-arranged).
- **The day-before and the morning brief** can't happen inside 6 minutes. Use an **admin "send due messages as of
  {time}"** trigger, available only to the founder's account, and **say so on stage**: *"This is tomorrow at 18:00, sent
  early for the demo."* Never present it as having happened on its own.
- **leave_now** only if the Routes API is enabled and "my hotel" is saved. Otherwise skip it.

---

## Built, Sasha 109–110 (2 Oct 2026)

- **`booking_signer/proactive.py`** implements §1–§5:
  - `render` (one owner of the words), quiet hours, the daily cap with §1.3's priority, once per kind per booking (the
    ledger is claimed before delivery), the status re-read at the send, and per-kind and full opt-outs;
  - written confirmations from `booking_inbound`;
  - leave_now via the Routes API only (never straight-line);
  - `deliver_or_template` with `SASHA_WA_TEMPLATES` SIDs, and "not sent" without them, as in the sandbox;
  - the loop in the retention shape (`SASHA_PROACTIVE_LOOP`). Until 026 is applied it logs "not running" every ten
    minutes and sends nothing.
- **Consent v3 (§3a)** is now `CURRENT` for new links; v2 links keep v2.
  - A v2 guest gets only written confirmations, and is asked ONCE on their next message ("Reply YES REMINDERS"); the
    ask is recorded as `all_off` until they say yes.
  - "STOP REMINDERS" and "YES REMINDERS" work on WhatsApp.
- **Web:** reminders on/off and the starting point, in the WhatsApp block on the booking page.
- **The founder's demo trigger:** `POST /api/booking/proactive/run {as_of}`, his account only (§8: say so on stage).
- **Erasure:** `DELETE /account/data` also empties the three tables (test 11).
- **One change from §3's draft SQL:** `guest_places.lat/lng` are nullable and left empty. Only the address the guest
  typed is kept, and Routes takes it as the origin; coordinates looked up from Google would be Google content.
- **Known limit:** the leave_now destination is the venue's name, as the reservation knows it. If Routes can't resolve
  it, there's no leave_now (logged), never an estimate.
- **Tests:** `tests/test_proactive_s83.py` covers §6 tests 1–9, 11 and 12. Test 10 is the live one, after 026 is applied
  and the Routes API is enabled.
