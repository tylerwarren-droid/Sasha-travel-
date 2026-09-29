# S-30 — TheFork: one map for every venue on it. Is its booking page a form or a wizard, and what it costs

**Filed:** 29 September 2026, night. **Report only; nothing built.** The ticket number S-30 is proposed.

## 0. Blunt answer

- **The founder's point is right in structure.** A platform is a form, and one map covers every venue on it. That
  is concentration, not an obstacle.
- ⚠ **TheFork is a wizard, not a plain form.** The name and email step exists only after a date, a party size and
  a time slot have been chosen. That part is **from general knowledge and not observed tonight** (§1).
- ⛔ **What was observed tonight stops the usual method.**
  - TheFork's `robots.txt` disallows **`/reservation/`**, the path of the contact-details step, on every locale
    checked (`.com`, `.pt`).
  - The site is **DataDome-protected**: our request got **HTTP 403** with `x-datadome: protected`.
  - Psi was mapped from our own fetch. **TheFork cannot be**, and we do not work around a bot wall or a
    robots rule.
- **Cost: not estimable honestly until someone looks at the flow in a real browser.** The ranges in §3 are
  conditional.

## 1. Form or wizard

**Observed (29 Sept):**

| check | result |
|---|---|
| `thefork.com/robots.txt`, `thefork.pt/robots.txt` | `disallow: /reservation/`; `/*?date=*` also disallowed |
| `GET https://www.thefork.pt/` (plain client) | **403**, `x-datadome: protected`, a DataDome cookie set |
| a real Chromium render of the home page | a DataDome page; no restaurant links rendered |

**Not observed, from general knowledge only:**
- The restaurant page carries a **booking widget**: pick a date on a calendar → party size → one of that day's
  **time slots** (live availability) → often an **offer** (a discount tier).
- Only then does it move to `/reservation/…` for **name, email and phone**.
- It may need a **TheFork account**, or a guest step with **phone verification**.
- Some venues ask for a **card guarantee**.

**Every one of those needs checking before it is relied on.**

**So it is a wizard.** The reason matters for the approval order:
- **The slot list does not exist until date and party are chosen**, and it is per venue, per day, live.
- So the read-back cannot be built before the page is opened, as Psi's is.
- Choosing a date and party **commits nothing**. It is a read, not an act.
- So the order is still solvable: **step through the non-committing choices (a survey on the user's device) →
  read back the real slot and fields → yes → the final confirm is the only act.**
- ⚠ That holds only if **no step before the last one creates a hold or a pending reservation**, which must be
  observed, not assumed.
- It is a **different job from a form**: a step runner, and a definition of which clicks are reads and which one
  is the act.

## 2. What else stands in the way (each one can stop it by itself)

1. **DataDome.** On the user's own device a real person usually passes. **An automated fill inside their browser
   can still draw a challenge.** A challenge is a **stop**, never worked around, so every such run ends with
   "please finish on TheFork".
2. **robots `/reservation/`.** The rule governs crawlers. The helper acting for one user, on their device, at
   their yes, is closer to a user agent. **Our side must never fetch it**, which means no server survey and no
   server-side map capture. Mapping has to be done by observation in a real browser.
3. **Terms of use.** Not read tonight: the page is behind the same wall. Platforms commonly forbid automated
   access. ⚠ **A legal read before anything is built.** The honest alternative is TheFork's own **partner
   channel** (they run one for restaurants and affiliates), if it takes bookings.
4. **Account or verification.** If booking needs a TheFork login or an SMS code, **the user does that step**.
   The helper never holds their password (the standing rule).
5. **Card guarantee.** It hits the payment stop, which is correct, and those venues become "finish on TheFork".
6. **Map upkeep.** A platform ships often, with generated class names. The map needs **label-based selectors**
   (the S-29 vocabulary helps here) and a check before each run that it still fits.

## 3. Cost, conditional

| step | cost | condition |
|---|---|---|
| **observe the flow once**, in the founder's own Chrome (or with me reading his tab), stopping **before** the confirm | 1 h | he is willing; no booking made |
| legal read of TheFork's terms, and whether its partner channel books | days, outside engineering | none |
| **step runner**: reads vs the act, survey through the wizard on the device, read-back from the real slot | **3–5 days** | no hold before the confirm; no mandatory login |
| TheFork map (label-based) plus its per-run fit check | 1–2 days | the observation shows a stable structure |
| end-to-end tests without touching the live platform | 1–2 days | a local replica of the wizard, like the Sasha rig |

- **Best case, once the terms allow it: about 1–2 weeks** to "any TheFork venue, with challenges and
  guarantees ending in 'finish on TheFork'".
- **Worst case: the terms forbid it**, and the path is the partner channel, which is business development, not
  code.

**The other platforms:**
- **Fresha** also disallows its booking paths (`booking/time`, `booking?…`).
- **OpenTable** did not answer a plain client.
- **Booksy** answered 200 on its home page only.

The same shape holds for all four: **a wizard, with robots and a wall in front of it**.

## 4. Recommendation

1. **First, the one-hour observation**, in the founder's real browser, reading only and stopping before any
   confirm. It settles five of §2's six unknowns.
2. **In parallel, the terms read.**
3. **Build nothing until both are in.** If they are clean, the step runner is the next build, and it serves every
   wizard platform, not only TheFork.
