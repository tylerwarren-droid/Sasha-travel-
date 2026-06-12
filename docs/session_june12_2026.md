# Session notes — June 12, 2026

## Shipped today

### 7 new agents (backend/app/services/)
visa_agent.py, currency_agent.py, weather_agent.py, emergency_agent.py, language_agent.py, packing_agent.py, family_agent.py — all wired into conductor.py with keyword dispatch and 30s timeout.

**Total agents now live: 17**

### Conductor changes
- Timeout increased from 5s → 30s (`run_with_timeout`) to accommodate web search latency
- Full traceback logging added to `run_with_timeout` exception handler and `run_visa_intent`

### Railway / build fixes
- Removed `playwright` and `browserbase` from requirements.txt — local Chromium too heavy for Railway free tier
- Deleted nixpacks.toml
- Added Procfile (`web: uvicorn app.main:app --host 0.0.0.0 --port $PORT`) and runtime.txt (`python-3.11`)

---

## Open items

### Browserbase
- Account created, API key in hand
- Playwright-based implementation written and then reverted (no local Chromium on Railway)
- **Next:** re-implement using Browserbase remote API only — no local Playwright/Chromium needed
- Targets: restaurant `book_via_website` and visa `start_visa_application`

### Anthropic API
- API key fixed to point to Default/AppliedDiligence workspace with auto-reload

### HeyGen voice echo
- HeyGen reviewing source code for the speaker bleed / echo issue
- Current architecture: timer-based gate (safetyTimerRef + trailingTimerRef), speech_final gating on Deepgram, content-based echo filter (word overlap ≥70% against lastRepeatTextRef)

### GitHub
- Repository should be made private

### Railway
- Needs credit card / balance top-up for continued deployments

---

## Next session priorities

1. **Duffel API** — flight search and booking
2. **Travel insurance** — SafetyWing and/or InsureMyTrip integration
3. **Browserbase remote API** — re-add web form filling to restaurant and visa agents without local Chromium
4. **Phase 2 agents** — multi-tenant client config (clients table, TenantMiddleware already scaffolded)
