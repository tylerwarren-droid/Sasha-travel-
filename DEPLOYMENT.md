# Sasha Travel — Deployment & Operations Runbook

Covers running, configuring, and deploying the **application**. The live cloud/region
migration (Railway → Hetzner, Supabase → EU) is intentionally **not performed** here — it's
a checklist at the bottom for whoever runs it with the cloud credentials.

---

## 1. Architecture

```
Browser ──▶ Next.js (Vercel)            ──▶ /api/heygen/token  ──▶ LiveAvatar (avatar)
   │            │                                                    (FULL mode, repeat())
   │            └─ Deepgram STT (ephemeral key from backend) ───────▶ Deepgram
   │
   └─ POST /api/agents/conductor ──▶ FastAPI (Railway) ──▶ Claude (Haiku conductor + Sonnet specialists)
                                          └─ /api/payments/* ──▶ Stripe Checkout
```

Per-turn latency path: Deepgram STT (client) → Conductor HTTP → keyword classify → parallel
agents → optional merge → text → `avatar.repeat()` → LiveAvatar TTS.

---

## 2. Configuration

Backend vars: see [`backend/.env.example`](backend/.env.example).
Frontend vars: see [`frontend/.env.example`](frontend/.env.example).

**The two that must agree:** if you enable the auth gate, set `CONDUCTOR_API_SECRET` (backend)
and `NEXT_PUBLIC_CLIENT_KEY` (frontend) to the **same** value, or every conductor call 401s.

---

## 3. Run locally

```bash
# Backend
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # fill ANTHROPIC_API_KEY at minimum
uvicorn app.main:app --reload --port 8000

# Frontend (separate shell)
cd frontend
npm install
cp .env.example .env.local    # set NEXT_PUBLIC_API_URL=http://localhost:8000
npm run dev                   # http://localhost:3000/vietnam
```

## 4. Run the backend in Docker (host-agnostic)

```bash
cd backend
docker build -t sasha-backend .
docker run -p 8000:8000 --env-file .env sasha-backend
```

---

## 5. Feature setup

### Stripe payments
1. Set `STRIPE_SECRET_KEY` (test: `sk_test_…`), `STRIPE_SUCCESS_URL`, `STRIPE_CANCEL_URL`.
2. Create a webhook endpoint → `https://<backend>/api/payments/webhook`, subscribe to
   `checkout.session.completed`, copy its signing secret into `STRIPE_WEBHOOK_SECRET`.
   Local: `stripe listen --forward-to localhost:8000/api/payments/webhook`.
3. Until keys are set the endpoints return **501** and the UI shows "payments not configured"
   — the demo never crashes.

### Deepgram ephemeral STT keys (removes the exposed browser key)
1. Set `DEEPGRAM_API_KEY` (master) **and** `DEEPGRAM_PROJECT_ID` on the backend.
2. The browser then mints a short-lived `usage:write` key per session via
   `/api/voice/deepgram-key`; you can leave `NEXT_PUBLIC_DEEPGRAM_API_KEY` blank in prod.
3. If unset, the backend returns 501 and the browser falls back to the public env key (dev).

### Rate limiting / cost guard
- `RATE_LIMIT_RPM` (default 30/IP/min), `CONDUCTOR_API_SECRET` (+ `NEXT_PUBLIC_CLIENT_KEY`),
  `DAILY_REQUEST_CAP` + `COST_ALERT_WEBHOOK`. In-memory — correct for a single instance.
  For multiple workers/VMs, back the bucket with Redis (swap `_buckets` in
  `app/middleware/ratelimit.py`).

---

## 6. Latency knobs (the main goal)

| Lever | Where | Effect |
|-------|-------|--------|
| Cold-start mask | `SashaAvatar` "Waking Sasha up…" | hides the ~4s LiveAvatar allocation |
| Backend warm-up | frontend fires `/api/agents/warmup` on load | first turn isn't cold |
| Supabase off hot path | `prompts.py` fire-and-forget refresh | no DB wait mid-conversation |
| Haiku conductor | `FAST_MODEL` | fast time-to-first-audio |
| History trim | `CONDUCTOR_MAX_HISTORY` | shorter prompt = lower TTFT |
| Shared LLM client | `services/llm.py` | one connection pool, fewer handshakes |

The **biggest remaining latency win is geographic** (backend + DB co-located with the
kiosk) — that's the deferred migration below; it needs cloud credentials.

---

## 7. DEFERRED — region migration & infra (NOT done here; needs cloud accounts)

> Out of scope per instruction. Listed so it can be executed later. None of the app code
> hardcodes a region — `NEXT_PUBLIC_API_URL` + DB env move everything.

- [ ] **Backend → Hetzner Helsinki VM** (or Fly.io/Cloud Run EU). Build the image
      (`backend/Dockerfile`), run behind Caddy (auto-TLS) or the host's TLS, set env, point
      `NEXT_PUBLIC_API_URL` at the new host. EU co-location is the real latency win for an
      EU/Finland kiosk.
- [ ] **Supabase → EU region (Frankfurt)** or co-locate Postgres on the VM. Keep all DB
      writes async/fire-and-forget (already true for prompts).
- [ ] **CI/CD** to the chosen host + a staging env (version control is now in place).
- [ ] **Uptime/alerting** — point a monitor at `GET /health`; wire `COST_ALERT_WEBHOOK` for
      cost spikes.
- [ ] **GDPR** for the EU voice kiosk — consent + data-handling review.
