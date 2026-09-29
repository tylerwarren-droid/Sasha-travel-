# S-31 — The wizard walk: survey, read back real slots, then sign the fill

**Filed:** 29 September 2026, night. **Design only; nothing built.** Grounded in the code read for the S-30
addendum.

## 0. Blunt answer

- **The founder's shape is right, and it moves the danger to one place: the click step.**
  - The survey reads.
  - The user chooses from what was actually read.
  - The fill is signed against a survey the device itself signed.
- ⚠ **One correction the design has to carry.** On many wizards (TheFork, by general knowledge) **the booking
  form does not exist until a slot is chosen**.
  - A survey that "never chooses a slot" stops at the slot picker and cannot see the contact fields.
  - **So: the survey never chooses a slot the user has not picked.** The walk runs in rounds.
    1. Round 1 reads the offered slots.
    2. The user picks.
    3. Round 2 chooses **that** slot and walks on to the form, reading, never filling.
  - On a page like Psi, where choices and fields share one page, round 1 is the only round.
- **What stops "click whatever looks right":**
  - the device never chooses a target;
  - every click is **named in the signed task**: selector, expected text and purpose;
  - clicks come from a **reviewed platform map**, never from a heuristic at run time;
  - anything that does not match exactly is a stop.
- **Cost: about 3 weeks for the machinery**, then **per platform:** an hour's observation, 1–2 days of map, and
  a terms read.
  - ⚠ The machinery is necessary, not sufficient.
  - Whether it is "thousands of venues" is decided by each platform's **terms and bot wall** (S-30), not by
    this build.

## 1. The click step

**The fixed vocabulary gains `click`, and one read step for what is offered** (§2). The rules below are the
whole design; each one refuses on its own.

**What a click names, exactly as `fill` names what it types:**

```
{ step: "click",
  selector: "…",                          // must match exactly ONE visible, enabled element
  expect:   { tag: "button", text: "Continuar" },   // accessible name, compared exactly (trimmed)
  purpose:  "advance" | "choose",          // advance = next/continue/show; choose = the user's picked value
  choose_value?: "2026-10-05" | "19:30" | "2",      // present iff purpose = choose, and it must be the user's pick
  map: { platform: "thefork", version: "…", step_id: "s2.next" } }
```

**The device refuses the click, and the run stops, if any of these holds:**

| # | refusal | why |
|---|---|---|
| 1 | the selector matches **0 or more than 1** visible element | no "the nearest one" |
| 2 | the element's text or tag differs from `expect` | the page changed; the map does not fit |
| 3 | the element **would submit a form** (`type=submit`, or a default button inside a `<form>`) | a submit is an act. ⚠ Some wizards advance by POST; **those stop the survey**, which is correct: each POST is a request to the venue |
| 4 | the element is a **link off the task's origin** | the worker never chooses where to go (the `sw.js` header) |
| 5 | its text matches **the act or payment vocabulary** (book, reserve, confirm, pay, reservar, confirmar, rezervasyon yap, onayla, pagar, bezahlen…), **whatever the map says** | a map error must not be able to press "Confirm" |
| 6 | its text or form carries **a price** (the existing `payment()` rule for a control) | §5 |
| 7 | `purpose: "choose"`, and the value is not the user's pick recorded on the server, or not in the survey's offers | the survey chooses only what the user chose |
| 8 | more clicks than the task lists, or a click not in the list | **no loops, no "click until"**. A cap of 12 per task |

**After every click:** wait for the named `await`, then run the **challenge check**, the **payment check**
(§5) and the **origin check**. Any hit is a stop.

**Where the click list comes from:**
- A **platform map**: one per platform, recorded from an **observation session in a real browser**, reviewed by
  a person, versioned, and fixture-tested.
- **The server may suggest a map; only a person promotes it.**
- **A venue with no map gets a zero-click survey**: read the landing page, nothing else.
- That is the line between "names exactly what it clicks" and "clicks whatever looks right".

**Enforced in the same three places as today:**
- `portable/originates.js` (and its vendored copy);
- `booking_signer/issue.py`;
- `page.js`, which gets a new `click` op. **`page.js` does all eight checks itself**, so a bad signed task still
  cannot press a submit.

## 2. Reading what is OFFERED

**A new read-only op, `read_offers`.** For each control in the stop's named container it returns:

| control | returned | basis |
|---|---|---|
| `<select>` | every option: value, label, `disabled` | served. The same shape as `form-map.ts:68`, so server and device agree |
| radios and checkbox groups | value, label, disabled | served |
| **button groups** (time chips) | text, a value attribute where one is present, enabled or disabled (`disabled`, `aria-disabled`, a class the map names) | ⚠ **per map**: which attribute or class means "not available" is the platform's convention |
| **calendar** | per day cell: the date (from an attribute the map names, or `aria-label` parsed by the map's date format), enabled or disabled, **the month shown** | ⚠ **per map**, never guessed. A calendar reader with no map returns **"calendar seen, not read"**, not a list of days |
| other months | only through `advance` clicks the map names ("next month"), capped | the same click rules |

**Also returned:**
- the **fields** at the stop (the same shape as the booking roles take, S-29), so the read-back can say real
  labels;
- a **hold signal**: countdown text or "held for N minutes". If a choose-click creates a hold, that click is an
  act (§4).

**Bounded:** structure, not the full markup; no user data exists on the device in a survey. The device **signs
the survey report** with its key (the existing `signAsDevice`).

⚠ **An offer is what the page showed at that minute, not a promise.** At fill time, if the slot has gone, the
existing `option_not_served` stop fires, and Sasha says *"19:30 has gone since I looked"*. It never takes the
nearest one.

## 3. The survey task's own refusal: the booking rule, inverted

**A second payload kind, domain-separated:** `kind: "sasha_survey_task"` against `"sasha_booking_task"`, inside
the signed bytes. `verify.js` accepts a payload **only as the kind the run path is running**. A survey signature
can never verify as a booking, or the reverse.

`assertSurveyOnly(task)`, next to `assertOriginatesOnDevice`, **with the same force**:

| rule | refusal |
|---|---|
| steps only from `SURVEY_STEPS = navigate · await · click · read_offers · read_fields · report` | `unknown_step` |
| **`submit` present** | **`survey_must_not_submit`**: *"a survey reads; a submit is an act, and an act needs a read-back and a yes"* |
| **`fill_fields` present, or any value to type** | **`survey_must_not_fill`**: *"a survey carries no user data"* |
| no `read_offers` or `read_fields` | `survey_reads_nothing` |
| every click passes §1 at signing | `click_malformed`, … |
| the same origin, https, not ours | the existing rules, unchanged |

**On the device:**
- **the survey run path never calls `fill` or `submit`**; they are not reachable from it;
- `page.js`'s `click` refuses a submitting element regardless (§1 rule 3);
- a byte-copy test and a parity test (Python and JS) pin both kinds, as today.

**Consent:**
- A survey opens the venue's page on the user's device, so it needs **a light yes**: *"Shall I check what they
  have on the 5th?"* That yes is recorded.
- The **per-origin Chrome grant** is asked as today.
- ⚠ **One grant for a platform's origin covers every venue on it.** That is concentration again.

## 4. The two-phase binding

**The survey report is signed by the device's key** (`signAsDevice`, over the survey task's digest). **The server
cannot forge it; it does not hold that key.** That is the anchor.

**The fill task carries:**

```
survey: { survey_task_digest, survey_report_sha256, device_id, observed_at, map_version }
choices: [{ field/click, value, offered_in: "survey_report_sha256#stop2.times[3]" }]
```

**The signer refuses the fill unless:**
1. the referenced survey report **exists on the server**, and its **device signature verifies** against the
   paired device's public key;
2. `device_id` is the same one (the page was seen on that device);
3. the **origin and map version** equal the survey's, and the fill's `advance` clicks are **the same route** the
   survey walked;
4. **every chosen value is in that survey's offers** (a membership check, not a match) **and was the user's
   pick**;
5. the survey is **fresh** (15 minutes, the task ceiling already in `issue.py`);
6. the survey is **unconsumed**: one fill per survey, marked as used when signed. A retry is a new survey, just as
   a retry is a new intent today.

**The read-back cites it:** *"From their page at 21:14: 19:30 or 21:15 on the 5th. You chose 21:15. In their
'Nombre' field I'll write…"*

**The approval's hash covers those lines**, so the yes binds to a slot that was **seen**.

**Rounds:** round 2 is a survey that also names the round-1 survey and the user's pick. The chain is walked back
to round 1 by the same checks.

**Storage:** a `booking_surveys` table (report, signature, device, origin, map version, consumed_at). SQL for
chat, never applied by me.

## 5. The payment stop inside a walk

- **A card step mid-walk, before any form, is a stop in the survey too.**
- After **every** click and at **every** stop, the existing `payment()` check runs over the whole document: card
  and bank fields, a payment provider's frame. Rule 6 in §1 also refuses **pressing** a control that shows a
  price.
- The survey reports *"the walk reached a payment step at stop 3: a card field (guarantee €20)"*. **Nothing
  pressed, nothing typed.**
- ⚠ **A card guarantee with no charge is still a payment step.** It is irreversible exposure, and it gets its
  own yes. That yes does not exist in this build.
- **So those venues read back as:** *"Booking there asks for a card at step 3. I stopped; you can finish it on
  their page."*
- **A hold is not a payment, but it is an act.** If observation shows that a choose-click holds a table, that
  click is **moved behind a yes**: round 2 needs the user's *"yes, check 21:15"*, which is cheap because the user
  just picked it.

## 6. Cost, honestly

**The machinery**, built once, serves every wizard platform:

| piece | days |
|---|---|
| vocabulary, both kinds, `assertSurveyOnly`, JS and Python, parity and byte-copy tests | 1 |
| `page.js` `click` with its 8 refusals, plus `read_offers` (select, radio, buttons) | 2–3 |
| calendar reading **per map**, month paging | 2 |
| `sw.js` survey run path: kind check, signed report, pending and re-delivery, no fill or submit reachable | 1–2 |
| signer: survey issue, report verification, the fill binding (§4 rules 1–6), rounds, `booking_surveys` SQL, routes | 3 |
| page and chat: "checking…", real slots read back, the pick, round 2, "that slot has gone" | 2 |
| **a local wizard replica in the rig**: steps, calendar, time chips, POST-advance, mid-walk card, hold countdown. **The only way to test this without touching a platform** | 2–3 |
| **total** | **about 13–16 working days: 3 weeks** |

**Per platform, after that:**
- 1 hour of observation, in the founder's real browser, reading only;
- 1–2 days for the map and its fixtures;
- **a terms read, which can say no**;
- upkeep whenever they redesign. The map's fit check catches it as a stop, never as a wrong click.

**What decides "thousands":**
- **TheFork:** robots disallows `/reservation/`, there is a DataDome wall, and the terms are unread (S-30). This
  build does **not** remove those. On the user's device a person usually passes DataDome, and an automated
  click can still draw a challenge, which is a stop.
- **So the order is:**
  1. the observation and the terms read (S-30 §4);
  2. then this build;
  3. then the first map on a platform whose terms allow it.

**Building the machinery first risks three weeks for a platform that says no.**
