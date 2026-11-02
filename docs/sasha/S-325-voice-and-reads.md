# Sasha 325 · the voice never reads a mark aloud, and one read per refresh

Tyler's S2 train test, 2 Nov 2026:
- She said "star 1 person" and "star 15:30 in the afternoon".
- agapi-live refused ~280 of Sasha's calls in two minutes (14:52:30–14:54:22 UTC), all with 429.

## Root test (written before the code)

### 1. The one place, confirmed by file

**Bug A, speech.**
- Every word Sasha says aloud becomes audio in ONE engine: `app/api/voice_conductor.text_to_speech`.
  - It produces her voice as mp3 (`/api/voice/tts`).
  - It produces her face's lip-sync audio as raw 24 kHz PCM (the same route with `format: "pcm"`).
  - WhatsApp voice notes and the voice conductor also use it.
  - The ticket said `voice.py`, but `voice.py` writes her lines and makes no audio.
- Before this fix there was a SECOND engine: the Next route `frontend/app/api/s2-voice/pcm`, which made her face's audio.
  - Each engine stripped a few marks of its own: `*` and `#`.
  - Neither stripped `·`, which the speech engine reads as "star". Her trip lines use it: "Mon 2 Nov · 15:30 · 1 person".
- Now there is ONE engine (the Next route is deleted), and its first step is `spoken.speakable`.
  - That function's first step is `spoken.marks`, which drops every layout mark and keeps the words: `·` `•` `*` `_` `#` backticks, bullets, headings, `[label](url)` becomes its label, links are dropped, `→` becomes "to".
- HeyGen's avatar speaks whatever `heygen_chat` returns, so that reply passes `speakable` too.

**Bug B, booking status.**
- The ONE source of a booking's status is AgAPI: `venue.bookings` gives every act on the record with its state in one call.
- Sasha reaches it through its ONE transport, `agapi_route.post`.
- Sasha's ONE reader is `venue_submit.bookings`. Every screen's read goes through it:
  - the trip's Journeys and Plan;
  - `get_status`;
  - `trip_status`;
  - the itinerary.
- Why there was a flood: every refresh, every 6 s on each of the two trip pollers, asked AgAPI three to five times over.
  1. `venue_submit.bookings` asked `venue.booking_status` once for each open act (the per-item fan-out).
  2. The same refresh reached it two or three times: Plan read `venue_rows`, then `venue_bookings`, then `trip_status`, and each read the acts again.
  3. Nothing waited after AgAPI's 429. The next refresh asked again at once, and every refused call counted toward the minute.
  4. `access.get` was read every 60 s per account, every 10 s after a failure, and by every request at once on a cold read.

### 2. PATCH check

- **Raising AgAPI's limit:** not done.
- **A per-screen throttle:** not done. The screens still refresh every 6 s.
- **Stripping `*` in one template:** not done. One function is applied to every spoken line.
- **PATCH (said honestly): one shared read per account per refresh window (`RECORD_S`, 10 s).**
  - Every reader in that window (Journeys, Plan, a turn's `get_status`, the sweep) gets the same answer from `venue.bookings`.
  - That answer is a cache, kept for at most 10 s.
  - It exists because nothing tells Sasha when an act changes, so a screen can only learn by asking.
  - The root alternative is AgAPI pushing an act's change to Sasha (a signed webhook). That is AgAPI's to add, proposed as a CR.
  - Until then, the 10 s window is what "no re-ask while nothing changed" means in practice.
- **Not a patch: AgAPI's own Retry-After is kept.**
  - After a 429, the transport doesn't send to that key until AgAPI's `Retry-After` has passed.
  - That is AgAPI's documented client contract ("wait `retry_after_s`, then retry"), not a throttle of Sasha's.

### 3. Whole class impossible?

**Bug A: yes.**
- There is one engine, and its first step is `speakable`.
- A test runs every module constant and every `*_line` template in `voice.py`, `sasha.py` and `s2.py` through it. None may come out with a mark.
- A scan fails the build if any other file calls Deepgram's `/v1/speak`.

**Bug B: yes for the fan-out.**
- `venue.booking_status` is asked only for an act whose entry on the record CHANGED since it was last read. That covers a venue's reply, a cancel answered, and a change answered.
- It is asked once per change, never once per refresh.
- In steady state each refresh makes ONE `venue.bookings` call per account, shared across all readers.
- `access.get` is read once per session (15 min), with one read in flight at a time. After a failure it waits AgAPI's `Retry-After`.
- One exception remains: an AgAPI without `venue.bookings` (older versions; not live or sandbox today) still gets the per-act reads.

## The health email

The email now says which of the two outages it was, in one sentence:
- **429:** "AgAPI's per-minute rate limit (429): too many calls in one minute. The key's budget is fine, and it clears by itself within a minute."
- **402:** "the key's monthly budget is spent (402)."
