# Sasha 149: performance round 2 (before → after)

*5 Oct 2026. Commits 450c0c2 (the measuring endpoint) and 507329c (the changes); gate green, 1,142 tests.
`SASHA_STREAM_CARDS=1` is set on Railway.*

**How it was measured**
- **On the server itself** (Railway), with `POST /api/booking/ops/perf` (founder only; `booking_signer/perf_ops.py`).
  Every step runs a few times; the figures are p50 / p95 in ms. Raw JSON: `s149_before.json`, `s149_after.json`
  (scratchpad).
- **WhatsApp:** the founder's account, real Google and the venues' own photos, the sender **simulated** (nothing sent).
  Harness: `s149_cards.py`.

## 1. The numbers

| Step (on the server) | Before p50 / p95 | After p50 / p95 |
|---|---|---|
| **One database query** | **444 / 445** | **145 / 290** (132 / 264 after 10 min idle) |
| Google "Find venues" (Places) | 311 / 352 | 294 / 305 (Google's own time) |
| A web turn answered by the model | **2,568 / 2,783** | **1,365 / 1,920** (it makes database queries before the model answers) |
| A web turn with no model (booking hand-off) | 0 / 20 | 0 / 10 |
| The model alone (Haiku 4.5, one line) | 397 / 402 | 472 / 481 (Anthropic's own time; varies) |
| /voice, speech in → reply spoken (deterministic answer) | 236 total: STT 64, conduct 1, TTS 172 | 248 total: STT 68, TTS 187 (unchanged: already fast) |
| Routes, new vs reused connection | 189 → 46 when reused | now reused (a pooled, kept-alive client) |
| Bland, new vs reused connection | 59 → 39 when reused | now reused |

| WhatsApp cards (from here, simulated sender) | Before (all together) | After (streamed) |
|---|---|---|
| First message, cold cache, p50 | 1.36–1.65 s | **1.04–1.09 s** |
| First message, warm cache, p50 | 0.35–0.38 s | 0.33–0.35 s |
| **When the header (the first message) arrives** | after the photo budget: up to search + 1 s | **always at search time** (0.31–0.37 s warm) |
| Last card | at most search + the 1 s photo budget | the same bound, each card in rank order as soon as its own photo is ready |

**After 10 minutes idle** (no requests from us):
- database 132 ms;
- Find 272 ms;
- a no-model web turn 0.44 s from Madrid;
- `/health` 1.39 s on the very first request, then 0.83–0.91 s. The first request pays a new TLS handshake from Madrid to
  San Francisco: that's the region, not a cold server.

## 2. What changed, and why

1. **Cold starts.**
   - Railway's sleep was already **off** (`sleepApplication: false`), with one replica. The service never scaled to zero.
   - Added: the database pool keeps **one connection always open** (`min_size=1`).
   - Added: a **1-minute keep-warm** inside the server (`SASHA_KEEP_WARM`, default on). It touches the database and the
     hot path's hosts' root pages (Google, Duffel), which are not API calls and are not billed. Status at
     `GET /ops/perf/warm`.
2. **Models.** The hot path already used the fastest model, and nothing changed:
   - intent is keyword rules, with no model;
   - the conductor and replies run on Haiku 4.5 (`FAST_MODEL`).
   - The larger models are used only off the hot path, where accuracy matters: Sonnet 5 reads call transcripts, Opus 5.5
     reads passports, Sonnet builds itineraries.
3. **Streaming.**
   - **WhatsApp:** the header is sent at once, then each card the moment its own photo is ready, in rank order. A slow
     photo holds only its own card and follows later; the buttons come last (`SASHA_STREAM_CARDS=1`).
   - **Web text: not built, on the numbers.** Sasha's web reply is one Haiku call writing about 25 words (`max_tokens`
     200, spoken). The wait is the database plus the model's first word, not the writing, so streaming would save under
     0.1 s.
4. **Region: measured, not moved** (the founder decides). See §3.
5. **/voice: measured.** Speech in → reply spoken is **0.25 s** server-side when the answer needs no model: STT 68 ms,
   TTS 187 ms. A model answer adds the model turn above, and nothing in /voice itself is worth cutting.
6. **Connection reuse.**
   - **Database:** each query made **3** transatlantic round trips (prepare, execute, a session reset on release). Now it
     makes **1**.
     - No reset: this code holds no session state. An open transaction is still rolled back.
     - Prepared statements are cached on the **session** pooler. The deployment uses Supabase's port 5432, which is
       session mode, so the old comment about "transaction mode" was wrong.
     - Never on 6543. `SASHA_DB_STATEMENT_CACHE` overrides.
     - Tested against the real pooler: no statement clash across four successive pools.
   - **HTTP:** one pooled, kept-alive client per event loop (`booking_signer/http_pool.py`) for the ladder, the calls and
     Routes.

## 3. Region: the founder's decision

- **Railway runs in sfo (San Francisco). Supabase is in eu-west-1 (Ireland).**
  - One database round trip from the server is **≈ 145 ms**.
  - A WhatsApp turn makes about 3 database queries: ≈ 0.4 s of each turn is the Atlantic.
  - A pick makes 1–2 more.
- **The guest is in Madrid**, so every web request also crosses the US twice: a new connection costs ≈ 0.5 s more.
- **If moved to Railway's EU region** (europe-west4, Amsterdam), estimated:
  - database ≈ 15–25 ms per query: **≈ −0.4 s per WhatsApp turn**;
  - web connections from Madrid ≈ −0.3 s;
  - Anthropic, Twilio, Bland and Deepgram are US-hosted: **≈ +0.1 s per model call**;
  - Google (Places, Routes) is global: no change.
- **Recommendation:** move to the EU. It's a redeploy of the same service, with **not moved without the founder's yes**.
  After a move, pre-warm again.

## 4. For the founder

- **Pre-warm (Ops → Pre-warm) AFTER the last deploy before Wednesday.** Every deploy empties the photo cache, and several
  happened today (the last was the SASHA_STREAM_CARDS switch).
- **Region:** answer yes or no to the move in §3.
- **CR 23** (Browserbase live hand-over) asks for two lines in my files:
  - mount its router;
  - **an exception in the booking gate:** `GET /api/booking/handover/*` is public, keyed by a 32-byte token in the URL.
  - **Your yes needed** for the gate exception. CR has added nothing meanwhile.
