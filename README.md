# Sasha / Kanoe — AI Travel Concierge

## Starting a new chat

Paste this exact line into Claude:

```
Read docs/session_current.md and the files it references in https://github.com/tylerwarren-droid/Sasha-travel- then pick up where we left off.
```

To regenerate `session_current.md` at the end of a session (calls Claude via API and auto-commits):

```bash
ANTHROPIC_API_KEY=your_key ./scripts/end_session.sh
```

---

## What this is

Kanoe is a multi-agent AI travel platform. The AI concierge is called Sasha. She runs on a HeyGen LiveAvatar (video), speaks via the HeyGen TTS, and listens via a Deepgram AudioWorklet STT pipeline. Behind the scenes, 23 specialist agents handle everything from golf bookings to visa requirements to restaurant reservations.

## Stack

- **Frontend:** Next.js App Router, React 19, TypeScript, Tailwind — Vercel (sasha-heygen project)
- **Backend:** FastAPI — Railway (`sasha-travel-production.up.railway.app`)
- **Database:** Supabase Postgres with RLS (`xlqtveusyfpffaejegiq.supabase.co`)
- **AI:** Anthropic Claude (Opus/Sonnet for conductor, Haiku for agent tool loops)
- **Avatar:** HeyGen LiveAvatar SDK (`voiceChat: false` — we own the mic pipeline)
- **STT:** Deepgram nova-3 streaming via AudioWorklet PCM

## Key docs

- `docs/session_current.md` — current session state (regenerate with `end_session.sh`)
- `docs/new_chat_handoff.md` — full architectural reference
- `docs/agents.md` — all 23 agents: triggers, capabilities, tools
- `docs/data_model.md` — full database schema spec
- `docs/session_june12_2026.md` — session log June 12 2026

## Live URLs

| | URL |
|--|-----|
| Investor portal | investor.kanoe.ai |
| Demo | demo.kanoe.ai |
| Vietnam demo | sasha-heygen.vercel.app/vietnam |
| Phu Quoc demo | sasha-heygen.vercel.app/phuquoc |
| Backend API | sasha-travel-production.up.railway.app |
