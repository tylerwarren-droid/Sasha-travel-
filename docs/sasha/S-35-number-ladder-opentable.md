# S-35 — Sasha's number, the ladder, OpenTable. Report before building each

**Filed:** 30 September 2026. **Report only; nothing built.**

⛔ **Standing order, saved as a memory:** no request to any booking platform (TheFork, OpenTable, …) from this
machine or the founder's network, ever. TheFork's block on his home IP (`84.233.199.85`) came from our S-30 probes.
OpenTable is mapped only from markup he captures (§3).

Vendor facts below are from Bland's and Twilio's own documentation, read today. Nothing was bought, called or texted.

## 1. A phone number for Sasha

### 1.1 What the providers actually sell

| | Bland | Twilio |
|---|---|---|
| **numbers** | **US only** documented. *Agent Phone Plan*: **$29.99/month**, one US local number, inbound calls, SMS. *"Calls, transfers, and SMS are limited to US and Canada destinations"* | most countries, from **$1.15/month**. Each country has its own regulatory requirements |
| **receives SMS** | yes, on Bland numbers. **SMS is US-only and needs an A2P campaign registration**; BYOT self-service A2P is "coming soon" | yes; Spain lists **two-way SMS supported** |
| **inbound calls** | yes: an AI agent answers (a pathway or prompt) | yes: a webhook decides (forward it, or hand it to Bland) |
| **bring your own number** | **yes**: Twilio numbers can be imported (BYOT) and then used by Bland for calls, and for SMS with a Messaging Service SID | — |

**So:** Bland alone gives a **US** number. For anything else, **Twilio is needed**, and Bland can drive calls through
the imported number.

### 1.2 One number for SMS and calls?

- **Yes**, where the number type has both capabilities (a US or UK mobile Twilio number does).
- **Spain is the awkward case:**
  - **Local (geographic) numbers:** Twilio requires a **Spanish CIF** and **an address inside the prefix's region**.
    Their SMS capability is not stated in Twilio's Spain pages.
  - **Mobile numbers:** under Spain's 2025 rule, *"Spanish Mobile numbers can't be used for unsolicited marketing or
    customer service calls"*. Carriers may block them as caller ID, and Twilio recommends a landline or toll-free
    number.
  - **A Spanish number is not needed to CALL a Spanish venue.** Bland places the call, and a foreign caller ID is
    allowed. It would only make callbacks local and look familiar. **It needs a Spanish company (CIF) with an
    address in the area.** Without one, a Spanish landline is not available.

### 1.3 ⚠ The OpenTable SMS code: what is unknown and must be tested, not assumed

1. **Whether opentable.es sends its code to a non-Spanish number, and to a VoIP number.** Many verification senders
   refuse VoIP ranges, and Twilio numbers are VoIP. **One test settles it** (step 4 below).
2. **Sasha becomes OpenTable's contact of record for that diner**, receiving reminders and changes, exactly as with
   email. That is the intent. ⚠ Whether OpenTable's terms allow a concierge's number at its verification step is
   **the terms read S-30 already asked for**.

### 1.4 The callback line

- When a venue rings Sasha's number back, **a Bland inbound agent answers**: *"Hello, this is Sasha, an AI assistant
  for [the guest]…"*.
- It takes the message **without recording audio**. The transcript comes to our webhook and is matched **by the
  calling number to the venue we called**, never guessed.
- **A voicemail box would be a recording**, so it is not the default.

### 1.5 Cost, roughly

| item | cost |
|---|---|
| a Twilio number | ~$1–15/month by country |
| SMS | ~$0.01–0.08 per message by country |
| calls | Bland's per-minute rate as today |

Or Bland's US plan at $29.99/month, if a US number turns out to be enough.

### 1.6 The founder's exact steps

1. **Twilio:** sign up at twilio.com, then **upgrade** (add a card). A trial account restricts numbers.
2. **Phone Numbers → Buy a number.** Country: **United Kingdom, mobile** (my suggestion: voice and SMS, receives
   international SMS; Twilio shows its address requirement at purchase). Tick **Voice + SMS**.
   - If the company has a Spanish CIF and address, a Spanish landline can come later, for callbacks.
3. **Railway:** set `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN` and `SASHA_PHONE_NUMBER` **yourself** (names only
   here; never paste values in chat).
4. **The test that settles §1.3.** In **your own browser, on mobile data**:
   - go to an OpenTable booking up to its SMS step, and enter **Sasha's number**;
   - check **Twilio Console → Monitor → Logs → Messaging** for the code;
   - **stop there** and do not complete the booking.

   If the code arrives, the rung works. If not, the answer is a different number type, not code.
5. Then I build (after your go):
   - `POST /api/booking/sms` (Twilio signature verified; stored; the code read from the message, **matched to the
     booking in flight by time and sender**);
   - the inbound-call agent, importing the number into Bland.
   - **About a day.**

## 2. The ladder

### 2.1 What Magellan reads, and what counts as read

**A fact we read** is a number, address or link **present in bytes we fetched from a named source**, kept with:
- the URL;
- `fetched_at`;
- the page hash;
- the snippet.

**A number is not a fact** when a model produced it from a web search. That is exactly the deleted agent's "best
guess".

**Where the facts come from:**

| source | reads | notes |
|---|---|---|
| **the venue's own site** (fetched from Railway, **robots first**; venue sites are not booking platforms) | `tel:`, visible phone numbers, `mailto:`, `wa.me`, a booking form (S-29 roles), a platform widget (`registry.ts` recognition) | a small Python reader in Sasha's backend |
| **Google Places API** (Place Details: `formatted_phone_number`, `website`) | **La Contra's case**: no website, a public number | ⚠ **needs `GOOGLE_PLACES_API_KEY`** (about $0.02 per lookup). Reading Google Maps pages directly would be scraping |

⚠ **Today's restaurant cards carry no website and no phone** (`travel_search.py`). The ladder starts from the name
and the city, which is why the Places lookup matters.

### 2.2 What she says

From what exists, in the ladder's order (S-28):
- *"They have no booking form. I'll call them — or I can email and we wait. Which?"*
- *"…the number on their Google listing, +34 91…"*: the **source is said** in the read-back.

**Rungs today:**

| rung | state |
|---|---|
| form | Psi only; the wizard is not built (S-31) |
| **phone** | **built (S-33)** |
| email | not built |
| WhatsApp (`wa.me`, sent from the user's own phone) | hours |

### 2.3 Wiring S-33 to it

- `CALL_VENUES` becomes **a venue record Magellan read**, stored server-side with its provenance.
- **The request names the venue, never a number** (unchanged).
- The number is normalised to E.164 from the venue's country.

⚠ **Once any public number is callable, the daily ceiling is the only brake, because nobody signs in.** That is up to
**3 calls a day to any restaurant, placed by anyone who finds the page**. Keep the ceiling low until there is
sign-in.

### 2.4 Email, the smallest honest version

1. Sasha reads the email back (to, subject, body), and **the yes binds to its hash**.
2. It is sent through **Resend**, from a verified Sasha domain, with **reply-to `act-{id}@<inbound>`**, and **Resend's
   answer is checked**.
3. Replies arrive through **Resend inbound** (svix-verified webhook), are **matched by the address**, and are shown
   in the venue's own words. Unmatched mail is quarantined.

**The founder's DNS:** SPF and DKIM for the sending domain, **MX** for the inbound subdomain, and the webhook secret
on Railway.

### 2.5 Cost

| piece | estimate |
|---|---|
| contact reader and Places lookup, storage, the choice line, S-33 wired to it | **2–3 days** |
| the email rung | **2–4 days**, plus the DNS |
| WhatsApp | hours |

## 3. OpenTable

### 3.1 The record, corrected

**P807nb** (`docs/P807nb-platforms-by-reach.md`) says:
- line 35: OpenTable *"0 of 32 Madrid … a measured zero"*;
- §3.1: *"Not present … Whatever its form is, it buys nothing in our cities"*.

**That conclusion is wrong.**
- The founder reached **a full OpenTable booking flow for a Madrid restaurant on opentable.es**, 30 September, with
  no challenge at any step.
- **0 of 32 was a sample, not absence.**
- `registry.ts:160–161` states the sample correctly (*"appeared ZERO times in thirty-two venues"*). Only the doc's
  inference overreached.

⚠ **P807nb is untracked and was not written by this session**, so I have not edited it. The correction is handed
over in the TO FILE block (chat reply).

### 3.2 Mapping it without touching it

- **From markup the founder captures**, on whatever network worked for him, **never this machine**.
- **At each wizard stop** (date → time → party → contact → SMS step): DevTools → Elements → right-click `<html>` →
  **Copy → Copy outerHTML** → paste into `~/Desktop/opentable-capture/NN-step.html`.
- **Stop before the final confirm.** At the contact step, use Sasha's number and a dummy name, or none.
- I then map from the files, **offline**: fields and choices per stop, which clicks are reads, where the act is, and
  where the SMS gate sits.
- That feeds S-31's machinery (the click step, reading offers, two-phase approval). **S-31's estimate stands: about 3
  weeks for the machinery**, plus the terms read.
- **The SMS gate needs §1 first.**

## 4. Order and gates

1. **§1: test first** (step 4, five minutes, the founder), then about a day of build.
2. **§2:** needs `GOOGLE_PLACES_API_KEY`, and a yes to "any public number is callable, capped at 3 a day".
3. **§3:** the captures, the terms read, then S-31.
