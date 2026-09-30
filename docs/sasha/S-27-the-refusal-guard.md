# S-27 — Replacing the refusal-half guard with "read the page; if unclear, show its words"

**Filed:** 29 September 2026, night. **Report first; nothing built yet.**

## 0. Blunt answer

- **The founder's correction is right, and the change is small in the code:** remove one guard in three places,
  keep the page's words when the reading is "neither", and let the user's reading of those words be recorded
  as **theirs**.
- ⚠ **It changes nothing about tomorrow unless live is turned on.** The guard applies to **live** tasks only.
  Live submission is **off** (`LIVE_SUBMIT_ENABLED = false` in the helper, `LIVE_ISSUE_ENABLED = False` on the
  server), and stays off without his explicit word. A dry run never reached the guard.
- ⚠ **It does not make an unmapped venue bookable.** It fixes **reading** the page after. **Filling** the form
  still needs a map, because the approval is bound to exact fields and values **before** the page is opened
  (§3). That, not the guard, is the "one restaurant vs. a tattoo parlour in Istanbul" distance.
- ⚠ **Railway is still not serving S-26** (the Stage E probe failed). Nothing on the server side of this change
  can go live until that is resolved.

## 1. Where the guard lives today

| place | what it does |
|---|---|
| `lib/agapi/portable/refusal-standing.js` (Applied Diligence) | the rule itself: `live_without_established_refusal`, `live_refusal_basis_not_accepted`, `live_refusal_without_source`, `live_on_a_placeholder_refusal`, `live_refusal_pattern_invalid`, `live_refusal_selector_unsupported` |
| `extension-sasha/lib/vendor/refusal-standing.js` | **a byte-for-byte copy** in the helper, asserted identical by `scripts/portable-vendored.test.mjs` |
| `backend/booking_signer/issue.py` `live_refusal_check` (Sasha) | the signer's step 1, **parity-tested** case by case against the reference signer |
| `docs/sasha-contract/README.md` §3.5 step 1 | the contract that states it |

**And the reading after submit** (`extension-sasha/sw.js:246–275`, `portable/page-after.js`):
- refusals are checked first, then acceptance, then **neither**;
- ⚠ **on "neither", the page's words are thrown away** (`quoted: ""`), and the server records `unreachable`
  with no words;
- so today, the one reading the founder wants shown to the user is the one we discard.

## 2. The replacement

**Read the page after, and then:**

| the page | outcome | on the record |
|---|---|---|
| matches **accepted** | **the venue's ceiling**: `confirmed` where the form confirms with a reference, `requested` where it only takes a request (Psi) | the page's words, and the **reference**, extracted by `reference_pattern` |
| matches a **known refusal** | `declined` | the page's words |
| matches **neither** | **`page_says`**: a new outcome, *"the page answered; read it"*. **Not a guess, not a refusal** | **the page's own words**, bounded (the visible text of the result region, capped at ~1,500 characters), shown to the user |
| the user reads them and answers | **their** answer: `requested`, `confirmed` or `declined` | a **second** attempt row, `observed_by = "the user, reading the page's own words"`. **Appended, never rewriting** the device's reading |
| the page **did not load / could not be read** | `unreachable` / `failed`, as now | unchanged: a genuinely unreachable page stays unreachable |

**Kept, unchanged:**
- **the payment stop**, which lives in the helper, before and after submit;
- **the approval bound to the read-back hash**;
- **the request originating on the user's device**;
- **CAPTCHA never worked around**;
- **the email check for live** (a confirmation must be able to arrive).

**What the "neither" path needs, concretely:**
1. **The helper** (`sw.js`, `page-after.js`): on "neither", capture the page's visible text, bounded, as
   `quoted`, instead of `""`.
2. **The server** (`outcome.py`): "neither" → `page_says`, with `venue_words` kept, and a line for the user:
   *"Their page said this — read it and tell me: did it work?"*
3. **A route** `POST /api/booking/reservations/{id}/reading` `{verdict}`: records the user's reading as an
   appended attempt, and moves the trip item's status.
4. **The page**: shows the words and three buttons: *It worked* · *It was declined* · *I can't tell*.
   ⚠ The last one keeps it `page_says`, never a guess.
5. **Schema**: `page_says` in both status CHECKs. One small SQL block for chat.

**Remove the guard:** in `portable/refusal-standing.js` (and its vendored copy), `issue.py`, the contract, and
the parity fixture.
- ⚠ **The reference signer's parity cases that expect `live_*` refusals are rewritten, not deleted.** They
  become cases that **sign**, so parity still pins the new behaviour.
- The helper must be **reloaded** (unpacked) to pick this up.

**Two repos, two sessions' surfaces:**
- the helper and `portable/` live in **Applied Diligence** (S-series owns them);
- the signer and the page live in **Sasha**.

Both are this session's to change, and both suites (`npm test` in AD; the Python suites and `tsc` in Sasha)
gate it. **Estimate: most of an evening, done carefully**, including the end-to-end run with a "neither" page
and a user's reading.

## 3. The question that matters: a venue with no map

**Today a map must exist first. The guard is not why; the approval is.**
- The yes is bound to `filled_values_sha256`: every **selector = value** line, in the venue's own formats,
  hashed **before the page is opened**.
- The helper fills **exactly** those, and stops if the page does not match (`field_not_found`,
  `option_not_served`, `payload_differs_from_approved`).
- So the server has to know the fields, their selectors and their formats **before** the read-back. Today that
  knowledge is a **form map** (Magellan) and a **venue builder** (`venues.py`).

**Could the fields be mapped live from served HTML? Yes, in principle, as a two-phase run.** It is **not
tonight**:
1. **Survey:** the helper opens the venue's page on the user's device, **reads only**, and returns the form's
   structure: fields, labels, types, required marks, options and the hidden envelope. That is device-observed,
   like a report.
2. **Map:** the server matches the guest's particulars to those fields and formats (date format from
   `type=date` / placeholder / options; time from served options), builds the read-back **from the real
   labels**, and asks for the yes. **The approval then binds to what the form really is.**
3. **Run:** the signed task fills exactly that, as today; then the reading, with "neither" shown to the user.

**What it reaches, and what it does not:**

| venue's booking | survey + map works? |
|---|---|
| a plain served HTML form: name, date, time, party, email, phone | ✅ **yes**. This is the tattoo parlour in Istanbul, **if** its form is served in the page |
| a JavaScript date/time picker over a text field | ◐ often: fill the underlying field, and the helper already refuses if the page rewrites it |
| a multi-step form, or a form that appears after a click (the Booked plugin: *"a click is an act"*) | ⛔ no: each step is an act the approval did not cover |
| a platform widget or iframe (TheFork, OpenTable…) | ⛔ no: that is the platform path (S-27 anywhere §2) |
| a CAPTCHA | ⛔ never |

**Cost:** the form-reading core exists (`lib/agapi/forms` in AD: classify, form map, render). Porting a survey
into the helper, a generic mapper and read-back on the server, and tests is **about a week**. With it plus
tonight's change, the reach becomes **"any venue whose booking is a served form"**, about 1 in 30 restaurants,
and more in other trades.

## 4. Recommendation

- **Tonight:** build §2, if the founder says go. It makes the reading honest for every venue and removes a
  guard that blocks the common case.
- ⚠ **It does not change tomorrow's demo.** Live is off, and no venue but Psi has a map. Turning live on at
  Psi is his explicit decision, with the untested-path caveats (S-26 §4).
- **Before any of it goes live:** Railway must be serving S-26.
- **The week:** §3's survey and map. That is the step from one restaurant to any served form.
