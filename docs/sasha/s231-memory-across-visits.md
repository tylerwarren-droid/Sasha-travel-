# Sasha 231 · /s2 memory across visits

## What /s2 remembered between visits BEFORE 231 (read from the code at 3211c33)

| What | Where it lived | How long |
|---|---|---|
| The conversation | Only in the open tab: S2App's `histRef` (React memory), sent back as `history` each turn. Nothing on the server. | Until the tab closed or reloaded. Gone. |
| Session-scoped state (cards on screen `_SCREEN`, openers used `_OPENERS`) | Backend process memory, keyed by the page's session id. The id is new on every page load. | Unreachable after a reload: the new session can't find it. |
| A hold awaiting a yes (venue, flight, email, WhatsApp, change/cancel) | Backend process memory, per account: `_HELD` in venues / v0 / s2_tools / s2_whatsapp / s2_manage, plus CR 76's `_RB`/`_APV` in yes_gate. | 15 min (READ_BACK_TTL_S / YES_WINDOW), or until a restart. A reopened page didn't mention it: no history, so she didn't know. |
| Cards she'd shown (`venues._SHOWN`) | Process memory, per account | Until a restart |
| "We've met" | localStorage `s2_met` (230): her face says "Hey, welcome back!" | This browser only |
| Durable records | Postgres: s2_acts (Activity), plans/trips, venue bookings, s2_rentals, the Keep, WhatsApp state | Permanent. But nothing of the conversation, and no unfinished task. |

In short: a closed tab lost the conversation and anything unfinished. Only what was DONE (Activity, bookings) survived.

## What 231 keeps (agapi/s2_memory.py)

Per account, one row:
- **recent:** the last 20 lines (theirs and hers), each read through the vault and Keep guards first. A card, password, passport or ID value is never kept; the whole line becomes `[removed]`. Masks such as "Passport ES ••••456" are kept.
- **summary:** a short running list of topics (≤ 6).
- **thing:** what they were looking at, e.g. "Italian restaurants in Madrid, tonight 21:00".
- **pending:** anything unfinished, either a hold awaiting their yes (and which one) or the question she last asked.
- **screen:** the cards she showed, without photos, so a return fetches no photos.

On return (`GET /api/s2-memory` → backend `/api/agent/s2/memory`, /s2 only), within 24 hours:
- She says "Welcome back — we were looking at <thing>. Want to carry on?", spoken by her face in place of "Hey, welcome back!".
- The page shows the last lines and her cards. Those cards are on screen again for the new session, so she may name them and a Choose tap matches them.

Nothing is offered once the thing was done (booked/sent), after 24 hours, or after "thanks / bye" (unless a hold still waits for a yes).

**Storage:** `s2_memory` (booking_signer/sql/041_s2_memory.sql). This is a DRAFT: apply it after this deploy. Until it's applied, the memory lives in the backend process. A redeploy forgets it and nothing fails.

## Proof (live, project.kanoe.ai/s2, phone-sized, scratch guest 204e2a90, deleted after)

Recording: `s231-memory-return.gif` (52 frames). Stills: `s231-shots/`.

1. "Find me somewhere Italian for dinner for two in Madrid tonight at 9." She showed 5 cards. This was the run's one live search; "carry on" reused it from the cache.
2. /s2 was closed, then reopened in a new tab. Her face said: "Welcome back — we were looking at Italian restaurant in Madrid, Saturday 10 October 21:00. Want to carry on?" The last lines and her cards were back on screen.
3. "Yes, carry on." She carried on from the same cards ("back on your screen… which one should I try?").
4. Choose was tapped on "Beata Pasta - Gran Vía". The tap sent its place_id ChIJdbYp…; the hold's focus was ChIJdbYp…, the same card and not "Beata Pasta - Goya" (ChIJM9Dv…). Her read-back followed. It was never sent.
5. "Thanks!" She answered "OK! Just tap me if you need me — I'm right here." The page faded to 0.22 and the mic was unmounted. A tap brought her back at 1.0 with the mic, and she said nothing more.
6. On reopening again, the memory had the hold: "Welcome back — we were looking at Beata Pasta - Gran Vía — it's ready, waiting for your yes. Want to carry on?"
7. "Gracias, eso es todo" got "¡Vale! Tócame si me necesitas, aquí estoy." and she rested.
8. The bubble no longer covers "Type instead": the link spans 752–780 px and the bubble 658–716 px.

The memory endpoint held no run of 8+ digits; a card number typed in a unit test was stored as `[removed]`.
