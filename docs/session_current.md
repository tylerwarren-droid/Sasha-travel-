# Session State — 07/16/2026, 02:13 PM

_Auto-captured by Claude Thread_

## Summary
This was primarily a 'test' capture session with no transcript, but the substantive in-flight work is editing the investor presentation at frontend/public/sasha_investor.html. Tyler made two requests: remove four $1M fundraising boxes from the Teaser and Investor Deck tabs (already located via grep at lines ~306, ~319, ~339–346, ~419–420), and design a new 'API Hub' architecture slide where system APIs coordinate with the 23 agents. The assistant was cut off mid-grep while locating the $1M boxes; earlier the agent-architecture + token-optimization content was consolidated into one 'Performance Architecture' slide (tdm-s11) inside the TDM deck after Tyler rejected standalone Investor-Deck slides.

# ════════════════════════════════════════════════════════════
# SASHA / KANOE — AI TRAVEL CONCIERGE — THREAD CONTEXT
# The single source of truth. Read this completely before doing anything.
# Generated: 2026-07-12 · Model: Sonnet · Session #4 · ~54527 tokens
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
- WORKING NOW (verified): Live URLs deployed — investor.kanoe.ai (→ /sasha_investor.html), demo.kanoe.ai, sasha-heygen.vercel.app/vietnam, sasha-heygen.vercel.app/phuquoc, backend at sasha-travel-production.up.railway.app. Supabase Postgres with RLS live (xlqtveusyfpffaejegiq.supabase.co). Investor deck sasha_investor.html renders with Teaser / Investor Deck / TDM / Onboarding tabs. TDM deck has 11 slides including newly added 'Performance Architecture' (tdm-s11). Backend CTO services layer committed (llm, chat_store, ideas, itinerary, smart_sasha, travel_search, payments, chats, trips, ratelimit + updated conductor) per recent commits 50b4976 and bc193e6.
- BUILT BUT UNVERIFIED: The tdm-s11 'Performance Architecture' slide (consolidated agent-architecture + token-optimization content) — added but not yet confirmed visually approved by Tyler. New CTO backend services layer just committed but not yet noted as tested. Uncommitted file `frontend/public/slides/Kanoe_Investor_Deck_May 2026 7.key` sitting untracked in the working tree.
- ASPIRATIONAL / NOT BUILT: The 'API Hub' architecture slide (task 2) — discussed/requested by Tyler but NOT yet designed or added. The four $1M box deletions — located via grep but NOT yet removed (assistant was cut off mid-grep).

## LAST SESSION — what just happened
- We worked on: Editing frontend/public/sasha_investor.html — removing $1M fundraising boxes and planning an API Hub architecture slide.
- We completed: Located all four $1M elements via grep (Teaser ~306, ~319; Investor Deck ~339–346; Onboarding ~419–420). Earlier consolidated agent-architecture + token-optimization into ONE 'Performance Architecture' slide (tdm-s11) in the TDM deck after Tyler rejected standalone Investor-Deck slides.
- We changed: No code edits landed this session for the $1M removal (grep only). The tdm-s11 consolidation was completed in a prior turn. Recent commits added CTO backend services (unrelated to the deck work).
- We left off mid-: grep for the $1M boxes — the assistant was cut off after locating them, before actually deleting them from the HTML.

## OPEN TASKS — ranked, with the WHY
1. Remove the four $1M fundraising boxes from sasha_investor.html — matters because Tyler explicitly requested it and shares funding figures separately/privately, so they must not appear in the public deck HeyGen is reviewing — constraint: delete entirely (not comment out), deliver via Download link + `cp ~/Downloads/...` command, verify with a re-grep showing zero matches.
2. Design and add an 'API Hub' architecture slide — matters because Tyler wants to show investors how system APIs coordinate with the 23 agents — constraint: place it correctly (Tyler is opinionated on slide placement; confirm which tab before hardcoding, given he rejected standalone Investor-Deck slides before).
3. Confirm tdm-s11 'Performance Architecture' slide renders/reads correctly — matters because it was just consolidated and hasn't been visually verified by Tyler.

# ─────────────────────────────────────────────────────────────
# PART 3 — THE GUARDRAILS (what stops drift and repetition)
# ─────────────────────────────────────────────────────────────

## ✋ DO NOT TOUCH — load-bearing, deliberate, leave alone
- HeyGen LiveAvatar `voiceChat: false` setting — looks like a feature you could enable but is deliberately OFF because WE own the mic pipeline (Deepgram nova-3 AudioWorklet PCM). Enabling HeyGen's built-in voice chat would collide with our STT and break turn-taking. Do not change.
- frontend/public/pcm-capture.js and the Deepgram AudioWorklet STT pipeline — load-bearing crown jewel; do not refactor or 'optimize' unless explicitly asked.
- The tdm-s11 'Performance Architecture' slide placement (inside TDM deck) — deliberately placed there because Tyler rejected standalone Investor-Deck slides. Do not move it back.

## 🚫 ALREADY DECIDED — do not re-open these
| Decision | Why we chose it | What we rejected | Reversible? |
|----------|-----------------|------------------|-------------|
| Agent-architecture + token-optimization live as ONE 'Performance Architecture' slide (tdm-s11) in the TDM deck | Tyler wanted it consolidated, not scattered | Standalone Agent Architecture / Token Optimization slides in the Investor Deck | No |
| Deliver edited files via Download link + `cp ~/Downloads/...` | Tyler's terminal cannot access container paths | Delivering via /mnt/user-data/outputs (failed: 'No such file or directory') | No |
| Read attached files from project knowledge first | Tyler already dragged them in; re-asking frustrates him | Asking Tyler to re-drag/re-upload files | No |
| Remove $1M boxes entirely (not hide/comment) | Tyler shares funding info separately | Leaving them in the public deck | No |

## 💀 TRIED AND FAILED — do not suggest these again
- Delivering files via /mnt/user-data/outputs and telling Tyler to `cp` from there — failed because that path is NOT on his Mac Mini terminal ("No such file or directory"). Do not retry; always use Download link + `cp ~/Downloads/...`.
- Standalone Agent Architecture / Token Optimization slides in the Investor Deck — Tyler rejected the placement. Do not re-add as separate Investor-Deck slides.

## 🧭 USER'S STANDING PREFERENCES — how they want things done
- Read files from the project space before doing anything; NEVER ask him to re-attach files he's already provided (he replies in ALL CAPS when annoyed).
- Deliver every edited file as a Download link accompanied by an exact `cp ~/Downloads/... && git add/commit/push` command he can paste directly.
- He is opinionated about slide placement — confirm placement rather than assuming; he will redirect content he doesn't like.
- Funding/fundraising figures are shared separately — keep them OUT of the public deck.
- He runs git manually from ~/Projects/sasha-travel; give repo-scoped `git -C ~/Projects/sasha-travel ...` commands.

# ─────────────────────────────────────────────────────────────
# PART 4 — THE MAP (how it's all put together)
# ─────────────────────────────────────────────────────────────

## ARCHITECTURE / STRUCTURE
- frontend/public/sasha_investor.html — the investor presentation (Teaser / Investor Deck / TDM / Onboarding tabs). ACTIVE EDIT TARGET. Safe to modify, but deliver via Download + cp command.
- frontend/ — Next.js App Router, React 19, TypeScript, Tailwind (Vercel project sasha-heygen). Demo pages: app/vietnam/page.tsx, app/phuquoc/page.tsx, app/voice/page.tsx. Load-bearing: app/components/SashaAvatar.tsx, VoiceButton.tsx, public/pcm-capture.js (voice pipeline).
- backend/app/ — FastAPI (Railway). api/ has conductor.py, voice.py, voice_conductor.py, heygen_chat.py, payments.py, etc. services/ holds the 23 agents + conductor.py, claude.py, deepgram_service.py, llm.py. Load-bearing: conductor.py, deepgram_service.py, claude.py.
- backend/app/services/*_agent.py — the 23 specialist agents (golf, visa, restaurant, airport_transfer, currency, etc.). Do not casually refactor.
- docs/ — session_current.md (auto-regenerated), new_chat_handoff.md (full architecture ref), agents.md (23 agents), data_model.md (DB schema).

## KEY FILES / ARTIFACTS / LINKS
- frontend/public/sasha_investor.html — the investor deck; touch NOW for the two open tasks.
- docs/session_current.md — current session state; regenerate via scripts/end_session.sh.
- docs/new_chat_handoff.md — full architectural reference; read when you need deep architecture context.
- docs/agents.md — all 23 agents' triggers/capabilities/tools.
- scripts/end_session.sh — regenerates session_current.md via Claude API and auto-commits (run: `ANTHROPIC_API_KEY=... ./scripts/end_session.sh`).
- Live: investor.kanoe.ai, demo.kanoe.ai, sasha-heygen.vercel.app/vietnam, sasha-heygen.vercel.app/phuquoc, sasha-travel-production.up.railway.app.

## DEPENDENCIES & CONNECTIONS
- Frontend (Vercel) → Backend FastAPI (Railway sasha-travel-production.up.railway.app) → Supabase Postgres (xlqtveusyfpffaejegiq.supabase.co, RLS on).
- Voice: HeyGen LiveAvatar SDK (video + TTS) + Deepgram nova-3 STT (AudioWorklet PCM via pcm-capture.js) → conductor → Anthropic Claude (Opus/Sonnet conductor, Haiku for agent tool loops).
- investor.kanoe.ai serves frontend/public/sasha_investor.html — editing that file affects the live investor portal after deploy.
- HeyGen is reviewing the public repo — repo cleanliness/content matters right now.

# ─────────────────────────────────────────────────────────────
# PART 5 — THE HUMAN CONTEXT (the WHY behind it all)
# ─────────────────────────────────────────────────────────────

## PEOPLE
- Tyler (GitHub tylerwarren-droid) — repo owner/developer, works from a Mac Mini (~/Projects/sasha-travel). Cares about a polished investor deck, correct slide placement, and NOT being asked to re-attach files. Requested $1M box removal and the API Hub slide.
- HeyGen (partner/vendor) — currently reviewing the repo (repo made public for the review). Their SDK powers Sasha's avatar.
- End users — luxury/high-end travelers experiencing the /vietnam and /phuquoc demos.

## STRATEGIC CONTEXT — the bigger picture
Kanoe is actively fundraising (Pre-Seed) — the investor portal (investor.kanoe.ai) is a live pitch surface, so the deck's content and polish directly affect fundraising outcomes. Tyler deliberately keeps specific funding figures OUT of the public deck (shares them separately), hence the $1M box removal. HeyGen is reviewing the now-public repo, adding reputational pressure to keep everything clean. Success right now = a clean investor deck (no stray $1M figures) plus a clear 'API Hub' slide that communicates how the platform's APIs orchestrate the 23 agents.

## BLOCKERS & OPEN QUESTIONS
- No transcript was captured this session (auto-capture / pre-buffer) — rely on session_current.md and grep line numbers; verify current file contents before editing since line numbers are approximate (~306, ~319, ~339–346, ~419–420).
- Open question: which tab should the new 'API Hub' architecture slide live in? Tyler rejected standalone Investor-Deck slides before, so confirm placement before hardcoding (likely the TDM deck alongside tdm-s11, but ask/confirm).
- Uncommitted untracked file `frontend/public/slides/Kanoe_Investor_Deck_May 2026 7.key` — decide whether to commit or ignore (do not commit without Tyler's say-so).

# ─────────────────────────────────────────────────────────────
# PART 6 — THE HANDOFF (verbatim instructions to the next Claude)
# ─────────────────────────────────────────────────────────────

## 📋 VERBATIM BRIEFING — read this as if I'm speaking directly to you
"You are continuing work on Sasha / Kanoe, an AI travel concierge platform. Here is what you must understand:

The core of this project is a low-latency voice conversation with an on-screen HeyGen avatar (Sasha) that dispatches to 23 specialist agents — WE own the mic pipeline (Deepgram nova-3, `voiceChat: false`). Protect that pipeline; don't touch it unless asked.

Right now, though, the active work is the investor deck at frontend/public/sasha_investor.html — NOT the voice pipeline. The last thing that happened: I located (via grep) four $1M fundraising boxes to delete but got cut off before removing them, and Tyler also asked for a new 'API Hub' architecture slide.

Your first action is to read sasha_investor.html from the project knowledge (Tyler already attached it — do NOT ask him to re-drag), delete the four confirmed $1M elements at ~306, ~319, ~339–346, ~419–420, and hand back a Download link plus the exact `cp ~/Downloads/... && git ... push` command. Then verify by re-grepping for zero $1M matches. After that, design the API Hub slide.

Before you do anything, know that Tyler's terminal cannot see /mnt/user-data/outputs — ALWAYS deliver via a Download link and a `cp ~/Downloads/...` command.

Do not re-add Agent Architecture / Token Optimization as standalone Investor-Deck slides, because Tyler explicitly rejected that placement — they now live as ONE 'Performance Architecture' slide (tdm-s11) in the TDM deck. We learned this the hard way.

The user is Tyler, a competent developer who is fundraising and being reviewed by HeyGen; he values a clean deck, correct slide placement, and NOT re-explaining or re-attaching things. When in doubt, optimize for a polished, funding-figure-free public deck and confirm slide placement before hardcoding.

If you're about to ask Tyler to re-upload sasha_investor.html or hand him a /mnt/user-data/outputs path — stop. That's the drift we're preventing."

# ════════════════════════════════════════════════════════════
# END OF CONTEXT. You now know everything the last session knew.
# Do not ask the user to re-explain any of the above.
# ════════════════════════════════════════════════════════════

# DOMAIN 1: SOFTWARE / ENGINEERING

## TECH STACK & VERSIONS
- Frontend: Next.js App Router, React 19, TypeScript, Tailwind — deployed on Vercel (project sasha-heygen).
- Backend: FastAPI (Python; runtime.txt + requirements.txt in backend/) — deployed on Railway (sasha-travel-production.up.railway.app), Procfile-based.
- Database: Supabase Postgres with RLS (xlqtveusyfpffaejegiq.supabase.co).
- AI: Anthropic Claude — Opus/Sonnet for the conductor, Haiku for agent tool loops.
- Avatar: HeyGen LiveAvatar SDK (`voiceChat: false`).
- STT: Deepgram nova-3 streaming via AudioWorklet PCM (frontend/public/pcm-capture.js).

## BUILD / RUN / TEST COMMANDS
- New chat startup (per README): paste into Claude → "Read docs/session_current.md and the files it references in https://github.com/tylerwarren-droid/Sasha-travel- then pick up where we left off."
- Regenerate session state: `ANTHROPIC_API_KEY=your_key ./scripts/end_session.sh` (calls Claude API, auto-commits).
- Git (Tyler's flow): `git -C ~/Projects/sasha-travel add . && git -C ~/Projects/sasha-travel commit -m "..." && git -C ~/Projects/sasha-travel push origin main`
- Frontend: Next.js dev/build via npm (frontend/package.json) — not explicitly run this session.
- Test suite: Not yet established (no test command surfaced in source material).

## ENV / SECRETS / CONFIG
- ANTHROPIC_API_KEY — required for scripts/end_session.sh.
- Supabase URL/keys — xlqtveusyfpffaejegiq.supabase.co (frontend/lib/supabase.ts).
- HeyGen token routes: frontend/app/api/heygen/token/route.ts and .../token/phuquoc/route.ts.
- Deepgram API key — for nova-3 STT (backend/app/services/deepgram_service.py).
- Railway config: backend/railway.json, backend/Procfile, backend/runtime.txt.
- Exact secret names/values: Not yet established (not surfaced in source material).

## CI / DEPLOYMENT
- Frontend auto-deploys to Vercel (sasha-heygen) on push to main → serves investor.kanoe.ai (from public/sasha_investor.html), demo.kanoe.ai, /vietnam, /phuquoc.
- Backend deploys to Railway (sasha-travel-production.up.railway.app) via railway.json/Procfile.
- No explicit CI test gate documented — Not yet established.

## KNOWN ISSUES / TECH DEBT
- Line numbers for $1M boxes are approximate (~306, ~319, ~339–346, ~419–420) — re-verify against current file before deleting.
- Untracked file `frontend/public/slides/Kanoe_Investor_Deck_May 2026 7.key` in working tree — undecided whether to commit.
- tdm-s11 'Performance Architecture' slide unverified visually.
- New CTO backend services layer (commits 50b4976, bc193e6) recently added — testing status not documented.
- No captured transcript this session — treat session_current.md as primary source.
---
_Generated: 2026-07-16T12:13:55.411Z
