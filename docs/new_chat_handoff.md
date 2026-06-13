# Sasha / Kanoe — New Chat Handoff

**Last updated:** June 13, 2026  
**Project:** Kanoe travel platform — AI concierge branded "Sasha"  
**Repo:** github.com/tylerwarren-droid/Sasha-travel- (currently public for HeyGen review — make private once resolved)

---

## Repository structure

```
sasha-travel/
├── frontend/          # Next.js App Router, React 19, TypeScript, Tailwind — deployed on Vercel (sasha-heygen project)
│   ├── app/
│   │   ├── vietnam/page.tsx        # Main live demo — HeyGen avatar + Deepgram mic + SashaChat
│   │   ├── phuquoc/page.tsx        # Phu Quoc variant (same architecture)
│   │   ├── components/
│   │   │   ├── SashaAvatar.tsx     # HeyGen LiveAvatar session lifecycle
│   │   │   ├── SashaChat.tsx       # Chat UI + threads VoiceButton
│   │   │   └── VoiceButton.tsx     # AudioWorklet PCM → Deepgram STT
│   │   └── api/heygen/
│   │       ├── token/route.ts           # Vietnam token endpoint
│   │       └── token/phuquoc/route.ts   # Phu Quoc token endpoint
│   └── public/
│       ├── pcm-capture.js          # AudioWorklet processor (MUST exist for VoiceButton)
│       └── sasha_investor.html     # Investor portal — 5-tab app with 3-demo pill switcher
├── backend/           # FastAPI on Railway (sasha-travel-production.up.railway.app)
│   ├── app/
│   │   ├── api/conductor.py        # Main message router — dispatches agents
│   │   ├── services/*_agent.py     # 23 agent files (one each)
│   │   └── services/claude.py      # Claude API wrapper, intent extraction
│   └── migrations/
│       ├── 001_initial_schema.sql  # Supabase schema (10 tables, RLS) — LIVE
│       └── 002_clients_schema.sql  # Multi-tenant clients table
└── docs/
    ├── agents.md          # Full agent spec with triggers, capabilities, tools
    ├── data_model.md      # Full database schema spec
    └── session_june12_2026.md  # Session log with key decisions
```

---

## Deployments

| Service | URL | Platform |
|---------|-----|----------|
| Frontend (main) | sasha-heygen.vercel.app | Vercel — project: sasha-heygen |
| demo.kanoe.ai | demo.kanoe.ai → `/chat` route | Vercel — custom domain on sasha-heygen |
| investor.kanoe.ai | investor.kanoe.ai → `/` (serves sasha_investor.html) | Vercel — custom domain on sasha-heygen |
| Backend API | sasha-travel-production.up.railway.app | Railway |
| Supabase | xlqtveusyfpffaejegiq.supabase.co | Supabase — project: SASHA |

---

## Environment variables

### `frontend/.env.local` (local dev only — Vercel has its own env settings)
```
HEYGEN_API_KEY=...                    # Server-side only — used in /api/heygen/token routes
NEXT_PUBLIC_HEYGEN_AVATAR_ID=...      # Vietnam avatar ID
NEXT_PUBLIC_SUPABASE_URL=...
NEXT_PUBLIC_SUPABASE_ANON_KEY=...
NEXT_PUBLIC_API_URL=http://localhost:8000   # Switch to Railway URL for production
NEXT_PUBLIC_DEEPGRAM_API_KEY=...      # Client-side STT key
```

### `backend/.env` (local) / Railway environment variables (production)
```
ANTHROPIC_API_KEY       # Claude API — Default/AppliedDiligence workspace
DATABASE_URL            # Supabase Postgres connection string
SUPABASE_URL            # Supabase project URL
SUPABASE_SERVICE_KEY    # Service role JWT (rotated after exposure incident)
DEEPGRAM_API_KEY        # Backend voice pipeline
RESEND_API_KEY          # Restaurant email reservations (rotated after exposure)
STRIPE_SECRET_KEY       # Payments
EXPEDIA_API_KEY / EXPEDIA_API_SECRET
RATEHAWK_API_KEY / RATEHAWK_API_URL / RATEHAWK_KEY_ID
```

**Security note:** Resend API key and Supabase service role JWT were exposed when the repo was briefly public for HeyGen debugging. Both were rotated. Railway env vars are the source of truth for production.

---

## Database schema — LIVE

Migration `001_initial_schema.sql` has been run against the Supabase SASHA project. All tables exist with RLS enabled.

**10 tables:**
- `user_profiles` — extends `auth.users`, app-level role and display name
- `organizations` — multi-tenant orgs
- `traveler_profiles` — traveler details linked to user
- `trips` — trip records
- `trip_items` — individual bookings within a trip (hotel, flight, transfer, etc.)
- `booking_attempts` — booking attempt log with status
- `documents` — passports, visas, travel docs
- `escalations` — human escalation requests
- `conversations` — conversation history
- `calendar_events` — trip calendar

Full schema spec: `docs/data_model.md`

**Next step for database:** Wire agents to write `trip_items` rows when bookings are made (currently all bookings are mock/in-memory).

---

## All 23 agents

Dispatched by `backend/app/api/conductor.py` via keyword classification → `asyncio.gather` with 30s timeout. Multiple agents can fire in parallel per message. All agent tool calls use `claude-haiku-4-5`; only the conductor merge step uses Sonnet.

| # | Agent | Key triggers |
|---|-------|-------------|
| 1 | golf | golf, tee time, fairway, green fee |
| 2 | booking_confirmation | confirm booking, reservation number, PMS |
| 3 | beauty | massage, spa, facial, salon |
| 4 | health | doctor, clinic, hospital, pharmacy |
| 5 | dog_walking | dog, pet, kennel, grooming |
| 6 | foto | show me, photo, picture, what does … look like |
| 7 | restaurant | restaurant, dinner, eat, reservation + action word |
| 8 | smart_sasha | plan a trip, want to travel, fly to, vacation to |
| 9 | credit_card | credit card, points, miles, rewards, Amex, Chase |
| 10 | car_rental | rental car, hire a car, CDW, rental insurance |
| 11 | visa | visa, entry requirements, passport, do I need a visa |
| 12 | currency | exchange rate, ATM, cash, tipping, dong, baht |
| 13 | weather | weather, climate, best time to visit, monsoon |
| 14 | emergency | emergency, lost passport, stolen, embassy, help me |
| 15 | language | phrases, how do I say, etiquette, customs, dress code |
| 16 | packing | packing, what to bring, luggage, carry on |
| 17 | family | kids, children, baby, family travel, kid-friendly |
| 18 | airport_transfer | airport transfer, taxi, pickup, private car |
| 19 | experiences | cooking class, tour, activity, things to do, day trip |
| 20 | coworking | coworking, remote work, digital nomad, fast wifi |
| 21 | insurance | travel insurance, SafetyWing, World Nomads, coverage |
| 22 | loyalty | loyalty program, frequent flyer, hotel points, status |
| 23 | api_assimilation | api, integrate, which api, flight api, hotel api |

Full spec with triggers, capabilities, and tools for each: `docs/agents.md`

---

## Voice pipeline — current state

### Architecture (vietnam/page.tsx → SashaAvatar + SashaChat → VoiceButton)

```
HeyGen LiveAvatar (voiceChat: false)
  → AVATAR_SPEAK_STARTED  → gate mic ON  (VoiceButton drops PCM frames)
  → AVATAR_SPEAK_ENDED    → 900ms trailing timer → gate mic OFF
                          → first time only: onReadyToListen() → starts Deepgram

Deepgram (nova-3, streaming WebSocket)
  ← AudioWorklet (pcm-capture.js) → linear16 PCM at AudioContext native sample rate
  → interim + final transcripts → sendMessage() → conductor → Sasha response
  → response text → avatar.repeat(text) → HeyGen speaks it
```

### Key files

**`SashaAvatar.tsx`**
- `voiceChat: false` — we own the entire mic pipeline
- `avatar.repeat(text)` — speaks text (no second argument)
- `avatar.interrupt()` — stops mid-speech
- `avatar.keepAlive()` — every 150s
- `AgentEventsEnum.AVATAR_SPEAK_STARTED` → calls `onGate?.(true)` + `onAvatarSpeakingChange?.(true)`
- `AgentEventsEnum.AVATAR_SPEAK_ENDED` → 900ms trailing timer → `openGate()` → `onGate?.(false)` + `onReadyToListen?.()` (once only via `hasOpenedMicRef`)
- Safety timer: `Math.max(1500, text.length * 65) + 900` ms — fires `openGate()` if AVATAR_SPEAK_ENDED never arrives
- Reconnect on `SESSION_DISCONNECTED` unless `MAX_DURATION_REACHED`

**`VoiceButton.tsx`**
- AudioWorklet-based PCM capture (`/public/pcm-capture.js` — file exists)
- `micGatedRef = useRef(true)` — starts gated; gate is a pure ref flag (no audio pipeline pause)
- While gated: RMS measured — if > 0.0005 → user interrupt → `onInterrupt?.()` + gate opens immediately
- While ungated: float32 → int16 → `ws.send(int16.buffer)` to Deepgram
- Gate registered with parent on mount via `onSetGate` prop (stable ref, empty deps)
- `onSetGate` callback called from `SashaChat` → `VoiceButton` prop chain
- Gate flush: on gate-open, sends `{ type: 'Finalize' }` to Deepgram to discard buffered avatar speech
- Echo filter: 70% word overlap against `avatarSpeechGetter?.()` discards echo transcripts
- KeepAlive: every 8s to Deepgram
- No auto-reconnect on close

**`vietnam/page.tsx`**
- `handleSetGate = useCallback((fn) => { gateRef.current = fn }, [])` — stable ref
- `handleGate = useCallback((value) => { gateRef.current?.(value) }, [])` — stable ref
- `voiceReady` state — set by `onReadyToListen` event (fires once after first AVATAR_SPEAK_ENDED)
- `voiceReady` drives `readyToListen` prop on `SashaChat` → `VoiceButton` (Deepgram doesn't connect until avatar finishes first greeting)
- `isRespondingRef` lock — blocks transcript processing while Sasha is speaking

### HeyGen session config

**Vietnam** (`/api/heygen/token`):
- `avatar_id: 'ab0765ad-69de-41fb-9f8a-bd01c3c52d6f'`
- `context_id: '10b5933f-d54a-4305-9f88-333b628a1d09'`
- `voice_id: '62bbb4b2-bb26-4727-bc87-cfb2bd4e0cc8'`
- `speed: 0.8`
- No `llm_configuration_id` (no custom LLM — avatar speaks what `avatar.repeat()` sends)

**Phu Quoc** (`/api/heygen/token/phuquoc`):
- `avatar_id: '075abc67-2fae-4548-8ca9-b815fcbd34c7'`
- `context_id: 'f5721bed-ade9-4c26-9beb-7fd17d7d8211'`
- Same voice
- `llm_configuration_id: '4267be4c-8959-443d-b682-36e7fff89b4d'` (custom LLM configured)

---

## HeyGen debugging — current status

**Issue:** Echo / mic gate opening during avatar speech, occasionally causing Deepgram to transcribe the avatar's voice and trigger a premature response.

**Current mitigations in place:**
1. `micGatedRef` gate — PCM frames dropped while avatar speaking
2. 900ms trailing timer on AVATAR_SPEAK_ENDED — accounts for TTS tail
3. Safety timer per `avatar.repeat()` call — catches cases where AVATAR_SPEAK_ENDED never fires
4. Deepgram `Finalize` message sent on gate-open — flushes buffered speech
5. Echo filter — 70% word-overlap check on transcripts against last spoken text
6. `isRespondingRef` lock — blocks re-entry while conductor is responding

**Status:** HeyGen support reviewed source code (repo was public for this). Waiting on their diagnosis. Events `AVATAR_SPEAK_STARTED` and `AVATAR_SPEAK_ENDED` confirmed firing correctly in console. Gate mechanism confirmed working (console shows `[GATE] set to true/false`).

**If HeyGen responds:** Their fix likely involves the event timing or a `voiceChat: false` mode edge case. Apply whatever they recommend to `SashaAvatar.tsx`.

---

## Investor demo — sasha_investor.html

File: `frontend/public/sasha_investor.html`  
Live at: investor.kanoe.ai  
Git tags: `sasha-investor-v1`, `sasha-investor-v2-working`

5 tabs: Overview, Demo, Platform, Technology, Investment  
Demo tab has 3 pill options in the nav bar:
- **Luxurious Traveler** → `https://demo.kanoe.ai/chat` (iframe)
- **Vietnam** → `https://sasha-heygen.vercel.app/vietnam` (iframe)
- **Phu Quoc** → `https://sasha-heygen.vercel.app/phuquoc` (iframe)

Switching pills destroys the inactive iframe (`panel.innerHTML = ''`) and recreates on switch to prevent background audio/session bleed.

---

## Open items — next priorities

### 1. Database write — wire trip_items
When an agent completes a booking (currently mock), write a `trip_items` row to Supabase. The schema is live. Pattern: agent returns booking data → conductor passes to a `db_writer` helper → Supabase insert.

### 2. Browserbase re-implementation
`book_via_website` (restaurant agent) and `start_visa_application` (visa agent) used local Playwright which was removed (too heavy for Railway). Re-implement using Browserbase remote API only — HTTP calls to Browserbase → get CDP session URL → connect remotely.

### 3. API applications to submit
- **Duffel** — flights (easy approval, good sandbox, start here)
- **SafetyWing** and/or **InsureMyTrip** — insurance agent
- **Viator / GetYourGuide** — experiences agent (currently web-search only)
- **GetTransfer / Blacklane** — transfer booking

### 4. Next agents to build (post-API approval)
- `flights_agent` — Duffel API
- `hotels_agent` — RateHawk

### 5. Railway credits
Top up Railway — credits were low as of June 12.

### 6. Repo visibility
Make repo private once HeyGen confirms they no longer need access.

---

## Key rules / things that burned us

1. **Never pass a second argument to `avatar.repeat()`** — the SDK only accepts `(text: string)`. Passing options (e.g. `{ rate: 0.85 }`) causes a silent failure.

2. **`avatar.keepAlive()` not `avatar.ping()`** — wrong method name silently fails.

3. **Gate callbacks must use `useCallback` with empty deps** — inline arrow functions in the parent cause stale closures in `VoiceButton`. The gate never fires if the reference changes on every render.

4. **Deepgram should not connect until after first AVATAR_SPEAK_ENDED** — connecting immediately captures the avatar's opening speech as user input. Use `onReadyToListen` (fires once after first AVATAR_SPEAK_ENDED + delay) to set `voiceReady`, which then triggers `connect()` in VoiceButton.

5. **`voiceChat: false` is mandatory** — setting `voiceChat: true` hands mic control to HeyGen and breaks our AudioWorklet pipeline.

6. **Don't auto-reconnect Deepgram WebSocket** — auto-reconnect on `ws.onclose` caused audio glitches. Let it close cleanly; the user can tap the button to reconnect.

7. **Conductor timeout is 30s** — was 5s and silently killed every agent (web search takes 8–15s). Don't lower it.

8. **All agent tool-call loops use `claude-haiku-4-5`** — only the conductor merge step uses Sonnet. Don't switch agents to Sonnet; costs ~20x more.

9. **intent extraction uses ` ```json ``` ` triple-backtick pattern** — not a custom `JSONBLOCK` marker. Pattern: `` r'```json\s*(.*?)\s*```' `` with `re.DOTALL`.

10. **`pcm-capture.js` must exist in `frontend/public/`** — VoiceButton loads it via `ctx.audioWorklet.addModule('/pcm-capture.js')`. It is already there. Do not delete it.

11. **Auth was fully removed from the Next.js app** — no login, no Supabase auth on the frontend. The demo runs as a hardcoded `DEMO_USER`. Don't add auth back without a specific product decision.
