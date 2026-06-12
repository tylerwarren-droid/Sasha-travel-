# Session notes — June 12, 2026

## Agents built today — 10 new, total now 23

### Phase 1 — Claude + web search (no external API required)
visa, currency, weather, emergency, language, packing, family

### Phase 2 — web search + booking links
airport_transfer, experiences, coworking, insurance, loyalty

### 23rd agent
api_assimilation — discovers and ranks travel APIs by vertical/region/use-case, generates working integration code in Python or TypeScript

---

## Key fixes

### Conductor timeout
Increased from 5s → 30s (`run_with_timeout`). Was silently killing every new agent — web search takes 8–15s and the timeout was never surfaced as an error, responses just came back empty.

### Anthropic API key
Fixed to point to Default/AppliedDiligence workspace with auto-reload. Previous key was pointing to the wrong workspace.

### Browserbase
Signed up — API key and project ID added to Railway environment. Playwright removed from requirements.txt (local Chromium too heavy for Railway free tier). Full Browserbase implementation (restaurant `book_via_website`, visa `start_visa_application`) needs to be rebuilt using the remote API only — no local Playwright.

### Model costs
All agents use `claude-haiku-4-5` for tool calls (web search loop). Only the conductor merge step uses Sonnet. Haiku is ~20x cheaper than Sonnet for the tool call loops that run on every agent.

---

## Architecture insight

**Agents as APIs**: Claude + web search covers the entire world where no REST APIs exist. APIs plug in when available (Duffel for flights, RateHawk for hotels). Agents are the global fallback for everything else.

**Unit economics at scale**: Agent routing is ~13x cheaper than monolithic Claude calls. Each specialist agent fires only when its keywords match, runs haiku for tool calls, and merges at the conductor level with a single Sonnet call.

**Integration path**: Start with agent (instant, global coverage) → apply for the relevant REST API → swap the web search tool for a real API call when approved. The agent wrapper stays the same.

---

## Security incident

Resend API key and Supabase service role JWT were exposed when the repo was temporarily made public for HeyGen source code review. Both rotated and updated in Railway environment variables. Repo is currently still public for ongoing HeyGen debugging — **make private once HeyGen confirms they have what they need.**

---

## Open items

### HeyGen voice echo
HeyGen reviewing source code for the gate-opens-during-avatar-speech bug. Current architecture: timer-based gate (`safetyTimerRef` + `trailingTimerRef`), `speech_final` gating on Deepgram, content-based echo filter (word overlap ≥70% against `lastRepeatTextRef`). Waiting on their diagnosis.

### Railway
Credits low — top up needed before next deploy.

### Browserbase
Re-implement `book_via_website` (restaurant) and `start_visa_application` (visa) using Browserbase remote API only. No local Chromium. Pattern: HTTP calls to Browserbase API → get session CDP URL → Playwright connects remotely (or use Browserbase's own JS SDK).

### API applications to submit
Per the api_assimilation agent's own recommendations:
- **Duffel** — flights search and booking, recommended starting point (easy approval, good sandbox, modern API)
- **SafetyWing** and/or **InsureMyTrip** — affiliate/partner APIs for insurance agent
- **Viator / GetYourGuide** — affiliate APIs for experiences agent (currently web-search only)
- **GetTransfer / Blacklane** — transfer booking APIs

### Next agents to build (pending API approval)
- `flights_agent` — Duffel API
- `hotels_agent` — RateHawk or similar

---

## Cumulative agent list (23 total)
golf, booking_confirmation, beauty, health, dog_walking, foto, restaurant, smart_sasha, credit_card, car_rental, visa, currency, weather, emergency, language, packing, family, airport_transfer, experiences, coworking, insurance, loyalty, api_assimilation
