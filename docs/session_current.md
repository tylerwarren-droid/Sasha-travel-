# Session State — 07/12/2026, 08:19 AM

_Auto-captured by Claude Thread_

## Summary
This session was largely a 'test' capture, but the substantive in-flight work is editing the investor presentation at frontend/public/sasha_investor.html. Tyler made two requests: (1) remove four $1M fundraising boxes from the Teaser and Investor Deck tabs (already located via grep at lines ~306, ~319, ~339–346, ~419–420), and (2) design a new 'API Hub' architecture slide where system APIs coordinate with the 23 agents. The assistant was cut off mid-grep while locating the $1M boxes; earlier the agent-architecture + token-optimization content was consolidated into one 'Performance Architecture' slide (tdm-s11) inside the TDM deck after Tyler rejected standalone Investor-Deck slides.

# ════════════════════════════════════════════════════════════
# SASHA / KANOE — AI TRAVEL CONCIERGE — THREAD CONTEXT
# The single source of truth. Read this completely before doing anything.
# Generated: 2026-07-12 · Model: Sonnet · Session #4 · ~2180 tokens
# ════════════════════════════════════════════════════════════

## ⚡ READ THIS FIRST — 30 SECOND ORIENTATION
Kanoe is a multi-agent AI travel platform whose voice concierge "Sasha" runs on a HeyGen LiveAvatar with a self-owned Deepgram STT mic pipeline and 23 backend specialist agents. The active work right now is NOT the voice pipeline — it is editing the investor presentation at frontend/public/sasha_investor.html. Two requests remain unfinished: (1) remove the four $1M fundraising boxes from BOTH the Teaser tab and the Investor Deck tab (already located via grep), and (2) design/add an "API Hub" architecture concept slide where system APIs coordinate with the agents.

> NEXT ACTION: Read frontend/public/sasha_investor.html from the project knowledge FIRST (Tyler already dragged it into the project space — do NOT ask him to re-attach; he responds in ALL CAPS when asked to re-drag). Then delete these four CONFIRMED $1M elements: (a) Teaser line ~306 `<div class="t-eyebrow">Pre-Seed · $1M · 2026</div>`, (b) Teaser line ~319 `<div class="stat"><div class="stat-n">$1M</div><div class="stat-l">Pre-Seed Target</div></div>`, (c) Investor Deck lines ~339–346 the entire `<div class="ask-box">` block with the $1.0M breakdown, (d) Onboarding lines ~419–420 the $1.0M Pre-Seed header block. Delete all four entirely (Tyler shares funding info separately). Provide a Download link + this EXACT command: `cp ~/Downloads/sasha_investor.html ~/Projects/sasha-travel/frontend/public/sasha_investor.html && git -C ~/Projects/sasha-travel add . && git -C ~/Projects/sasha-travel commit -m "Remove \$1M fundraising boxes from Teaser + Investor Deck tabs" && git -C ~/Projects/sasha-travel push origin main`. Verify by re-grepping the saved output for `1M\|1 million\|ask-box\|Pre-Seed Target` and confirming ZERO matches. THEN start task 2: design the 'API Hub' architecture slide.
> DO NOT: Do NOT deliver the file via /mnt/user-data/outputs and tell Tyler to `cp` from there — that path is NOT accessible from his terminal (it failed with "No such file or directory"). ALWAYS give a Download link + a `cp ~/Downloads/...` command. Also do NOT re-add Agent Architecture / Token Optimisation as standalone Investor-Deck slides — Tyler rejected that placement; it now lives as ONE combined 'Performance Architecture' slide (tdm-s11) inside the TDM deck.

# ─────────────────────────────────────────────────────────────
# PART 1 — WHAT THIS IS (the unchanging core)
# ─────────────────────────────────────────────────────────────

## THE ESSENCE — never let this drift
Kanoe is a multi-agent AI travel concierge platform. The one thing it must always do well: deliver a natural, low-latency VOICE conversation with an on-screen video avatar (Sasha) that dispatches user requests to 23 specialist agents (golf, visa, restaurants, transfers, etc.) and speaks answers back through the HeyGen avatar. The crown jewel and most fragile part is the voice pipeline: HeyGen LiveAvatar (video + TTS, `voiceChat: false` so WE own the mic) → Deepgram nova-3 AudioWorklet STT → conductor → response → avatar. Any change that degrades turn-taking, echo suppression, or gate/barge-in behavior compromises the essence and must be rejected. Secondary but active right now: the investor-facing presentation (sasha_investor.html) that pitches this to funders.

## WHO IT'S FOR
Repo owner/developer is Tyler (GitHub tylerwarren-droid; terminal prompt tylerwarren@Mac-mini-van-Tyler; project at ~/Projects/sasha-travel). End users are luxury/high-end travelers using demos like /vietnam and /phuquoc. There is a live investor-facing track (investor.kanoe.ai → sasha_investor.html) — polish and reliability matter for fundraising. HeyGen is currently reviewing the repo (made public for that review). Technical level: developer-competent, works from a Mac Mini, runs git manually, downloads files from Claude's chat rather than accessing container paths. He has clear opinions on slide placement and will redirect content he doesn't like. He gets frustrated (in ALL CAPS) when asked to re-drag/re-upload files he's already provided in the project space — read from project knowledge first.

# ─────────────────────────────────────────────────────────────
# PART 2 — WHAT'S TRUE RIGHT NOW (the current reality)
# ─────────────────────────────────────────────────────────────

## CURRENT STATE — what actually exists vs what's aspirational
- WORKING NOW (verified): Live URLs deployed — investor.kanoe.ai (→ /sasha_investor.html), demo.kanoe.ai, sasha-heygen.vercel.app/vietnam, sasha-heygen.vercel.app/phuquoc, backend at sasha-travel-production.up.railway.app. Supabase Postgres with RLS live (xlqtveusyfpffaejegiq.supabase.co). Investor deck sasha_investor.html renders with Teaser / Investor Deck / TDM / Onboarding tabs. TDM deck has 11 slides including newly added 'Performance Architecture' (tdm-s11).
- BUILT BUT UNVERIFIED: The tdm-s11 'Performance Architecture' slide (agent orchestration flow + three-level intelligence model + LLM routing cost table) was injected and delivered as a Download but has NOT been confirmed deployed/pushed by Tyler this session. The two standalone Investor-Deck slides (Agent Architecture, Token Optimisation) were built earlier then explicitly RELOCATED into tdm-s11 — do not assume the standalone versions still exist.
- ASPIRATIONAL / NOT BUILT: The 'API Hub' architecture slide (system APIs coordinating amongst themselves and with the 23 agents) — requested by Tyler, not yet designed. Removal of the four $1M fundraising boxes — located via grep but NOT yet executed/committed.

## LAST SESSION — what just happened
- We worked on: editing frontend/public/sasha_investor.html — relocating technical slides and preparing to remove $1M boxes.
- We completed: consolidated Agent Architecture + Token Optimisation into ONE new 'Performance Architecture' slide (tdm-s11) in the TDM deck and updated the nav counter; delivered file via Download link.
- We changed: sasha_investor.html (added tdm-s11, removed the two standalone Investor-Deck slides that had been added earlier). Note: an uncommitted stray file exists in repo: `frontend/public/slides/Kanoe_Investor_Deck_May 2026 7.key` (untracked).
- We left off mid-: grep to locate the four $1M boxes — the assistant was cut off mid-response ("Claude couldn't finish this response") while running the find. The four locations ARE already confirmed (lines ~306, ~319, ~339–346, ~419–420). Removal not yet executed.

## OPEN TASKS — ranked, with the WHY
1. Remove the four $1M fundraising boxes from Teaser + Investor Deck (+ Onboarding) tabs — matters because Tyler wants to share funding info separately, not in the deck — locations already found; delete entirely, deliver via Download link + cp command, verify with re-grep for zero matches.
2. Design + add the 'API Hub' architecture slide — matters because Tyler wants to show system APIs coordinating amongst themselves and with the 23 agents as a differentiator for investors — design the architecture concept first, then place it (likely inside the TDM deck given his preference for technical content there — confirm placement style but propose TDM).
3. Verify tdm-s11 'Performance Architecture' actually deployed — matters because it was delivered but not confirmed committed/pushed by Tyler — check investor.kanoe.ai TDM deck shows 11 slides.

# ─────────────────────────────────────────────────────────────
# PART 3 — THE GUARDRAILS (what stops drift and repetition)
# ─────────────────────────────────────────────────────────────

## ✋ DO NOT TOUCH — load-bearing, deliberate, leave alone
- The voice pipeline (`SashaAvatar.tsx`, `VoiceButton.tsx`, `pcm-capture.js`, backend `voice.py` / `voice_conductor.py` / `deepgram_service.py`) — looks improvable but `voiceChat: false` is deliberate because WE own the mic pipeline (Deepgram nova-3 AudioWorklet). Do not "simplify" by handing the mic back to HeyGen.
- DNS for demo.kanoe.ai (34.111.179.208 → Google App Engine) — do NOT touch; Tyler explicitly flagged this in a prior briefing.
- Git tags kanoe-v4-working and kanoe-v5-working — deliberate working checkpoints; do not delete or re-point.
- The stray untracked file `frontend/public/slides/Kanoe_Investor_Deck_May 2026 7.key` — do not blindly `git add .` it into the fundraising commit unless Tyler confirms; it may be intentional or scratch.

## 🚫 ALREADY DECIDED — do not re-open these
| Decision | Why we chose it | What we rejected | Reversible? |
|----------|-----------------|------------------|-------------|
| Agent Architecture + Token Optimisation live as ONE 'Performance Architecture' slide (tdm-s11) inside the TDM deck | Tyler said the TDM is the right home for technical detail | Two standalone slides in the Investor Deck tab (between Competitive Landscape and Financial Projections) | Yes but Tyler rejected the alternative |
| Deliver files via Claude Download link + `cp ~/Downloads/...` | Tyler's terminal cannot reach /mnt/user-data/outputs | cp from /mnt/user-data/outputs | No |
| Read files from project knowledge, never ask Tyler to re-drag | He already dragged sasha_investor.html into the project space and got frustrated (ALL CAPS) | Asking him to re-attach | No |

## 💀 TRIED AND FAILED — do not suggest these again
- Telling Tyler to `cp /mnt/user-data/outputs/sasha_investor.html ...` — failed with "No such file or directory" — that container path is isolated from his Mac. Do not retry; always use Download link + `cp ~/Downloads/...`.
- Fetching/`cat`-ing files from Tyler's local filesystem or from the Vercel domain via Claude's bash — failed (bash is isolated; Vercel not in allowed network list). Do not retry; get the file from project knowledge or a chat upload.
- Asking Tyler to re-drag/re-upload sasha_investor.html — he responded in ALL CAPS "DONT MAKE ME DO THAT AGAIN". Do not retry; read from project knowledge.

## 🧭 USER'S STANDING PREFERENCES — how they want things done
- Deliver edited files as a Download link plus a ready-to-paste `cp ~/Downloads/... && git add . && git commit -m "..." && git push origin main` command.
- Read files that are already in project knowledge; never ask him to re-attach.
- Technical architecture content belongs in the TDM deck, not scattered into the Investor Deck tab.
- Funding/fundraising amounts are shared separately — keep them OUT of the deck.
- He redirects placement decisively; propose, but defer to his layout preference.
- Confirm before running a destructive/removal command when the source file identity is in doubt.

# ─────────────────────────────────────────────────────────────
# PART 4 — THE MAP (how it's all put together)
# ─────────────────────────────────────────────────────────────

## ARCHITECTURE / STRUCTURE
- frontend/public/sasha_investor.html — THE active work file: the investor deck (Teaser / Investor Deck / TDM / Onboarding tabs). Safe to modify — this is where all current tasks live.
- frontend/app/components/SashaAvatar.tsx, VoiceButton.tsx, SashaChat.tsx — voice/avatar UI. LOAD-BEARING; do not touch without reason.
- frontend/public/pcm-capture.js — the AudioWorklet PCM mic capture. LOAD-BEARING (voice pipeline).
- frontend/app/vietnam/page.tsx, phuquoc/page.tsx, page.tsx — live demo pages. Modify with care.
- frontend/app/onboarding/* — 6-step onboarding flow (Step1Account → Step6Deploy). Not part of current tasks.
- backend/app/services/*_agent.py — the 23 specialist agents (golf, visa, restaurant, airport_transfer, currency, credit_card, etc.). Core product; do not touch for deck work.
- backend/app/services/conductor.py, claude.py, deepgram_service.py, prompts.py — conductor + LLM + STT. LOAD-BEARING.
- backend/app/api/*.py — FastAPI routes (conductor, voice, voice_conductor, bookings, golf, search, heygen_chat).

## KEY FILES / ARTIFACTS / LINKS
- frontend/public/sasha_investor.html — the investor deck; touch for ALL current tasks.
- docs/session_current.md — current session state; regenerate at session end with scripts/end_session.sh.
- docs/new_chat_handoff.md — full architectural reference.
- docs/agents.md — all 23 agents: triggers, capabilities, tools.
- docs/data_model.md — full DB schema spec.
- docs/Kanoe_TDM and Roadmap 5.key — TDM source deck reference.
- Live: investor.kanoe.ai (portal) · demo.kanoe.ai · sasha-heygen.vercel.app/vietnam · /phuquoc · sasha-travel-production.up.railway.app (API).

## DEPENDENCIES & CONNECTIONS
- investor.kanoe.ai root redirects to /sasha_investor.html (commit 85d7de5). Editing that file changes the live investor portal after a git push → Vercel auto-deploy.
- Frontend (Vercel, sasha-heygen project) → Backend (Railway) → Supabase Postgres (RLS) → Anthropic Claude (Opus/Sonnet conductor, Haiku agent loops).
- Voice pipeline chain: HeyGen LiveAvatar (video+TTS) → Deepgram nova-3 AudioWorklet STT → conductor → response → avatar. `voiceChat: false` means WE own the mic.
- project.kanoe.ai redirect exists (commit ad49a8b). Deploy path: git push origin main → Vercel auto-deploy.

# ─────────────────────────────────────────────────────────────
# PART 5 — THE HUMAN CONTEXT (the WHY behind it all)
# ─────────────────────────────────────────────────────────────

## PEOPLE
- Tyler (tylerwarren-droid) — repo owner, developer, sole decision-maker. Works from a Mac Mini, runs git manually, downloads files from chat. Cares about a polished investor deck, clean technical framing (TDM deck), and NOT being asked to re-upload files. Currently driving fundraising prep.
- HeyGen — currently reviewing the repo (repo made public for that review). Their SDK powers the avatar.
- Investors (prospective) — audience for sasha_investor.html; funding amounts shared separately, not in-deck.

## STRATEGIC CONTEXT — the bigger picture
Tyler is in active fundraising mode. The investor deck (sasha_investor.html) is the primary artifact being polished right now, which is why deck edits take priority over product/voice work this session. He wants funding amounts kept out of the deck (shared privately) and wants the technical story (agent orchestration, token economics, and now the API Hub concept) told compellingly inside the TDM deck to differentiate Kanoe as a serious multi-agent platform. HeyGen reviewing the (now public) repo adds reputational stakes. Success looks like a clean, investor-ready deck with a strong technical architecture narrative and no premature funding figures.

## BLOCKERS & OPEN QUESTIONS
- The 'API Hub' architecture is undefined — Tyler asked Claude to help DESIGN it (system APIs engaging with agents and coordinating amongst themselves). Needs a proposed architecture before building the slide. Options on the table: place it in the TDM deck (consistent with his stated preference) vs. Investor Deck tab — propose TDM.
- tdm-s11 'Performance Architecture' delivery not confirmed pushed by Tyler — unknown whether it is live.
- Stray untracked file `frontend/public/slides/Kanoe_Investor_Deck_May 2026 7.key` — unclear if it should be committed.

# ─────────────────────────────────────────────────────────────
# PART 6 — THE HANDOFF (verbatim instructions to the next Claude)
# ─────────────────────────────────────────────────────────────

## 📋 VERBATIM BRIEFING — read this as if I'm speaking directly to you
"You are continuing work on SASHA / KANOE — the AI travel concierge investor deck. Here is what you must understand:

The core of this project is a low-latency VOICE conversation with an on-screen avatar (Sasha) that dispatches to 23 specialist agents — protect the voice pipeline; but note the ACTIVE work right now is the investor deck at frontend/public/sasha_investor.html, not the pipeline.

Right now, the state is: the deck renders live at investor.kanoe.ai, a combined 'Performance Architecture' slide was just added as tdm-s11 in the TDM deck, and two tasks are unfinished — removing four $1M fundraising boxes and designing an 'API Hub' architecture slide.

Your first action is: read sasha_investor.html from project knowledge, then remove the four confirmed $1M boxes (lines ~306, ~319, ~339–346, ~419–420) and deliver via a Download link plus a `cp ~/Downloads/... && git add/commit/push` command, verifying with a re-grep for zero matches.

Before you do anything, know that Tyler's terminal CANNOT access /mnt/user-data/outputs — always use a Download link and `cp ~/Downloads/...`.

Do not ask Tyler to re-drag or re-upload sasha_investor.html, because he already put it in the project space and got angry (ALL CAPS) — we learned this the hard way. Read from project knowledge.

The user is Tyler, a hands-on developer fundraising for Kanoe, and he values clean investor framing, technical content living in the TDM deck, and never re-uploading files. When in doubt, optimize for a polished, investor-ready deck and defer to Tyler's placement calls.

If you're about to re-add Agent Architecture / Token Optimisation as standalone Investor-Deck slides, or tell Tyler to cp from /mnt/user-data/outputs, stop — that's the drift we're preventing."

# ════════════════════════════════════════════════════════════
# END OF CONTEXT. You now know everything the last session knew.
# Do not ask the user to re-explain any of the above.
# ════════════════════════════════════════════════════════════

# DOMAIN 1: SOFTWARE / ENGINEERING

## STACK & VERSIONS
- Frontend: Next.js App Router, React 19, TypeScript, Tailwind — deployed on Vercel (sasha-heygen project).
- Backend: FastAPI (Python) — deployed on Railway (sasha-travel-production.up.railway.app). See backend/requirements.txt, runtime.txt, Procfile, railway.json.
- Database: Supabase Postgres with RLS (xlqtveusyfpffaejegiq.supabase.co). Migrations in backend/migrations/ (001_initial_schema.sql, 001_kanoe_schema.sql, 002_clients_schema.sql).
- AI: Anthropic Claude — Opus/Sonnet for conductor, Haiku for agent tool loops.
- Avatar: HeyGen LiveAvatar SDK (voiceChat: false).
- STT: Deepgram nova-3 streaming via AudioWorklet PCM (frontend/public/pcm-capture.js, backend deepgram_service.py).

## BUILD / RUN / DEPLOY COMMANDS
- Deploy: git push origin main → Vercel auto-deploys frontend; Railway auto-deploys backend.
- Start a new chat: paste into Claude — `Read docs/session_current.md and the files it references in https://github.com/tylerwarren-droid/Sasha-travel- then pick up where we left off.`
- Regenerate session doc: `ANTHROPIC_API_KEY=your_key ./scripts/end_session.sh` (calls Claude via API, auto-commits).
- Deliver deck edits: Download link + `cp ~/Downloads/sasha_investor.html ~/Projects/sasha-travel/frontend/public/sasha_investor.html && git -C ~/Projects/sasha-travel add . && git -C ~/Projects/sasha-travel commit -m "..." && git -C ~/Projects/sasha-travel push origin main`.

## REPO STATE
- Project root: ~/Projects/sasha-travel (GitHub: tylerwarren-droid/Sasha-travel-, public for HeyGen review).
- 788 tracked files. Recent commits mostly auto session_current.md updates; substantive: 26b27bf (MOR corpus + Data Licensing pillar), 012bdd0 (investor deck full update — agents, TDM fixes, AgAPI, Dataset Licensing), 85d7de5 (redirect investor.kanoe.ai root → /sasha_investor.html), e5a5622 (teaser updates — AgAPI pillar, Business Model, Use of Proceeds, LunaJet removed).
- Uncommitted: `?? frontend/public/slides/Kanoe_Investor_Deck_May 2026 7.key` (untracked — do not blindly commit).

## TESTING / VERIFICATION
- After $1M removal: re-grep the saved output file for `1M\|1 million\|ask-box\|Pre-Seed Target` and confirm ZERO matches before delivering.
- After deploy: open investor.kanoe.ai and confirm the Teaser + Investor Deck tabs no longer show $1M boxes, and the TDM deck shows 11 slides ending in 'Performance Architecture'.
- Not yet established: any automated test suite for the frontend deck (no test command surfaced).

## ENV / SECRETS
- ANTHROPIC_API_KEY — used by scripts/end_session.sh (do not hardcode; passed inline).
- HeyGen token minted via frontend/app/api/heygen/token/route.ts (+ /phuquoc variant).
- Supabase config in frontend/lib/supabase.ts. Deepgram key server-side (backend). Exact env var names for HeyGen/Deepgram/Supabase not enumerated this session — Not yet established beyond file locations.
---
_Generated: 2026-07-12T06:19:53.325Z
