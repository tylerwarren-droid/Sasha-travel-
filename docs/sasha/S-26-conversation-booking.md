# S-26 — Sasha booking in conversation: what exists, what an evening carries, and what live would take

**Filed:** 29 September 2026. **Report only; nothing built.** Live submission is **off**, and stays off
without the founder saying so explicitly.

## 0. Blunt answer

- **Tonight, honestly:** Sasha, in conversation on `/vietnam`, recognises *"book a table at Psi"*, and
  **hands off to her booking tab** (`/booking-helper`, pre-filled). The five lines are read back there, the
  yes is given there, and the helper runs there. **Psi only, hardcoded. Dry run.** Roughly an evening's
  careful work, and testable tonight with the rig. It is also exactly **S-12's decided option B**: *"Sasha
  opens in her own tab when booking."*
- **Not tonight, about a week:** the whole booking inside the conversation. That means gathering the
  particulars over several turns, the avatar **speaking** the five lines, a **spoken** yes, the helper driven
  from `/vietnam` itself, and the outcome spoken back. It also means making all of that **survive a CTO
  drop**: every file it touches is the CTO's (§2).
- **The demo floor, which works now:** the dry run on `/booking-helper`, against real Psi.

## 1. What exists, and what does not

| a conversation needs | exists? | where |
|---|---|---|
| recognise a booking request | ◐ | the conductor has restaurant **search** routing (`RESTAURANT_WORDS`, `RESTAURANT_ACTION_WORDS`, `conductor.py:144–241`), and it yields restaurant **cards**. **Nothing turns "book it" into a booking task** |
| a fulfilment to point at | ⛔ **dead code** | `restaurant_agent.py` ("books by email and phone": `send_reservation_email`, Bland) **has no callers anywhere**. The conductor never imports it. There is no live booking fulfilment to redirect; the helper would be the first |
| gather venue, date, time, party, name, email, phone | ◐ | `/vietnam` already collects **typed** booking details: *"names/emails are unreliable over voice STT, so collect them here"* (`vietnam/page.tsx:143`). Date, time and party are not collected anywhere as structured values |
| the five read-back lines | ✅ | `POST /api/booking/intents` returns them, built by the server from the particulars (S-17) |
| a yes that binds to the same hash | ✅ **by construction** | the **server** binds the approval to the read-back and payload hashes it recorded (`routes.py`, issue). The page supplies only *how* and *what was said*. A spoken yes is `{how: "voice", said: "<transcript>"}`, and it binds to **the same hash** as the button, because neither page nor conversation ever computes it. ⚠ `said` must be non-empty for voice, or the signer refuses (`approval_voice_without_words`) |
| hand the signed task to the helper | ✅ | on `/booking-helper`. Only from a **top-level** tab on `project.kanoe.ai` (`/vietnam` qualifies; the Demo tab frames it and is refused) |
| say what came back | ✅ | the server's `say` (contract §8 wording) and the helper's `user_words` (`extension-sasha/lib/words.js`) come back in every report |
| ⛔ **the payment stop** | ✅ **untouchable** | it lives in the **helper**: checked before submit (`page.js:159`) and on the page after (`sw.js:273`), with *"a payment always needs its own yes"* (`words.js:60`). No conversation code can reach around it |
| chat UI acting on a conductor `action` | ✅ | `SashaChat.tsx:418–430` dispatches `action` (`confirm_card`, `await_payment`, …) to page callbacks. A new action is one more branch |

## 2. ⚠ The constraint that decides the size: every surface is the CTO's

`conductor.py` (2,562 lines), `SashaChat.tsx` and `vietnam/page.tsx` are all in the CTO's zip, so **Stage A
overwrites them on every drop.** That is what happened to the Duffel edits. Anything wired into them tonight
must be:
- **small and anchored**, so Stage B can re-apply it the way it re-applies CORS and the booking mount; and
- **listed in `CLAUDE.md`**, or it silently vanishes at the next drop, which is exactly the failure this estate
  keeps undoing.

A full in-conversation booking spreads across all three files. That is the week; a hand-off touches one line
in each.

## 3. Tonight's narrow version (option B), if the founder says go

1. **Conductor, one anchored hook** at the top of intent routing: *book / reserve / a table* **and** *Psi* →
   return `{response: "I'll open my booking tab for Restaurante Psi — read it through and say yes there.",
   action: "open_booking", booking: {venue: "restaurante-psi", date, time, party}}`. The date, time and party
   come from the message **if stated plainly**, and are left empty otherwise; the tab asks. **No LLM
   guessing**: a wrong date read aloud and approved is a real harm.
2. **SashaChat, one branch:** `action === "open_booking"` → `window.open("/booking-helper?venue=…&date=…",
   "_blank")`. It is a new top-level tab, which the helper accepts.
3. **`/booking-helper` (repo-only):** reads the query into the form. **Name, email and phone are typed there**,
   as `/vietnam` already does for voice. Then the existing flow runs: Prepare → the five lines → Yes → helper →
   report → the words.
4. **Test:** the rig harness already drives `/booking-helper` end to end. Add the pre-fill, and one curl at the
   conductor for the hand-off.

**What this does not do:** the avatar does not speak the five lines; the yes is a button in her tab, not a
spoken yes. **The approval is still bound to the exact words.**

## 4. Step 2 — what turning live on would take, and what would happen

**The switches, all three required:**
1. `LIVE_SUBMIT_ENABLED = true` in the helper (`extension-sasha/lib/config.js`), and reload the unpacked
   helper.
2. `LIVE_ISSUE_ENABLED = True` in `backend/booking_signer/routes.py`, then commit and deploy.
3. A **real, deliverable email** in the booking: the signer's email check refuses `example.org` and similar for
   live.

Psi's refusal half is established (`reference_install`), so the signer **would sign** a live task.

**What would actually happen:** the helper opens Psi's page in the founder's Chrome, fills it, **presses
submit**, and reads the page after:
- **A real booking request lands at Restaurante Psi.** Their staff see it, and the confirmation email goes to
  the address given. **It is a real booking**: it must be one he intends, or cancels.
- The page after decides **requested / declined / unreachable / failed**, and a `booking_attempts` row plus the
  trip item's status record it. `confirmed` is unreachable; Psi confirms later, by email.

**What is untested on that path, because nothing has ever been sent:**

| untested | why it matters |
|---|---|
| **the submit itself** at the real Psi | only ever run against a fixture copy of the form (23 Sept map) |
| **reading Psi's live page after submit** | the accepted/refused patterns come from our **reference install** of the plugin, *"NOT observed at Psi"*. A mismatch reads as `unreachable`, correctly, but the demo would say *"I couldn't read their reply"* |
| **payment detection at Psi** | tested on fixtures only |
| **the live outcome write path** (`booking_attempts` insert, trip-item status) | tested in Postgres suites and with synthetic signed reports; **never** from a real sent report |
| **the confirmation email** | nothing in Sasha receives it (S-18). The only confirmation is in the founder's inbox |

## 5. What the demo looks like at each level

| level | what the room sees | risk | tonight? |
|---|---|---|---|
| **dry run** (now) | he books Psi on Sasha's booking tab; his Chrome opens Psi's **real** page, fills it, and **stops before sending**: *"Nothing was sent."* | none: nothing reaches the restaurant | ✅ **works now**, if Psi's live form still matches (else a named stop, e.g. `option_not_served`) |
| **dry run, started in conversation** (§3) | he asks Sasha on `/vietnam`, she opens her booking tab pre-filled, then as above | low: the hand-off is one branch each in two CTO files, and dry run | ◐ **an evening**, on his go |
| **live at Psi** | as dry run, then **the request really goes**; Psi's page says *"your booking request is waiting to be confirmed"*; Sasha says **REQUESTED, not booked** | ⚠ a real request to a real restaurant, on an **untested submit path** (§4). A misread reads as *"couldn't read their reply"* | ⚠ possible tonight **only** on his explicit word, with a table he actually wants |
| **live at a venue he controls** | the same, against a booking form he owns, so a test booking harms no one | low for the venue; but it needs **that site to exist** (the same plugin, public https), and a **second venue entry** in `venues.py` (the Psi builder is hardcoded) | ⛔ **not tonight** unless the site already exists |
