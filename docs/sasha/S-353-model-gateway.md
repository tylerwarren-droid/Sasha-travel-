# Sasha 353 · EVERY model call through ONE gateway: only what the turn needs, the stable part cached, metered and capped

Tyler, 6 Nov 19:01: "drastic measures to cut this". FROZEN BETA LIST: SME demo. This ticket follows the NO PATCHES rule.

## STEP 1 · measured before changing anything (6 Nov, count_tokens on the requests the code builds; nothing sent)

**Method:** the real turn ran for the test organiser on production's data, with a client that captured each request instead of sending it. Each part was counted with Anthropic's free `count_tokens`.

| Run (first model step, a 30-line conversation) | Input tokens | System | Tools (count) | History |
|---|---|---|---|---|
| S2 turn ("What's Lisbon like in November?…") | 26,872 | 6,404 | 19,808 (78) | 622 |
| WhatsApp turn (the same) | 27,025 | 6,557 | 19,808 (78) | 622 |
| S1 (/next) turn | 27,114 | 7,401 | 19,672 (78) | — |

**The deploy gate** (its own cost report, a209d897):
- Verdict: 278 model calls, 5.82 M input tokens (5.38 M cache reads), $1.81 plus Opus (unpriced).
- After it: the loop-5 probe (6 conversations), the voice proof and the pay proof.
- It ran on the service's own key (no `SASHA_GATE_ANTHROPIC_API_KEY`).
- Railway shows 20 deploys on 6 Nov.

**Real S2 turns:** `sasha_measures` shows 43 turns on 6 Nov, ≈ 2.2 M tokens (90 % cache reads).

**Top 3 consumers:**
1. **The deploy gate:** ≈ 6–8 M tokens a run × 20 deploys ≈ 120–160 M tokens on 6 Nov. The 50–170 M a day is the gate.
2. **The tool definitions:** 19,808 tokens, 75 % of every call of every step.
3. **The system prompt:** 6,400–7,400 tokens on every call.

History and the 349 record are small: the page sends the last 30 lines, ≈ 600 tokens.

## The one gateway: `backend/booking_signer/model_gateway.py`

`install()` wraps the Anthropic SDK's own methods: async and sync `create`, `stream`, and the beta namespace.
- **Every call passes here,** from any module, the CTO's 30-odd call sites included, whichever client built it.
- **It is installed where the service starts** (`booking_signer`, imported by app.main's Stage B mount) and by the gate.
- **A test fails** on any other way to reach the API.

On each call, in order:
1. **Caps.** A global daily cap (`SASHA_MODEL_DAILY_TOKENS`, default 25 M) and a per-account daily budget (`SASHA_MODEL_ACCOUNT_DAILY_TOKENS`, default 2 M), counting input + cache + output.
   - They are kept on the record (`sasha_measures` `model_day:<date>`), so a restart never resets them.
   - Over a cap, the call is REFUSED loudly (`ModelBudgetExceeded`, logged as an error) and never sent.
2. **The model.** Opus runs only with `SASHA_MODEL_ALLOW_OPUS=1`; otherwise Sonnet. Opus was never measured as necessary: it "weighed" search results.
3. **Only what the call needs.**
   - History is the recent 8 turns, cut only where a turn begins (a tool_use always keeps its result); the running summary is the caller's.
   - The fixed parts (the system prompt's first block, the tool list) carry the cache mark.
4. **The gate's replay.** `SASHA_MODEL_REPLAY=replay` answers from RECORDED replies, kept on the record (`sasha_measures` kind `model_replay`, a year) because Railway's containers forget files.
   - The replay key leaves out what changes run to run: the system prompt (the date), numbers, ids and month names.
   - The one live call is the preflight's 1-token Haiku check.
   - `SASHA_GATE_RECORD=1` makes the recordings in ONE live run. A request with no recording fails the gate by name.
5. **The meter.** Each call's usage, by model, caller (module) and account, logged and added to the day's record.

## Only what the turn needs: `backend/app/agent/tool_need.py` (the turn's half)

**Tool families:**

| Kind | Families |
|---|---|
| Always | core |
| A trip's | plan · book · after |
| A place's | find · reserve |
| Others | messages · keep · cards · claims · entry · subscriptions · group · activity · founder |

**How a turn picks them:**
- Its words and its last exchange (her last line and their message) select the families.
- "Book it" / "yes" go to the booking the RECORD is waiting on: a trip waiting for its next booking step (352's state) or places on their screen.
- Nothing named → core + finding a place (she tries first).
- A tool in no family is always offered.
- Every call code makes this turn (352's next action, a tap, a change's quote) is offered with it.

**The system prompt:** a rule bullet whose subject (the first tool it names) isn't offered is left out.

## After (the same runs, the same counting)

| First model step, a 30-line conversation | Before | After | Change |
|---|---|---|---|
| S2 · "What's Lisbon like in November?…" | 26,872 | 8,904 (19 tools) | −67 % |
| S2 · "Book it." (a trip waiting) | 26,854 | 8,886 | −67 % |
| S2 · "Find us a restaurant for dinner tonight near the hotel" | 26,875 | 10,639 | −60 % |
| S2 · "Hi Sasha!" (no history) | 26,212 | 6,502 | −75 % |
| WhatsApp · the same four | 27,0xx | 9,057 · 9,039 · 10,792 · 6,655 | −60 % to −75 % |
| Deploy gate, a run | 278 + ≈ 120 live calls, ≈ 6–8 M tokens | 1 live call (Haiku, 1 token) + replays | ≈ −100 % |

**Dollars,** Sonnet 5.5 at $2 / M input, $0.10 / M cache read:
- S2 / WhatsApp first step: $0.054 → $0.018 uncached; $0.0027 → $0.0009 cached.
- Opus steps now run on Sonnet.
- The gate: ≈ $2–3 a run → ≈ $0.

**Live S2 / WhatsApp turns:** ≈ −67 % on average across these four, below the 70 % target (the restaurant turn, −60 %, offers finding AND planning: "near the hotel"). The system prompt (≈ 4,100 tokens after) is now the largest part.

## Not proven yet (said)

The org's Anthropic credit is exhausted (−$0.28), so nothing live can run.
1. **The recordings** need ONE gate run with `SASHA_GATE_RECORD=1` once credit is back. Until then the gate fails at its preflight (credit), and after that at the first missing recording, by name.
2. **The voice loops on recorded replies,** and **a live S2 turn's measured $ through the gateway's meter,** wait for that run.

## Tests

- `backend/tests/test_s353_gateway.py` (the SDK's own client against a mock transport, nothing sent) covers:
  - every call passes the gateway;
  - the caps refuse loudly (per account, global, a stream), and a restart never resets them;
  - history cut at turn starts; the fixed parts cached; Opus → Sonnet;
  - the families, the record's go-ahead and the rule bullets;
  - the turn offers what its code calls;
  - record once → replay without the API, dates and ids aside; a missing recording refused; the gate replays.
- The surface-isolation tests (S1 vs S2, WhatsApp, parity) compare each surface's WHOLE set (`tests/whole_surface.py`).
