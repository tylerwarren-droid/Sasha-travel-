# Session State — 07/11/2026, 10:39 PM

_Auto-captured by Claude Thread_

## Summary
This capture session was a trivial test ('doing a test' / 'toast test 2') with no substantive work performed. The real project state carries over from Session #2, which focused on editing the Kanoe investor presentation (frontend/public/sasha_investor.html) and left two outstanding requests unfinished: removing the $1M fundraising boxes from both the Teaser and Investor Deck tabs, and designing an 'API Hub' architecture concept. The assistant was cut off mid-search for the $1M boxes.

# ════════════════════════════════════════════════════════════
# SASHA / KANOE — AI TRAVEL CONCIERGE — THREAD CONTEXT
# The single source of truth. Read this completely before doing anything.
# Generated: 2026-07-11 · Model: Sonnet · Session #3 · ~0 tokens
# ════════════════════════════════════════════════════════════

## ⚡ READ THIS FIRST — 30 SECOND ORIENTATION
Kanoe is a multi-agent AI travel platform whose voice concierge "Sasha" runs on a HeyGen LiveAvatar with a self-owned Deepgram STT mic pipeline and 23 backend specialist agents. The current active work is NOT the voice pipeline — it is editing the investor presentation at frontend/public/sasha_investor.html. Two requests remain unfinished from the prior real session: remove the $1M fundraising boxes from BOTH the Teaser tab and the Investor Deck tab, and design/add an "API Hub" architecture concept — the assistant was cut off mid-search for the $1M boxes (this current chat was only a throwaway 'toast test' with no real work).

> NEXT ACTION: Open frontend/public/sasha_investor.html and run `grep -n "1 million\|1M\|\$1,000,000\|raise\|Use of Proceeds\|fundraising" frontend/public/sasha_investor.html` to locate BOTH $1M fundraising boxes — one in the Teaser tab and one in the Investor Deck tab. Delete both box elements entirely (funding info will be shared separately). Produce the updated file, give the user a Download link, and provide this exact command: `cp ~/Downloads/sasha_investor.html ~/Projects/sasha-travel/frontend/public/sasha_investor.html && git -C ~/Projects/sasha-travel add . && git -C ~/Projects/sasha-travel commit -m "Remove \$1M fundraising boxes from Teaser + Investor Deck tabs" && git -C ~/Projects/sasha-travel push origin main`. Verify by re-grepping the saved file to confirm zero remaining $1M box references.
> DO NOT: Do not deliver a file via /mnt/user-data/outputs and tell the user to `cp` from there — that path is NOT accessible from their terminal (it failed last session); always give them the Download link + a `cp ~/Downloads/...` command. Also do NOT re-add the Agent Architecture and Token Optimisation content as standalone investor-deck slides — the user explicitly rejected that; it now lives as ONE combined 'Performance Architecture' slide (tdm-s11) inside the TDM deck.

# ─────────────────────────────────────────────────────────────
# PART 1 — WHAT THIS IS (the unchanging core)
# ─────────────────────────────────────────────────────────────

## THE ESSENCE — never let this drift
Kanoe is a multi-agent AI travel concierge platform. The one thing it must always do well: deliver a natural, low-latency VOICE conversation with an on-screen video avatar (Sasha) that dispatches user requests to 23 specialist agents (golf, visa, restaurants, transfers, etc.) and speaks answers back through the HeyGen avatar. The crown jewel and most fragile part is the voice pipeline: HeyGen LiveAvatar (video + TTS, `voiceChat: false` so WE own the mic) → Deepgram nova-3 AudioWorklet STT → conductor → response → avatar.repeat(). Any change that degrades turn-taking, echo suppression, or gate/barge-in behavior compromises the essence and must be rejected. Secondary but active right now: the investor-facing presentation (sasha_investor.html) that pitches this to funders.

## WHO IT'S FOR
Repo owner/developer is tylerwarren-droid (terminal prompt: tylerwarren@Mac-mini-van-Tyler, project at ~/Projects/sasha-travel). End users are luxury/high-end travelers using demos like /vietnam and /phuquoc. There is a live investor-facing track (investor.kanoe.ai → sasha_investor.html) — polish and reliability matter for fundraising. HeyGen is currently reviewing the repo (made public for that review). Technical level: developer-competent, works from a Mac Mini, runs git manually, downloads files from Claude's chat rather than accessing container paths. He has clear opinions on slide placement and will redirect content he doesn't like.

# ─────────────────────────────────────────────────────────────
# PART 2 — WHAT'S TRUE RIGHT NOW (the current reality)
# ─────────────────────────────────────────────────────────────

## CURRENT STATE — what actually exists vs what's aspirational
- WORKING NOW (verified): Live URLs deployed — investor.kanoe.ai, demo.kanoe.ai, sasha-heygen.vercel.app/vietnam, sasha-heygen.vercel.app/phuquoc, backend at sasha-travel-production.up.railway.app. Voice pipeline documented as functioning (tap-to-start → HeyGen avatar → Deepgram STT → conductor → avatar.repeat, with echo filtering, dedup, gate/barge-in). 23 backend agent service modules exist (backend/app/services/*_agent.py). DB writes wired. The investor presentation sasha_investor.html has a Teaser tab, an Investor Deck tab, and a TDM deck (now 11 slides).
- BUILT BUT UNVERIFIED: The 'Performance Architecture' slide (tdm-s11) added in Session #2 — combines agent orchestration flow (left) + three-level intelligence model & LLM routing cost table (right). Written and delivered but NOT confirmed deployed/reviewed live by the user. The /vietnam2 Luxurious Traveler UI with Leaflet map (commits 6461b4c/990f01f). Onboarding flow (frontend/app/onboarding, 6 steps). An uncommitted asset exists: `frontend/public/slides/Kanoe_Investor_Deck_May 2026 7.key`.
- ASPIRATIONAL / NOT BUILT: The 'API Hub' architecture — the user asked to design a concept where system APIs coordinate with the agents; this has NOT been designed or built. This current Session #3 chat was only a throwaway test ('doing a test' → 'toast test 2') and produced no work.

## LAST SESSION — what just happened
- We worked on: Nothing substantive — this capture ('Session #3') was a test message pair only ('doing a test' / 'toast test 2'). The last REAL work was Session #2 on the investor presentation.
- We completed: In Session #2 — merged the Agent Architecture + Token Optimisation content into ONE 'Performance Architecture' slide (tdm-s11) inside the TDM deck, after the user rejected them as standalone investor-deck slides.
- We changed: frontend/public/sasha_investor.html (tdm-s11 added). Recent auto-commits are just session_current.md updates; last real content commit was 26b27bf (MOR corpus verbiage + Data Licensing pillar update).
- We left off mid-: Searching sasha_investor.html for the two $1M fundraising boxes to delete them — the assistant was cut off before locating/removing them. The API Hub design was never started.

## OPEN TASKS — ranked, with the WHY
1. Remove the $1M fundraising boxes from BOTH the Teaser tab and the Investor Deck tab in sasha_investor.html — matters because the user wants funding figures shared separately, not baked into the public investor deck (repo is public for HeyGen review) — constraint: deliver via Download link + `cp ~/Downloads/...` command, never /mnt/user-data/outputs.
2. Design and add the 'API Hub' architecture concept — matters because the user wants to show how system APIs coordinate with the 23 agents (strengthens the technical investor story) — constraint: do not create standalone investor-deck slides for architecture content unless the user explicitly asks; prior architecture content was directed into the TDM deck.
3. Confirm the tdm-s11 'Performance Architecture' slide renders correctly live at investor.kanoe.ai — matters because it was delivered but never verified deployed.

# ─────────────────────────────────────────────────────────────
# PART 3 — THE GUARDRAILS (what stops drift and repetition)
# ─────────────────────────────────────────────────────────────

## ✋ DO NOT TOUCH — load-bearing, deliberate, leave alone
- HeyGen LiveAvatar `voiceChat: false` setting — looks like a disabled feature but is deliberately off because WE own the mic pipeline (Deepgram nova-3 AudioWorklet STT). Turning it on would double-capture audio and destroy turn-taking. Do not change.
- The voice pipeline echo filtering / dedup / gate / barge-in logic (frontend/app/components/VoiceButton.tsx, SashaAvatar.tsx; backend voice_conductor.py) — looks like it could be simplified but each piece prevents Sasha from hearing herself or talking over the user. Do not refactor.
- tdm-s11 'Performance Architecture' slide placement inside the TDM deck — looks like it belongs in the Investor Deck, but the user explicitly placed it in the TDM deck. Leave it there.

## 🚫 ALREADY DECIDED — do not re-open these
| Decision | Why we chose it | What we rejected | Reversible? |
|----------|-----------------|------------------|-------------|
| Agent Architecture + Token Optimisation → ONE 'Performance Architecture' slide (tdm-s11) in the TDM deck | User wanted them combined and in the technical deck, not the investor deck | Two standalone Investor Deck slides | No |
| $1M fundraising figures shared separately, not in the public deck | Repo is public for HeyGen review; funding info kept out | Keeping the $1M boxes in Teaser + Investor Deck | No |
| We own the mic (Deepgram STT), HeyGen for video+TTS only | Full control of turn-taking / barge-in | Using HeyGen's built-in voiceChat | No |

## 💀 TRIED AND FAILED — do not suggest these again
- Delivering files via /mnt/user-data/outputs and telling the user to `cp` from that path — failed because that container path is NOT accessible from the user's Mac terminal. Always provide a Download link + a `cp ~/Downloads/...` command instead.

## 🧭 USER'S STANDING PREFERENCES — how they want things done
- Deliver edited files as a Download link plus an exact `cp ~/Downloads/... && git add/commit/push` command he can paste into his Mac terminal.
- He runs git manually from ~/Projects/sasha-travel; provide full `git -C ~/Projects/sasha-travel ...` commands.
- He has strong opinions on slide/content placement and will redirect content he dislikes — follow his placement decisions exactly.
- Verify changes with a re-grep / concrete check after editing.

# ─────────────────────────────────────────────────────────────
# PART 4 — THE MAP (how it's all put together)
# ─────────────────────────────────────────────────────────────

## ARCHITECTURE / STRUCTURE
- frontend/public/sasha_investor.html — the investor presentation (Teaser tab, Investor Deck tab, TDM deck of 11 slides). SAFE to modify — this is the active work surface. Load-bearing for fundraising.
- frontend/app/components/VoiceButton.tsx / SashaAvatar.tsx / SashaChat.tsx — the voice UI + mic pipeline. LOAD-BEARING, do not casually modify.
- frontend/app/api/heygen/token/route.ts + token/phuquoc/route.ts — HeyGen token issuance. Load-bearing.
- frontend/public/pcm-capture.js — the AudioWorklet PCM capture for Deepgram STT. Load-bearing, do not touch.
- backend/app/services/*_agent.py — the 23 specialist agents (golf, visa, restaurant, transfer, etc.). Modify with care.
- backend/app/services/conductor.py + backend/app/api/voice_conductor.py — the conductor that routes requests to agents. Load-bearing.
- backend/app/services/deepgram_service.py — Deepgram STT integration. Load-bearing.
- frontend/app/vietnam/page.tsx, /phuquoc/page.tsx, /vietnam2/page.tsx + MapPanel.tsx — demo UIs. Safe to modify.
- frontend/app/onboarding/* — 6-step onboarding flow. Safe to modify.

## KEY FILES / ARTIFACTS / LINKS
- frontend/public/sasha_investor.html — active investor deck; touch it for the $1M-box removal and any API Hub content.
- docs/session_current.md — current session state (regenerate with scripts/end_session.sh).
- docs/new_chat_handoff.md — full architectural reference.
- docs/agents.md — all 23 agents: triggers, capabilities, tools.
- docs/data_model.md — full database schema spec.
- docs/session_june12_2026.md — session log for June 12 2026.
- frontend/public/slides/Kanoe_Investor_Deck_May 2026 7.key — uncommitted Keynote asset (decide whether to commit or ignore).

## DEPENDENCIES & CONNECTIONS
- Frontend (Next.js/React 19/TS/Tailwind) on Vercel (project sasha-heygen) → Backend (FastAPI) on Railway (sasha-travel-production.up.railway.app) → Supabase Postgres w/ RLS (xlqtveusyfpffaejegiq.supabase.co).
- Voice: HeyGen LiveAvatar SDK (video+TTS) + Deepgram nova-3 (STT) — both external, both required for the core experience.
- AI: Anthropic Claude (Opus/Sonnet for conductor, Haiku for agent tool loops).
- Domains: investor.kanoe.ai and demo.kanoe.ai redirect into the Vercel deployment (see redirect commits ad49a8b, 85d7de5).

# ─────────────────────────────────────────────────────────────
# PART 5 — THE HUMAN CONTEXT (the WHY behind it all)
# ─────────────────────────────────────────────────────────────

## PEOPLE
- tylerwarren-droid (Tyler) — repo owner/developer, works from a Mac Mini (~/Projects/sasha-travel). Wants clean deliverables via Download + git commands; decisive about content placement.
- HeyGen (company) — currently reviewing the repo (made public for the review); investor deck polish and clean public content matter here.
- Investors/funders — audience for investor.kanoe.ai; reason the $1M boxes are being removed and the technical story (Performance Architecture / API Hub) is being strengthened.

## STRATEGIC CONTEXT — the bigger picture
Kanoe is in active fundraising mode. The investor presentation (sasha_investor.html) is a live pitch surface at investor.kanoe.ai, and the repo is public specifically for HeyGen's review — so both the public presentation content and the codebase's cleanliness carry weight. The immediate priority is polishing that investor deck (remove the $1M boxes, add the API Hub concept) so the technical and business story lands with funders. The voice pipeline is the actual product crown jewel and must never regress while presentation work proceeds. Success right now = a clean, compelling investor deck and a stable demo, without breaking the voice experience.

## BLOCKERS & OPEN QUESTIONS
- API Hub design — the user asked for it but hasn't specified exactly how the system APIs should coordinate with agents or where it should live (likely TDM deck given prior placement decisions) — needs a proposed design before building.
- Uncommitted file `frontend/public/slides/Kanoe_Investor_Deck_May 2026 7.key` — open question whether to commit, ignore, or delete.
- tdm-s11 'Performance Architecture' slide not confirmed live — need the user to verify or a deploy check.

# ─────────────────────────────────────────────────────────────
# PART 6 — THE HANDOFF (verbatim instructions to the next Claude)
# ─────────────────────────────────────────────────────────────

## 📋 VERBATIM BRIEFING — read this as if I'm speaking directly to you
"You are continuing work on Sasha / Kanoe, an AI travel concierge platform. Here is what you must understand:

The core of this project is a natural, low-latency VOICE conversation with an on-screen HeyGen video avatar (Sasha) that routes requests to 23 specialist agents and speaks answers back — the voice pipeline (HeyGen LiveAvatar with voiceChat:false + our own Deepgram nova-3 AudioWorklet STT + conductor) is the crown jewel — protect it.

Right now, the active work is NOT the voice pipeline — it's the investor presentation at frontend/public/sasha_investor.html. The last REAL thing that happened (Session #2) was merging Agent Architecture + Token Optimisation into a single 'Performance Architecture' slide (tdm-s11) in the TDM deck; this current chat was just a throwaway 'toast test' with no work.

Your first action is to open frontend/public/sasha_investor.html, grep for the two $1M fundraising boxes (one in the Teaser tab, one in the Investor Deck tab), delete both, and deliver the file as a Download link plus a `cp ~/Downloads/... && git add/commit/push` command — then verify by re-grepping.

Before you do anything, know that the repo is PUBLIC for HeyGen's review and Kanoe is actively fundraising — public content cleanliness matters.

Do not deliver files via /mnt/user-data/outputs and tell him to `cp` from there — that path is inaccessible from his Mac terminal and it failed before; always use a Download link + `cp ~/Downloads/...`. And do not re-add the architecture content as standalone investor-deck slides — he rejected that; it lives in the TDM deck as tdm-s11.

The user is Tyler (tylerwarren-droid), a developer working from a Mac Mini who runs git manually and has strong, decisive opinions on content placement, and he values clean, paste-ready deliverables. When in doubt, optimize for a polished investor deck and a rock-stable voice demo.

If you're about to touch the voice pipeline components (VoiceButton.tsx, SashaAvatar.tsx, pcm-capture.js, voice_conductor.py) or flip voiceChat to true, stop — that's the drift we're preventing."

# ════════════════════════════════════════════════════════════
# END OF CONTEXT. You now know everything the last session knew.
# Do not ask the user to re-explain any of the above.
# ════════════════════════════════════════════════════════════

# DOMAIN 1: SOFTWARE / ENGINEERING

## BUILD / RUN / TEST
- Frontend: Next.js App Router (React 19, TypeScript, Tailwind), deployed on Vercel (project sasha-heygen). Local dev: `cd frontend && npm install && npm run dev`.
- Backend: FastAPI on Railway (sasha-travel-production.up.railway.app). See backend/Procfile, backend/requirements.txt, backend/runtime.txt.
- DB migrations: backend/migrations/*.sql via backend/run_migration.py.
- Session regeneration: `ANTHROPIC_API_KEY=your_key ./scripts/end_session.sh` (calls Claude via API, auto-commits session_current.md).
- New-chat bootstrap: paste into Claude — "Read docs/session_current.md and the files it references in https://github.com/tylerwarren-droid/Sasha-travel- then pick up where we left off."

## ENV / SECRETS
- ANTHROPIC_API_KEY (Claude — conductor Opus/Sonnet, agent loops Haiku).
- HeyGen API key/token (issued via frontend/app/api/heygen/token/route.ts).
- Deepgram API key (nova-3 STT).
- Supabase URL/keys (xlqtveusyfpffaejegiq.supabase.co, RLS enabled).

## DEPLOY
- Frontend auto-deploys from main to Vercel (sasha-heygen). Domains investor.kanoe.ai + demo.kanoe.ai redirect in.
- Backend on Railway (railway.json / Procfile).
- Standard flow after edits: `cp ~/Downloads/<file> ~/Projects/sasha-travel/<path> && git -C ~/Projects/sasha-travel add . && git -C ~/Projects/sasha-travel commit -m "..." && git -C ~/Projects/sasha-travel push origin main`.

## GOTCHAS
- /mnt/user-data/outputs is NOT reachable from the user's terminal — use Download links.
- Do not set HeyGen voiceChat:true — it breaks the owned mic pipeline.
- node_modules is tracked/large in the repo listing; don't get lost in it — real source is under frontend/app, frontend/public, backend/app.
---
_Generated: 2026-07-11T20:39:20.252Z
