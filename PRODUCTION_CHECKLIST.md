# Sasha / Discover Vietnam — Production Deploy Checklist

This covers shipping the LiveAvatar fixes (async backend, brevity, echo/barge-in/turn-machine
fixes) to production. The local code is feature-complete and verified; these are the
deploy/config/security steps.

---

## 1. Backend → Railway (DO THIS FIRST)

The deployed Railway backend still runs the **old blocking code** that caused
"sometimes doesn't respond." It must be redeployed with the now-async services.

### 1a. Required environment variables (Railway → Variables)
| Var | Required | Notes |
|-----|----------|-------|
| `ANTHROPIC_API_KEY` | ✅ yes | the conductor/agents call Claude |
| `SUPABASE_URL` | if using DB prompts/tenant | else static prompts are used |
| `SUPABASE_SERVICE_KEY` | if using DB prompts/tenant | |
| `ALLOWED_ORIGINS` | recommended | comma-separated extra CORS origins, e.g. `https://discover-vietnam.vercel.app,https://demo.kanoe.ai` — must include the prod frontend domain or every conductor call is CORS-blocked |
| `RESEND_API_KEY` | optional | golf/restaurant/hotel email tools |
| `BLAND_API_KEY` | optional | AI phone-call tools |

### 1b. Deploy
Start command is already correct in `backend/railway.json`:
`uvicorn app.main:app --host 0.0.0.0 --port $PORT`

- If Railway is connected to a GitHub repo: commit + push the `backend/` changes.
- If deploying from the CLI: `cd backend && railway up`

(Optional, for higher load: add `--workers 2` to the start command. The async fix already
makes one worker handle concurrency without blocking.)

### 1c. Verify after deploy
```
curl https://sasha-travel-production.up.railway.app/health
curl -X POST https://sasha-travel-production.up.railway.app/api/agents/conductor \
  -H "Content-Type: application/json" \
  -d '{"message":"When is the best time to visit Vietnam?","conversation_history":[]}'
```
The response should be **1-2 short sentences** (not a 1400-char wall) and return quickly.

---

## 2. Supabase prompts (IMPORTANT — overrides the code)

Prod loads `conductor.general` and `conductor.merge` from the Supabase `prompt_versions`
table, which **override** the brevity edits in `prompts.py`. The per-agent `VOICE_BREVITY`
always applies, but you must update these two rows or general replies will be long again.

Update (or insert a new active version of) these two `prompt_name` rows with this exact text:

**`conductor.general`:**
```
You are Sasha, a warm, knowledgeable AI travel concierge specialising in Vietnam. This is a REAL-TIME VOICE conversation, so keep EVERY reply to one or two short spoken sentences — never longer. Be warm and natural, ask only ONE question at a time, and never use lists, bullet points, headings, or numbered steps. If the user wants detail, give a little and invite them to ask for more.
```

**`conductor.merge`:**
```
You are Sasha, a warm AI travel concierge on a REAL-TIME VOICE call. Synthesize the specialist responses into ONE natural reply of at most TWO short spoken sentences. Never mention "agents" or "specialists", never use lists or bullet points — just speak as Sasha, and ask only one question at a time.
```

(If you do NOT use Supabase for prompts, skip this — the static versions in
`backend/app/services/prompts.py` already contain the same text.)

---

## 3. Frontend → Vercel

`.env.local` is local-only (gitignored) and does NOT deploy. Set these in the Vercel
project (Settings → Environment Variables):

| Var | Value |
|-----|-------|
| `NEXT_PUBLIC_API_URL` | `https://sasha-travel-production.up.railway.app` |
| `HEYGEN_API_KEY` | your LiveAvatar key (server-side, used by `/api/heygen/token`) |
| `NEXT_PUBLIC_DEEPGRAM_API_KEY` | your Deepgram key (⚠️ see §4) |
| `NEXT_PUBLIC_SUPABASE_URL` | for the login page |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | for the login page |

Then redeploy the frontend. Confirm `/vietnam` loads, the avatar greets, and a couple of
voice turns work end to end against the prod backend.

---

## 4. ⚠️ Security follow-up — proxy the Deepgram key

`NEXT_PUBLIC_DEEPGRAM_API_KEY` is exposed in the browser; anyone can lift and abuse it.
For production, mint short-lived Deepgram keys server-side instead:

- Add a backend endpoint that calls Deepgram's `POST /v1/projects/{id}/keys` with a short
  TTL and `scopes: ["usage:write"]`, returning the temp key.
- Have `VoiceButton` fetch that temp key instead of reading `NEXT_PUBLIC_DEEPGRAM_API_KEY`.

(Not done yet — ask and I'll implement it. It's the one remaining security gap.)

---

## What was fixed (reference)
- Backend: all 11 services converted to `AsyncAnthropic` + `await` (was blocking the event
  loop → intermittent "no response"); conductor timeouts 5s→20s + merge fallback; CORS
  env-extensible; brevity on general/merge + per-agent `VOICE_BREVITY`.
- Frontend: turn state machine rewritten (no segment-counting wedge) + watchdogs; single
  session (StrictMode off); Deepgram auto-reconnect; single-flight conductor guard +
  30s axios timeout + never-silent fallback; echo filter time-boxed to a 1.5s window
  (fixed "stopped hearing me"); markdown rendered in chat + stripped from speech;
  barge-in tuned to 0.07 RMS / 30 frames (validated on speakers: bleed ≤0.03, voice ≥0.095);
  End Session button; avatar framing; keepAlive/stop async rejections caught.

## Optional / known
- Models are `claude-sonnet-4-5` (a generation old) — can bump to `claude-sonnet-4-6`.
- Reconnect doesn't cap retries on permanent failures (out-of-credits / avatar-deleted).
- Green-screen avatar background is cosmetic.
- `reactStrictMode: false` (next.config.ts) — only affects dev double-mount; harmless in prod.
