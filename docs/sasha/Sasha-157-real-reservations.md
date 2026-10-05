# Sasha 157: real reservations, every state honestly

*5 Oct 2026. Commits e609a33 (states) and e3bbe0d (the mailbox hook). Founder account only. Nothing is sent to a real venue
without his own yes.*

## 1. "dinner for 2 in Madrid tomorrow at 9": the top 3 real cards, each prepared to its read-back and STOPPED there

| Card | Route Sasha uses | Why |
|---|---|---|
| **D-Sunset Madrid** ★4.9 | **WhatsApp**: Sasha writes the message and **you** press send from your own WhatsApp | No booking form or email on their site. Their phone is listed, but calls are off on the server (`SASHA_CALLS_ENABLED` ≠ 1). |
| **Ástor gastro-place** ★4.9 | **CoverManager page** (the platform). Sasha hands you their page plus the day, time and party, and **you** make the final press | Their site books only through CoverManager. Sasha never presses on a platform, and never fetches a platform page. |
| **Los Montes de Galicia** ★4.8 | **Email** to info@losmontesdegalicia.es (the address on their own site), from sasha@booking.kanoe.ai, BCC to you | They book through CoverManager, but their site doesn't link that page, and Sasha never guesses one. Calls are off. |

**Read-backs** (verbatim in the session log):
- **Ástor:** "Restaurante ÁSTOR takes bookings only through CoverManager, so you make the final press… pick Tuesday 6 October at
  9 pm, for 2… forward the confirmation to act-…@booking.kanoe.ai and I'll put it in your trip."
- **Los Montes:** "I'll email Los Montes de Galicia at info@losmontesdegalicia.es… You're copied privately (BCC) at
  tyler@kanoe.ai… Subject: Solicitud de mesa — 2 personas el 2026-10-06 a las 21:00… Shall I send it?"

**Nothing was sent.** The email row is still `awaiting_approval`. The prepared items were cleared from your itinerary
afterwards, so your yes starts from a fresh ask on your phone.

## 2. The itinerary's states (added; verified live on OUR test venue)

**What each state shows:**
- **Requested** (sent): "Requested — waiting for <venue>". Google Calendar gets a tentative "(requested) <venue>" event
  ("Not booked yet").
- **Confirmed**: "Confirmed — <venue>: “their own words” · their ref <ref>". The calendar event becomes confirmed.
- **Declined**: "Declined — <venue>: “their own words”". A written "no" was filed as *unclear* before. The calendar event
  is removed.
- **Where:** the web itinerary (Trip; phone and desktop are the same page) shows these. So does the chat's "what's on my
  itinerary…" (web and WhatsApp), which showed **no state at all** before and hid declined bookings.
- **Updates by themselves:** a venue's email reply is read by the same function the inbound mail calls, and moves the state.
  A call's outcome already did (S-41). Calls are off on the server, so a call isn't re-verified here.

**Live, as the founder, on Sasha Test Venue:**

| Route | Step | What the itinerary showed |
|---|---|---|
| Email | Sent | "Requested — waiting for Sasha Test Venue" |
| Email | Their yes | "Confirmed — Sasha Test Venue: “Hola Sasha, sí, confirmamos la mesa para 2… Localizador PRUEBA-77…”" |
| Email | Their no | "Declined — Sasha Test Venue: “Lo sentimos, no tenemos mesa ese día, estamos completos.”" |
| Form | Sent | "Confirmed — Sasha Test Venue: “Reserva confirmada… Localizador: TV-0B010E-85…” · their ref TV-0B010E-85" |

- **Calendar outbox:** every change was processed without error. A request created an event, a confirmation updated it,
  and a decline removed it.
- **Cleanup:** the test bookings were cancelled. Calendar test events left: 0.
- **A new test page:** `/api/booking/test-venue/email` publishes only an address on our own domain, so the email route can
  be rehearsed on a venue that is ours.

**Gap found, not fixed (no OK yet):** you can't cancel an **email-route** booking from Sasha. The cancel route knows calls and
forms only (`cancel_routes._booking`).

## 3. Try it on your phone (WhatsApp to Sasha)

1. Type **dinner for 2 in Madrid tomorrow at 9**. You get three restaurants with photos, plus our test venue.
2. Tap **Los Montes de Galicia**. Sasha shows the exact email she'll send, and to whom.
3. Type **yes**. She says "Sent…", and your itinerary shows **Requested — waiting for Los Montes de Galicia** (Calendar:
   "(requested)…").
4. When they reply, it changes by itself to **Confirmed — Los Montes de Galicia: “their words”** (or **Declined**), and
   Calendar follows.
5. Check it anywhere: **what's on my itinerary tomorrow?** on WhatsApp, or **Trip** on project.kanoe.ai on desktop.

## 4. The mailbox Stop hook

- **Files:** `scripts/mailbox_stop_hook.py` and its tests, `scripts/test_mailbox_stop_hook.py` (6 pass), committed in
  e3bbe0d.
- **When it applies:** only to a prompt labelled **"Sasha <n>"** or **"CR <n>"**. The US and EU tabs' prompts pass
  untouched.
- **What it checks:**
  - the turn must contain a successful `insert into public.tab_messages` for tab SASHA/CR, with the body starting with the
    label, made after the prompt;
  - when `AD_MAILBOX_URL` and `AD_MAILBOX_KEY` (a read-only key) are set, it also checks the row is in the table.
- **What it does:** it blocks at most twice per prompt, then allows the stop with a loud warning. A failure of the hook
  itself never blocks.
- **Tested live** against this session's own transcript: it blocked Sasha 157 before its readout ("1/2: no readout for
  'Sasha 157'…").
- **Where it is registered:** in `Applied Diligence/.claude/settings.json` (a `Stop` hook), because this tab's sessions run
  in that folder. **That file is the US tab's to commit (TO FILE).** This tab never commits in AD.
