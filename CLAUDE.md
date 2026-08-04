# CLAUDE.md — Sasha / Kanoe.ai Project

This file gives Claude Code the full context and operating rules for the sasha-travel repo.

## Working style (CRITICAL)
- Tyler is non-technical. NEVER ask him to find lines in code or edit files manually.
- Every task must be delivered as ONE complete copy-paste command (sed, cat >, python3 heredoc, or a /tmp/*.sh script) that does the entire job.
- For multi-line sequences, write to a script file (cat > /tmp/x.sh << 'SCRIPT' ... SCRIPT then bash /tmp/x.sh) to avoid paste/quoting mangling in the terminal.
- Never suggest he sleep or make personal suggestions.

## What Sasha/Kanoe is
AI-first travel operating system. Sasha is a voice-enabled AI concierge. Architecture: hundreds of small specialist agents that never talk to each other, all routed through one Conductor. No universal APIs — web scraping, email agents, WhatsApp, MCP.

Flow: Sasha -> Conductor (keyword intent routing, parallel via asyncio) -> Specialist Agents -> merged into one response -> Sasha speaks it.

## Stack
- Backend: FastAPI (Python) on Railway — https://sasha-travel-production.up.railway.app
- Frontend: Next.js on Vercel. 4 projects watch the same repo and deploy on push: discover-vietnam, sasha-travel/demo.kanoe.ai, sasha-travel-hdyp, sasha-heygen/project.kanoe.ai. Env vars are per-project.
- DB: Supabase (pgvector planned for RAG)
- AI: Anthropic Claude (Haiku + Sonnet), HeyGen LiveAvatar, Deepgram STT/TTS
- Booking/comms: Resend (email), Bland.ai (calls), RateHawk (hotels), Stripe (payments), Unsplash (Foto agent)
- Repo: github.com/tylerwarren-droid/Sasha-travel- (private)
- Local project: /Users/tylerwarren/Projects/sasha-travel
- Local venv: backend/venv (NO dot). Activate: cd backend && source venv/bin/activate

## Agents (27 services, live)
golf (20 Vietnam courses, real emails, Resend booking), foto (Unsplash), booking_confirmation (web search + Resend + Bland.ai), health, beauty, dog_walking, restaurant, car_rental, credit_card, plus supporting services: llm, chat_store, ideas_agent, itinerary_agent, local_itinerary, smart_sasha_agent, travel_search, hotels_db, booking_links, booking_ref, ratehawk, deepgram_service, claude, prompts, tenant, card_benefits_db, vietnam_golf_database, conductor.

## Key API routes
- POST /api/agents/conductor — main text entry point
- POST /api/voice/conductor — voice pathway (Deepgram STT + Conductor + TTS)
- POST /api/heygen/chat/completions — HeyGen avatar pathway (OpenAI-compatible)
- POST /api/agents/ideas — Ideas agent (NOT /api/ideas — mounted with /api/agents prefix)
- payments: /api/payments/create-checkout, /verify, /webhook
- /api/chats, /api/trips

## CORS — #1 recurring deploy hazard
Every CTO zip ships backend/app/main.py WITHOUT https://project.kanoe.ai in _DEFAULT_ORIGINS (only investor + demo are listed). This breaks the frontend<->backend connection for project.kanoe.ai. The CORS fix MUST be re-applied after every sync, before the build gate. main.py also supports an ALLOWED_ORIGINS env var on Railway (comma-separated) as a no-code alternative.

Re-apply command:
    cd ~/Projects/sasha-travel && python3 - <<'PY'
    import pathlib
    p = pathlib.Path("backend/app/main.py"); s = p.read_text()
    if '"https://project.kanoe.ai"' not in s:
        s = s.replace('    "https://demo.kanoe.ai",', '    "https://demo.kanoe.ai",\n    "https://project.kanoe.ai",')
        p.write_text(s); print("CORS re-applied")
    else: print("already present")
    PY
    grep -n "kanoe.ai" backend/app/main.py

## Repo-only files that MUST survive every sync
- app/vietnam2/ — uses LEGACY component copies app/vietnam2/SashaChatLegacy.tsx and app/vietnam2/VoiceButton.tsx (CTO's rewritten SashaChat has an incompatible props interface). vietnam2 needs leaflet + @types/leaflet in package.json.
- app/kanoe/
- frontend/public/sasha_investor.html — investor portal, LIVE-ONLY. Never touch via repo without Tyler downloading/verifying/confirming first.

## Investor portal notes
- Served by sasha-heygen Vercel project at investor.kanoe.ai/sasha_investor.html
- Two distinct CSS classes: class="slide" (Investor Deck, 10 slides) vs class="tdm-slide" (TDM panel, 11 slides). Mixing them is a critical error.

## DNS — do NOT touch
- demo.kanoe.ai -> 34.111.179.208 (Google App Engine). Never change.

## Mac-mini download quirk
Google Drive downloads always get renamed sequentially regardless of version label: V5 -> Sasha_V2-2, V6 -> Sasha_V2-3, etc. Do NOT trust the folder name — verify contents. Find the newest with: ls -lat ~/Downloads/ | head -5

## THE DEPLOY PLAYBOOK (battle-tested: V2.4, V5, V6)
Run in order. Stop at any gate that fails.

Stage 0 — locate + git state:
    cd ~/Projects/sasha-travel && ls -lat ~/Downloads/ | head -5 && \
    git fetch -q && git log --oneline -1 && echo "uncommitted: $(git status --short | wc -l)"

Stage 0.5 — verify folder + CORS check (set V to newest folder):
    V=~/Downloads/Sasha_V2-X && \
    ls -d "$V/backend" "$V/frontend" && \
    ls "$V/backend/app/services/"*.py | xargs -n1 basename && \
    echo "CORS count (expect 0): $(grep -c project.kanoe.ai "$V/backend/app/main.py")"

Stage A — tag + sync (write to script to avoid paste mangling):
    cat > /tmp/sync.sh << 'SCRIPT'
    cd ~/Projects/sasha-travel
    git tag pre-vX-$(date +%Y%m%d-%H%M)
    V=~/Downloads/Sasha_V2-X
    rsync -av --delete \
      --exclude='__pycache__' --exclude='*.pyc' --exclude='.venv' --exclude='venv' \
      --exclude='.env' --exclude='*.db' --exclude='*.db-wal' --exclude='*.db-shm' \
      "$V/backend/app/" backend/app/
    rsync -av \
      --exclude='node_modules' --exclude='.next' --exclude='.vercel' \
      --exclude='package.json' --exclude='package-lock.json' \
      --exclude='.env' --exclude='.env.local' \
      --exclude='public/sasha_investor.html' \
      --exclude='tsconfig.tsbuildinfo' --exclude='next-env.d.ts' \
      "$V/frontend/app/" frontend/app/
    rsync -av --exclude='node_modules' "$V/frontend/lib/" frontend/lib/
    git status --short | grep -i sasha_investor && echo "PORTAL TOUCHED" || echo "portal untouched"
    echo "deletions: $(git status --short | grep '^ D' | wc -l | tr -d ' ')"
    echo "total changes: $(git status --short | wc -l | tr -d ' ')"
    SCRIPT
    bash /tmp/sync.sh
If deletions > 0, investigate each deleted file before proceeding (check it's not a repo-only file or a still-imported agent). Confirm the new conductor does not IMPORT any deleted agent (grep for 'from app.services.X import'); keyword-only references are safe.

Stage B — re-apply CORS (command above), then import test:
    cd ~/Projects/sasha-travel/backend && source venv/bin/activate && \
    python3 -c "from app.main import app; print('BACKEND LOADS CLEAN')" 2>&1 | tail -6

Stage C — frontend build gate:
    cd ~/Projects/sasha-travel/frontend && npm install 2>&1 | tail -3 && \
    npm run build 2>&1 | tail -25
Must produce 17 routes with no compile errors.

Stage D — commit + push (only if both gates passed):
    cd ~/Projects/sasha-travel && git add -A && \
    git status --short | grep -i sasha_investor && echo "STOP - portal staged" || \
    ( git commit -m "Deploy CTO VX: <summary>; CORS project.kanoe.ai preserved" && \
      git push origin main && echo "PUSHED" )

Stage E — verify (wait ~3 min for Railway/Vercel):
    echo -n "backend: " && curl -s -o /dev/null -w "%{http_code}\n" https://sasha-travel-production.up.railway.app/
    echo -n "conductor: " && curl -s -o /dev/null -w "%{http_code}\n" -X POST -H "Content-Type: application/json" -d '{}' https://sasha-travel-production.up.railway.app/api/agents/conductor
    echo -n "CORS: " && curl -s -i -X POST https://sasha-travel-production.up.railway.app/api/agents/conductor -H "Origin: https://project.kanoe.ai" -H "Content-Type: application/json" -d '{"message":"test"}' 2>&1 | grep -i "access-control-allow-origin"
    echo -n "vietnam2: " && curl -s -o /dev/null -w "%{http_code}\n" https://project.kanoe.ai/vietnam2
Expected: backend 200, conductor 422, CORS header echoes project.kanoe.ai, vietnam2 200.

Rollback if needed: git reset --hard pre-vX-<timestamp> (tag was set in Stage A).

## Two deploy patterns
- Full rsync (major CTO drops): the playbook above.
- Surgical (small patches): diff zip dates, copy only changed files, build-gated push.

## Known crash history
July 16 2026: first CTO deploy crashed on Railway with ModuleNotFoundError app.services.llm — a new conductor imported services not copied. Fixed by copying the whole services folder. Lesson: the local import test (Stage B) catches this before push.

## Deploy history
- V2.4 (commit 8338744): credit_card + car_rental agents, RateHawk hotel cards, TripMap, workspace panels; removed 14 unused agent stubs.
- CORS hotfix (e4abe0f): added project.kanoe.ai to _DEFAULT_ORIGINS.
- V5 (89ab434): conductor + itinerary + travel_search refinements, cache 90->108.
- V6 (21bb0f8): conductor + SashaChat + ItineraryDays + TripPanel + heygen token refinements.
