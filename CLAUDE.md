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
golf (20 Vietnam courses, real emails, Resend booking), foto (Unsplash), car_rental, credit_card, plus supporting services: llm, chat_store, ideas_agent, itinerary_agent, local_itinerary, smart_sasha_agent, travel_search, hotels_db, booking_links, booking_ref, ratehawk, deepgram_service, claude, prompts, tenant, card_benefits_db, vietnam_golf_database, conductor.

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
        demo = '    "https://demo.kanoe.ai",'
        if demo not in s:   # S-45: this used to replace nothing and still print "CORS re-applied"
            raise SystemExit("⛔ STOP: main.py's demo.kanoe.ai origin line changed in this CTO drop — CORS was NOT re-applied. Add project.kanoe.ai by hand.")
        s = s.replace(demo, demo + '\n    "https://project.kanoe.ai",', 1)
        p.write_text(s); print("CORS re-applied")
    else: print("already present")
    PY
    grep -n "kanoe.ai" backend/app/main.py

Booking hand-off re-apply command (S-26) — conductor.py is the CTO's; every zip drops this hook. It REFUSES,
loudly, if the anchor line it sits above has changed, rather than silently not applying:
    cd ~/Projects/sasha-travel && python3 - <<'PY'
    import pathlib
    p = pathlib.Path("backend/app/services/conductor.py"); s = p.read_text()
    if "from booking_signer.handoff import booking_handoff" not in s:
        anchor = "    # ── Card choice (second half of a booking) ─────────────────────────────────────────\n"
        block = ("    # S-26 booking hand-off: backend/booking_signer/handoff.py. CTO zips drop this; Stage B re-applies it.\n"
                 "    from booking_signer.handoff import booking_handoff  # noqa: E402\n"
                 "    _handoff = booking_handoff(user_message, conversation_history)\n"
                 "    if _handoff is not None:\n"
                 "        return _handoff\n\n")
        if anchor not in s:
            raise SystemExit("⛔ STOP: the conductor's anchor line changed in this CTO drop — the booking hand-off was NOT re-applied. Place it by hand at the top of conduct().")
        s = s.replace(anchor, block + anchor); p.write_text(s); print("booking hand-off re-applied")
    else: print("booking hand-off already present")
    PY
    grep -n "booking_signer.handoff" backend/app/services/conductor.py

Booking drafts re-apply command (S-64 step 11) — booking-in-chat for ANY venue: the conductor asks only what is missing
and returns the reservation/1 draft. Sits directly under the S-26 hand-off, so RUN THE HAND-OFF COMMAND FIRST. It REFUSES,
loudly, if the hand-off lines it sits under are not there:
    cd ~/Projects/sasha-travel && python3 - <<'PY'
    import pathlib
    p = pathlib.Path("backend/app/services/conductor.py"); s = p.read_text()
    if "from booking_signer.chat_request import booking_turn" not in s:
        anchor = ("    _handoff = booking_handoff(user_message, conversation_history)\n"
                  "    if _handoff is not None:\n"
                  "        return _handoff\n")
        block = ("    # S-64 booking drafts: backend/booking_signer/chat_request.py. CTO zips drop this; Stage B re-applies it.\n"
                 "    from booking_signer.chat_request import booking_turn  # noqa: E402\n"
                 "    _draft_turn = booking_turn(user_message, conversation_history)\n"
                 "    if _draft_turn is not None:\n"
                 "        return _draft_turn\n")
        if anchor not in s:
            raise SystemExit("⛔ STOP: the Psi hand-off lines (the anchor) are not in conductor.py — re-apply the S-26 hand-off first; the booking drafts were NOT applied.")
        s = s.replace(anchor, anchor + block); p.write_text(s); print("booking drafts re-applied")
    else: print("booking drafts already present")
    PY
    grep -n "booking_signer.chat_request" backend/app/services/conductor.py
The suite refuses if this is skipped: backend/tests/test_stage_b_hooks.py fails, and /api/booking/health reports
"chat_hooks": {"booking_drafts": false} (Stage E below).

Chat cancel (Sasha 96) — "cancel X" is a conductor hand-off (`booking_cancel`, backend/booking_signer/handoff.py) the
chat renders as ChatCancel. Three CTO-file lines, each marked "Sasha 96 chat cancel (Stage B)":
  · backend/app/api/conductor.py: `booking_cancel: Optional[dict] = None` after `booking_find` in the response model, and
    `booking_cancel=result.get("booking_cancel"),` after `booking_find=result.get("booking_find"),` in the call;
  · frontend/app/components/SashaChat.tsx: the import (`import ChatCancel from './ChatCancel'`), the state
    (`const [bookingCancel, setBookingCancel] = useState<{ venue: string; n: number } | null>(null)`), the setter after
    the booking_find one (`if (response.data.booking_cancel) setBookingCancel({ ...response.data.booking_cancel, n: Date.now() })`),
    and the JSX after ChatBooking's (`{bookingCancel && <ChatCancel key={bookingCancel.n} venue={bookingCancel.venue} />}`).
/api/booking/health reports "chat_hooks": {"response_fields": false} if the conductor lines are lost.

Sasha's abilities re-apply command (Sasha 88) — the conversational model is told what she can do (phone, email,
WhatsApp, book, follow up, cancel), so the chat and the avatar never say she "can't call". Run after the booking drafts:
    cd ~/Projects/sasha-travel && python3 - <<'PY'
    import pathlib
    p = pathlib.Path("backend/app/services/conductor.py"); s = p.read_text()
    if "from booking_signer.abilities import ABILITIES" not in s:
        anchor = "    \"options up' — instead of claiming you can't.\"\n)\n"
        block = ("# Sasha 88 abilities: backend/booking_signer/abilities.py. CTO zips drop this; Stage B re-applies it.\n"
                 "from booking_signer.abilities import ABILITIES as _SASHA_ABILITIES  # noqa: E402\n"
                 "CAPABILITY_FACTS += _SASHA_ABILITIES\n")
        if anchor not in s:
            raise SystemExit("⛔ STOP: CAPABILITY_FACTS' closing line moved — find where CAPABILITY_FACTS is defined and add the block after it.")
        s = s.replace(anchor, anchor + block); p.write_text(s); print("abilities re-applied")
    else: print("abilities already present")
    PY
/api/booking/health reports "chat_hooks": {"abilities": false} if it is lost.

## Repo-only files that MUST survive every sync
- app/vietnam2/ — uses LEGACY component copies app/vietnam2/SashaChatLegacy.tsx and app/vietnam2/VoiceButton.tsx (CTO's rewritten SashaChat has an incompatible props interface). vietnam2 needs leaflet + @types/leaflet in package.json.
- app/kanoe/
- frontend/app/booking-helper/ — the booking page (S-25): repo-only. Stage A's frontend rsync has no --delete, so it survives unless the CTO ships a file at the same path.
- S-62 step 7 (chat history per account): backend/app/services/chat_account.py and the owner checks in app/api/chats.py, conductor.py (classify too), payments.py and trips.py; frontend/lib/guest-auth.ts and five "S-62 step 7" lines in SashaChat.tsx (import, refreshGuestAuth before a turn, guestAuth() on classify and conductor, session_id adoption) plus YouPanel's trips fetch. If a backend/app or SashaChat replacement drops them, re-apply; the prebuild fails without the SashaChat lines and tests/test_chat_accounts.py fails without the backend ones.
- frontend/lib/signed-in.ts (S-62) — repo-only. AND the S-62 sign-in gate inside the CTO's frontend/app/api/onboarding/save/route.ts: if a drop replaces that file, re-add `import { founderSignedIn } from '@/lib/signed-in'` and, first in POST, `if (!(await founderSignedIn())) return Response.json({ error: 'Sign in to save onboarding; nothing was saved', rule: 'sign_in_required' }, { status: 401 })`. The build refuses until it is back (prebuild).
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

### ⚠⚠ READ BEFORE ANY CTO DROP (added 25 Sep 2026)
1. WHICH COPY. The up-to-date checkout is ~/Developer/Sasha-travel- (it matches GitHub main).
   ~/Projects/sasha-travel is an older copy of the same repo and is behind. The paths below still say
   ~/Projects/sasha-travel — until they are changed, `git pull` there first or you will sync into a stale tree.
2. STAGE A DELETES REPO-ONLY FILES. `rsync --delete` makes backend/app/ an exact copy of the CTO's zip:
   any file in backend/app/ that is NOT in his zip is DELETED, and any repo edit to a file he ships is
   OVERWRITTEN. As of 25 Sep 2026 that includes the Duffel work (commits 5b0fee9, 6664cec, 7e124bf):
     - backend/app/services/duffel.py          repo-only → DELETED unless the CTO ships it
     - backend/app/services/conductor.py       Duffel edits → OVERWRITTEN unless he folded them in
     - backend/app/services/travel_search.py   Duffel edits → OVERWRITTEN unless he folded them in
   (backend/tests/ and frontend/ are not deleted; frontend files he ships are still overwritten.)
3. Stage 0.6 — list what Stage A would delete, BEFORE running it (read-only):
       cd ~/Projects/sasha-travel && V=~/Downloads/Sasha_V2-X && \
       comm -23 <(cd backend/app && find . -type f ! -path '*/__pycache__/*' ! -name '*.pyc' | sort) \
                <(cd "$V/backend/app" && find . -type f ! -path '*/__pycache__/*' ! -name '*.pyc' | sort)
   Every line printed is a file Stage A will delete. For each: re-add it after the sync, or confirm the CTO
   replaced it. Then check conductor.py / travel_search.py for the Duffel edits after the sync.
4. backend/booking_signer/ (Sasha booking-task signer) lives OUTSIDE backend/app/ on purpose, so Stage A
   never touches it. It IS mounted (S-17) by three lines in app/main.py, which every CTO zip drops: Stage B
   re-applies them exactly like the CORS line, and Stage E probes /api/booking/health. A forgotten mount
   shows as a loud 404 there, never a silent loss.

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

Stage B — re-apply CORS (command above), the booking hand-off (above), THEN the booking drafts (above, after the hand-off), the chat booking (above), the booking mount (below), the reservations insertion (below), the onboarding honesty (`python3 frontend/scripts/stage_b_onboarding_honesty.py`, S-62: Go Live never shows success for a refused save; refuses loudly if an anchor moved; the prebuild fails without it) and the onboarding sign-in gate (see Repo-only files), then import test.

Chat booking re-apply command (S-66, EU's booking-in-chat) — SashaChat.tsx is the CTO's; every zip drops these five
lines. They give the chat Find → pick → read (frontend/app/components/ChatBooking.tsx, repo-only) and let a typed line
reach the booking thread first. It REFUSES, loudly, if any anchor changed:
    cd ~/Projects/sasha-travel && python3 - <<'PY'
    import pathlib
    p = pathlib.Path("frontend/app/components/SashaChat.tsx"); s = p.read_text()
    if "S-66 chat booking" not in s:
        a_imp = "import YouPanel from './workspace/YouPanel'\n"
        a_state = "  const [bookings, setBookings] = useState<"
        a_send = "  const sendMessage = async (content: string, opts?: { force?: boolean; intent?: string }) => {\n"
        a_resp = "      const { response: sashaResponse, conversation_history,"
        a_jsx = "        {(hotels.length > 0 || bookings.length > 0 || bookingLinks.length > 0) && ("
        if any(a not in s for a in (a_imp, a_state, a_send, a_resp, a_jsx)):
            raise SystemExit("⛔ STOP: SashaChat's anchors changed in this CTO drop — chat booking was NOT re-applied. Place it by hand.")
        s = s.replace(a_imp, a_imp + "import ChatBooking from './ChatBooking'  // S-66 chat booking, Stage B re-applies\nimport { takeChatText } from '@/lib/chat-booking-bus'\n", 1)
        s = s.replace(a_state, "  const [bookingFind, setBookingFind] = useState<{ what: string; where: string; country?: string; draft?: unknown } | null>(null)  // S-66 chat booking\n" + a_state, 1)
        s = s.replace(a_send, a_send + "    if (takeChatText(content)) { setMessages(prev => [...prev, { role: 'user', content }]); return }  // S-66 chat booking\n", 1)
        i = s.index(a_resp); j = s.index("\n", i) + 1
        s = s[:j] + "      if (response.data.booking_find) setBookingFind({ ...response.data.booking_find, draft: response.data.reservation_draft ?? null })  // S-66 chat booking\n" + s[j:]
        s = s.replace(a_jsx, "        {/* S-66 chat booking: repo-only component. CTO zips drop this; Stage B re-applies it. */}\n        {bookingFind && <ChatBooking key={`${bookingFind.what}|${bookingFind.where}`} find={bookingFind} />}\n" + a_jsx, 1)
        p.write_text(s); print("chat booking re-applied")
    else: print("chat booking already present")
    PY
    grep -n "S-66 chat booking" frontend/app/components/SashaChat.tsx
The build refuses if this is skipped: prebuild (scripts/check-outcome-surfaces.mjs) fails when SashaChat lacks it.
The conductor's HTTP response carries only the fields its model declares, so the chat needs two more (S-66; the
CTO's backend/app/api/conductor.py, dropped by every zip). Same rules — refuses loudly if an anchor moved:
    cd ~/Projects/sasha-travel && python3 - <<'PY'
    import pathlib
    p = pathlib.Path("backend/app/api/conductor.py"); s = p.read_text()
    if "S-66 chat booking" not in s:
        a_model = "    saved_card: Optional[dict] = None\n    conversation_history: list\n"
        a_call = "            saved_card=result.get(\"saved_card\"),\n"
        if a_model not in s or a_call not in s:
            raise SystemExit("⛔ STOP: api/conductor.py's anchors changed in this CTO drop — booking_find was NOT re-applied; the chat cannot book.")
        s = s.replace(a_model, "    saved_card: Optional[dict] = None\n    booking_find: Optional[dict] = None  # S-66 chat booking (Stage B)\n    reservation_draft: Optional[dict] = None  # S-66 chat booking (Stage B)\n    conversation_history: list\n", 1)
        s = s.replace(a_call, a_call + "            booking_find=result.get(\"booking_find\"),  # S-66 chat booking (Stage B)\n            reservation_draft=result.get(\"reservation_draft\"),  # S-66 chat booking (Stage B)\n", 1)
        p.write_text(s); print("conductor response fields re-applied")
    else: print("conductor response fields already present")
    PY
    grep -n "S-66 chat booking" backend/app/api/conductor.py
backend/tests/test_stage_b_hooks.py fails, and /api/booking/health shows chat_hooks.response_fields false, if this is skipped.

Booking mount re-apply command (S-17):
    cd ~/Projects/sasha-travel && python3 - <<'PY'
    import pathlib
    p = pathlib.Path("backend/app/main.py"); s = p.read_text()
    if "from booking_signer.routes import router as booking_signer_router" not in s:
        block = ("# S-17 booking signer: backend/booking_signer/ (outside app/). CTO zips drop this line; Stage B re-applies it.\n"
                 "from booking_signer.routes import router as booking_signer_router  # noqa: E402\n"
                 "app.include_router(booking_signer_router)  # /api/booking/*\n")
        anchor = "app.include_router(trips_router)     # already prefixed /api/trips\n"
        if anchor in s:
            s = s.replace(anchor, anchor + block)
        else:   # S-45: still mounts, but say so — a moved anchor must be seen
            s = s.rstrip("\n") + "\n" + block
            print("⚠ the trips_router anchor moved — the booking mount was APPENDED at the end of main.py; check it")
        p.write_text(s); print("booking mount re-applied")
    else: print("booking mount already present")
    PY
    grep -n "booking_signer" backend/app/main.py

Reservations re-apply command (S-45) — Sasha's reservations in the guest's trip view (YouPanel). Refuses, never guesses:
    cd ~/Projects/sasha-travel && python3 - <<'PY'
    import pathlib
    p = pathlib.Path("frontend/app/components/workspace/YouPanel.tsx"); s = p.read_text()
    if "S-45 Sasha reservations" not in s:
        a_imp = "import { apiUrl, apiHeaders } from '@/lib/api'\n"
        a_jsx = "      <div className=\"lw-when\">Where you've been</div>\n"
        if a_imp not in s or a_jsx not in s:
            raise SystemExit("⛔ STOP: YouPanel's anchors changed in this CTO drop — Sasha's reservations were NOT re-applied. Place them by hand.")
        s = s.replace(a_imp, a_imp + "import SashaReservations from './SashaReservations'  // S-45, Stage B re-applies\n", 1)
        s = s.replace(a_jsx, "      {/* S-45 Sasha reservations: repo-only component. CTO zips drop this; Stage B re-applies it. */}\n      <SashaReservations />\n\n" + a_jsx, 1)
        p.write_text(s); print("reservations re-applied")
    else: print("reservations already present")
    PY
    grep -n "SashaReservations" frontend/app/components/workspace/YouPanel.tsx
The build refuses if this is skipped: prebuild (scripts/check-outcome-surfaces.mjs) fails when YouPanel lacks "S-45 Sasha reservations".

Import test:
    cd ~/Projects/sasha-travel/backend && source venv/bin/activate && \
    python3 -c "from app.main import app; print('BACKEND LOADS CLEAN')" 2>&1 | tail -6

Stage C — frontend build gate:
    cd ~/Projects/sasha-travel/frontend && npm install 2>&1 | tail -3 && \
    npm run build 2>&1 | tail -25
Must produce 18 routes with no compile errors (17 until S-25 added /booking-helper).
`npm run build` first runs `prebuild` = scripts/check-outcome-surfaces.mjs (P807mt): it fails the build if an outcome
surface has a silent grey button, an unobserved promise, or "Nothing yet" drawn from an empty list. Do not bypass it.

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
    echo -n "booking: " && curl -s https://sasha-travel-production.up.railway.app/api/booking/health
Expected: backend 200, conductor 422, CORS header echoes project.kanoe.ai, vietnam2 200, and booking prints
JSON with "mounted":true and "matches_pinned":true ("provisioned":true once the booking SQL has been run).
⚠ booking printing {"detail":"Not Found"} means the Stage B mount line was lost — re-apply it and redeploy.
    echo -n "hand-off: " && curl -s -o /tmp/ho.json -w "%{http_code} " -X POST https://sasha-travel-production.up.railway.app/api/agents/conductor -H "Content-Type: application/json" -H "Origin: https://project.kanoe.ai" -d '{"message":"find me a tattoo studio in Nairobi"}' && (grep -o '"booking_find":{[^}]*}' /tmp/ho.json || echo "⛔ HAND-OFF MISSING — the Stage B conductor hook was lost; re-apply it and redeploy")
    echo -n "drafts: " && curl -s https://sasha-travel-production.up.railway.app/api/booking/health | python3 -c "import sys,json; h=json.load(sys.stdin).get('chat_hooks') or {}; print('ok' if h.get('booking_drafts') and h.get('in_order') else '⛔ BOOKING DRAFTS MISSING — the S-64 Stage B conductor hook was lost; re-apply it and redeploy', h)"
Expected: 200 and "booking_find":{"what":"tattoo studio","where":"Nairobi"} (S-66: the Psi console link is retired); drafts prints ok. (401 means CONDUCTOR_API_SECRET is
set: add -H "X-Client-Key: <the frontend's NEXT_PUBLIC_CLIENT_KEY>".)

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
