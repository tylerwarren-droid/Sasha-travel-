# Sasha 150: the move to the EU, CR 23's hooks, and the six verify-once links

*5 Oct 2026. Commits 7fdcbfc, 0a8decf and 61fa39f (gate green). The founder's decisions, in his words: "move the Railway
service to the EU", "YES to CR 23's hooks".*

## 1. The move: sfo → europe-west4

- **What was done** (Railway's API):
  - `multiRegionConfig` changed from `{"sfo": {"numReplicas": 1}}` to `{"europe-west4": {"numReplicas": 1}}`, then
    redeployed.
  - It's the same service with the same variables.
  - No volume is attached (`volumeMounts: []`), so nothing had to move with it.
  - The chat SQLite file lives in the container, so it starts fresh on every deploy, as before.
- **Live at 10:59 CEST.** The server reports `europe-west4-drams3a`.
- **Rollback:** not needed.
  - The old setting is saved in `s150_rollback_region.json`.
  - To roll back: set it again, redeploy, and unset `DEEPGRAM_API_BASE` and `DEEPGRAM_STT_BASE`.

**Measured on the server (`/ops/perf`), p50 / p95 in ms**

| Step | Before (sfo) | After (europe-west4) |
|---|---|---|
| **One database query** (Supabase eu-west-1) | **147 / 293** | **18 / 35** |
| A web turn answered by the model | 1,744 / 2,007 | 959 / 1,426 (875 / 1,257 in the first run) |
| A web turn with no model | 1 / 26 | 0 / 9 |
| Google "Find venues" | 283 / 289 | 298 / 302 (Google's own time) |
| The model alone (Haiku 4.5) | 464 / 1,565 | 448 / 478 |
| **/voice, speech in → reply spoken** | **539** (STT 155, TTS 405) | **305** (STT 152, TTS 126) |
| New connection: Anthropic / Bland / Twilio | 92 / 100 / 19 | 123 / 251 / 14 (US-hosted: slightly further) |

**From Madrid** (the guest's side):
- health 0.88–1.30 s → **0.49–0.57 s**;
- a web booking turn 0.44 s → 0.45 s;
- a model web turn 1.64 s after the move.

**Deepgram, found on the way, and fixed**
- **The problem:** with Deepgram's US endpoint, /voice went from 0.54 s to 1.55 s right after the move. Every request was
  a new connection across the Atlantic.
- **What changed:**
  - Deepgram's address is now a setting (`DEEPGRAM_API_BASE`);
  - its calls use the pooled, kept-alive client;
  - speech-to-text may use its own endpoint (`DEEPGRAM_STT_BASE`).
- **Measured from europe-west4:**
  - the EU endpoint's text-to-speech is fastest (126 ms);
  - its speech-to-text was slower (1.8 s) than the US one (0.15 s).
- **Set on Railway:** TTS EU (`DEEPGRAM_API_BASE=https://api.eu.deepgram.com`), STT US
  (`DEEPGRAM_STT_BASE=https://api.deepgram.com`). /voice is **0.31 s**.

**Verified after:**
- health 200, every section present;
- the database (18 ms);
- one simulated WhatsApp card turn (the founder's account, sender simulated): header at 1.0 s cold, cards by 2.0 s;
  0.42 s warm;
- two web turns (a booking hand-off, and a model answer).

## 2. CR 23: the founder's yes, wired

- `routes.py` mounts `handover.router` and `handover.ops`.
- `gate.py` lets **GET** `/api/booking/handover/*` through. The 32-byte token in the URL is the key, compared in constant
  time by CR's handler, and read-only sessions are refused.
- **Still behind the key:** the POST that starts a hand-over (`/forms/{id}/handover`), `/ops/handovers`, and every other
  route.
  - Test: `test_booking_gate.test_the_live_handover_page_is_public_by_its_token_only`.
- **Real guests stay refused** until `BROWSERBASE_DPA=signed`: fictional details only.
- **CR is asked to re-time it from Railway** with one test-venue booking. CR's numbers go in the readout when they come.

## 3. The six verify-once links (CR 22)

- **How they're sent:** only once the founder's own message reopens WhatsApp's 24-hour window, and 90 s after it, so his
  turn finishes first.
- **What's sent:** a short intro, then six messages, one link each, with what it should show:

  | # | Engine | Venue | Should show |
  |---|---|---|---|
  | 1 | TableCheck | The Hill Station, Hoi An | 20 Nov, 19:00, 2 people |
  | 2 | SevenRooms | EVOK Brach, Madrid | 20 Nov, 20:30, 2 people |
  | 3 | Cloudbeds | Fuse Old Town, Hoi An | 20–22 Nov, 2 adults |
  | 4 | SiteMinder | ÊMM Hotel, Hoi An | 20–22 Nov, 2 adults |
  | 5 | Omnibees | Masa Hotel Campo Grande, Lisbon | 20–22 Nov, 1 room, 2 adults |
  | 6 | Guestcentric | Emporium Lisbon Suites, Lisbon | from 20 Nov, 2 nights, 2 adults |

- **His answers** ("1 filled", "2 not filled", "3 wrong page") are recorded by the `engine_check` step and confirmed one
  by one. The wording now counts its own links (six), not "three".
- **When he answers,** the results go to CR, so that `engine_library.Engine.verified` is set.

## 4. For the founder

**Pre-warm (Ops → Pre-warm) AFTER the last deploy before Wednesday.** This move and four config deploys today emptied the
photo cache.
