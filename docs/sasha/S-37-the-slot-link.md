# S-37 — The slot link: Sasha prepares the booking, the guest confirms it on the platform with one press

**Filed:** 30 September 2026. **Specification only; nothing built.** Every platform fact here comes from what the
founder captures in his own browser. ⛔ Nothing in this design sends a request to a booking platform from our
machines: not to read, not to check, not to learn.

## 0. Blunt answer

**The shape is right, and it is the one that is permitted everywhere:**
- Sasha prepares; the guest presses the platform's own button, in their own browser, under their own name.
- No platform terms are accepted by us, nothing is automated on their side, and the confirmation is theirs.

⚠ **One correction to the brief: "Sasha finds the slot" is not possible without touching the platform.**
- Live availability exists only on the platform.
- From our machines we can neither read it nor check it, and a model's guess at it is the fabrication rule 4
  forbids.
- **So she does not find a slot. She builds a link to the guest's date, time and party, already filled in.** The
  platform's own page, opened by the guest, **shows whether it is free**, and offers the nearest times if it is not.
- She says exactly that: *"here's their page with Thursday at 8 for four filled in"*, **never** *"I found you a
  table"*.

**This is also honest about the one press.**
- **Where the platform's page accepts the date, time and party in its URL**, the guest lands on the slot and presses
  Reserve. **That is one press, plus the platform's own sign-in or phone step.** The phone step is theirs, not ours
  (S-35's SMS problem disappears).
- **Where the URL does not carry them**, the guest lands on the venue's page and picks there. **We say that, too.**

## 1. What the link is

**It is a URL on the platform's own site, for this venue, with the guest's booking in its query string.** For
illustration only, not verified:

```
https://www.<platform>/<venue path>?<date param>=2026-10-08&<time param>=20:00&<party param>=4
```

**Three parts. Each has a source that never touches the platform from here:**

| part | where it comes from | touches the platform from our machines? |
|---|---|---|
| **the platform's host and URL pattern** (which parameters carry date, time and party, and their formats) | **a link recipe per platform**, written from URLs the **founder copies from his own browser's address bar** at each step (S-35 §3.2), and **checked by him once**: he opens the built link and sees the slot filled | **no.** He browses as a person; we read what he pastes |
| **the venue's identity on that platform** (its slug, or its numeric id) | **what Magellan already reads on the venue's own site** (S-36): the "Reserve" link's `href`, or the widget embed's `src`, which carries the venue's platform id. The `platform` fact already keeps both (`detail.link`, `detail.embed`). Or the Google listing's `websiteUri`, when that is the platform page | **no.** We read the venue's own site. The platform URL is **a string on it**, never fetched |
| **the guest's date, time and party** | the particulars the guest gave | no |

⚠ **A venue whose site does not link its platform page gets no link.** Sasha says so: *"They book through OpenTable,
but their site doesn't link their page — search OpenTable for La Contra, Madrid."* **No search from us, and no
model's guess at a URL.** A guessed URL could open the wrong restaurant, which is a wrong booking in the guest's
name.

## 2. The link recipes

A recipe is **data in code, with its provenance**, never inferred:

```
{ platform: "OpenTable", host_pattern: "opentable.es",
  venue_id_from: "embed query parameter 'rid'"  |  "link path segment",
  url_template: "...{venue}...{date}...{time}...{party}...",
  formats: { date: "YYYY-MM-DD", time: "HH:MM", party: "integer" },
  observed: { by: "the founder, in his own browser", on: "2026-10-0x", captures: ["…/01-date.url", …] },
  verified: { by: "the founder", on: "…", what: "the built link opened with the slot filled" } }
```

**Rules:**
- **No recipe, no link**: the guest gets the venue's platform page as linked, without the slot.
- **Unverified recipe, no slot claim**: *"their page — pick Thursday at 8 there"*.
- **A recipe is re-verified when the platform changes its URLs.** The guest reporting *"the link didn't fill it"* is
  the signal, recorded as theirs.
- **The parameters are URL-encoded, and only the four values go in.** No tracking, no affiliate code: we have no
  agreement with the platform, and adding one would be accepting terms.

## 3. What she says

**The read-back** (the yes binds to it, as on every rung, but **the yes here opens a link; it books nothing**):

> *"La Contra takes bookings through OpenTable. I can't book there for you, but here's their OpenTable page with
> **Thursday 8 October at 8 pm, for four**, already filled in. If it's free, press **Reserve** and it's booked in your
> name — OpenTable will send the confirmation to you. If 8 isn't free, their page will show you what is."*

**When the recipe is unverified, or the link carries no slot:**

> *"Here's La Contra's OpenTable page — pick Thursday at 8 for four there."*

**Always said:**
- **who books**: the guest, in their own name;
- **who confirms**: the platform, to the guest;
- **that nothing has been reserved yet.**

**The status line** until the guest comes back: *"La Contra — link sent · not booked yet."* ⚠ Never "requested" and
never "pending confirmation": **nothing has been asked of the venue.**

## 4. What happens after, since the confirmation goes to the guest

The platform confirms to **the guest**. Sasha learns it in one of three ways, in order of evidence:

| how | what Sasha records | status |
|---|---|---|
| **1. The guest forwards the platform's confirmation email** to `act-{id}@<inbound>`, the address she shows with the link (*"forward me the confirmation and I'll put it in your trip"*) | S-36's inbound path, **svix-verified, matched by address**. **The platform's own words** are shown and kept; the **reference is extracted only by the recipe's known pattern**, else shown for the guest to read | **`confirmed`**, `observed_by: "the platform's confirmation, forwarded by the guest"` |
| **2. The guest says "done"** (a button, or in chat) | the guest's word, **as theirs** | a new status, **`guest_booked`**: *"Booked by you on OpenTable — forward the confirmation to add the reference."* ⚠ Not `confirmed`: nobody but the guest has said so |
| **3. Nothing** | nothing | stays **`link_sent`**. After the slot's time has passed: *"I never heard whether you booked La Contra."* **Never** an assumed booking, and **never** an assumed cancellation |

**Why forwarding is the right main path:**
- the confirmation is the platform's own, carries the reference, and is evidence;
- it reuses the S-36 inbound path unchanged;
- it keeps Sasha out of the guest's inbox. **No mailbox access is asked for.**

⚠ **The reservation is the guest's.** Changes and cancellations go through the platform, by the guest. The itinerary
says so beside the reference.

## 5. Where it sits on the ladder

- **After** the form rung (only where Sasha may fill it: Psi).
- **Before** phone and email **when the venue books through a platform.** The platform is the venue's own channel,
  and a call would only be told *"book online"*.

Her sentence (S-36's chooser) gains one option:

> *"They book through OpenTable. I'll send you their page with your table filled in — one press. Or I can call them.
> Which?"*

## 6. What it needs, honestly

| piece | who | size |
|---|---|---|
| **captures per platform**: the address-bar URL at each step, and the venue page's "Reserve" link and embed `src`, from his own browser | **the founder**, per platform, once | 15 min each (OpenTable first; TheFork from mobile data, **never his home network**, which is blocked) |
| **recipe verification**: open the built link, see the slot filled | the founder, once per platform | minutes |
| recipes as data plus the builder; the platform fact extended with the venue id from `link` or `embed` | build | ½ day |
| the chooser option, the read-back, the `link_sent` / `guest_booked` statuses (**SQL for chat**: two statuses on `trip_items`) | build | ½ day |
| the "forward me the confirmation" path: S-36 inbound plus per-platform reference patterns (from a confirmation the founder forwards himself once) | build | ½ day |
| **total** | | **1½–2 days of build**, plus the founder's captures |

**What it cannot do:**
- know a slot is free;
- book for the guest;
- see a booking the guest does not tell her about.

All three are stated to the guest, not hidden.

## 7. Built (30 September) — not committed

| file | what |
|---|---|
| `booking_signer/slot_link.py` | the venue's platform page **from a `platform` fact's `detail.link`** (https, on that platform's own host, read on the venue's site); `RECIPES` — **empty**; `build()`; the read-back |
| `booking_signer/ladder.py` | the chooser gains the **link** rung, offered first when the venue links its platform page: *"They book through OpenTable. I'll send you their OpenTable page to book it yourself — or I'll call them. Which?"*. A platform its site doesn't link stays a fact: *"…I never guess one"* |
| `booking_signer/ladder_routes.py` | `POST /links` (read-back + URL; a `url` in the request is refused), `POST /links/{id}/opened` (bound to the read-back hash → `link_sent`), `POST /links/{id}/booked` (→ `guest_booked`, **the guest's word**), `GET /links/{id}`; the inbound webhook routes a forward to `act-{link_id}@…` as a **confirmation** — **counted only if it names the venue or the platform**, otherwise kept and shown, never counted |
| `booking_signer/ladder_store.py` | links and confirmations, memory and Postgres; `confirmed` records a `booking_attempts` row (`web_form`, observed by "the platform's confirmation, forwarded by the guest") |
| `sql/005_slot_links.sql` | `booking_links`, `booking_link_confirmations`, and `link_sent` / `guest_booked` on `trip_items`. **For the founder to run**, after 004 |
| `frontend/…/Ladder.tsx` | "Their OpenTable page" → the read-back → **Open their page** (a real link — the guest's press; opening records `link_sent`) → **I booked it** → **Check for the confirmation** |
| **the error fix** | `StorageUnavailable.detail` and `rehint()`: the rule is said **once**, in its own field, and the message names the block that creates the missing table (001/003/004/005), not the first one |

**Live after SQL 005:** the link rung for any venue whose own site links its platform page, on every platform — **without the slot filled** (no recipe exists), so she says *"pick Thursday at 8 there"*. **Forwarded confirmations** need the inbound half of email: `SASHA_INBOUND_DOMAIN` (MX to Resend) and `RESEND_WEBHOOK_SECRET`; without them she says *"tell me when you've booked"*, and "I booked it" records the guest's word.

**Slot pre-filled:** per platform, after the founder's captures and his one-time check (§2, §6).

**Tests:** 177 OK (14 new), memory and Postgres with 001–005; frontend tsc 0, 3 surfaces clean.
