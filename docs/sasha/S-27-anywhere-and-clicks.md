# S-27 — More venues tonight, "book anywhere", and every click that remains

**Filed:** 29 September 2026, evening. **Report only; nothing built.** The estate's own measurements, not
estimates, where they exist.

## 0. Blunt answer

- **More venues before morning: realistically none, possibly one.** The estate knows exactly **one** venue on
  this plugin at a version our map fits, and that is Psi. A new one has to be **found** first, and finding one is
  most of the cost.
- **"Book anywhere" is months, not an evening.** About 1 restaurant in 30 has a first-party booking form at all.
  The rest book through platforms (TheFork, OpenTable, SevenRooms, CoverManager…) or by phone and email. The
  form-fill we built is the **long tail**, by our own measurement.
- **Clicks:** the read-back **yes** stays; it is the authorisation. The **tab-opening click** stays tonight
  (§3). The **Chrome permission prompt** can go for known venues **without** the Web Store, which contradicts
  the brief (§3). Everything else can go.

## 1. More venues on the same plugin (1.4.6–1.5.3): how many, and what each costs

**How many exist that we know of: one.**
- The only `rtb-` form in the estate is Psi's.
- `lib/agapi/booking/registry.ts` records first-party forms at **1 of 29** Lisbon venues (Psi) and **1 of 32**
  in Madrid: *"roughly one venue in thirty"*, measured in two countries.
- Across about 95 venue hosts in four cities there are **two** genuine booking forms, and only one is this
  plugin.

**And "the same plugin" is narrower still.**
- Our map and our refusal wording fit releases **1.4.6–1.5.3**.
- Current installs run **2.7.x**, whose form differs by **371 tags** (S-08 §1).
- Most venues that still run this plugin will be on 2.7.x, and **our map does not fit them.**

**Per venue, once one is found** (old release):

| step | cost |
|---|---|
| **find it**: a Magellan detection pass over candidate venue sites (robots first), expecting about 1 in 30 with a form, of which only a fraction on this plugin and fewer on the old release | **the dominant cost, and unbounded**: hours for a city, with no guarantee of a hit |
| **map its form**: render, form map, compare against the reference | 30–60 min each |
| **its formats**: date format, time format, time step, party range and opening schedule are **per-install plugin settings**, not constants. Psi's `October 2, 2026` / `8:00 PM` may not hold | minutes each, but must be read, never assumed |
| **a venue entry in `venues.py`**: `build_for_venue` is hardcoded to Psi; generalising it to "a Five Star venue with these formats" is **one-time** code | about 1–2 h, once |
| **its host permission** in Chrome | one prompt per venue (§3) |

**Can the refusal half come from the reference install for a second venue? Yes, for the same release family.**
The refusal wording is the **plugin's** strings, observed on our own install of 1.4.6 and 1.5.3 (S-08). Psi's
standing rests on exactly that: *"reference_install … NOT observed at Psi"*. A second venue on the same releases
inherits it, on two conditions:
1. **Its served form matches the reference**, checked per venue (the form map).
2. **Its language.** A translated install words its errors differently. The spec already matches by **where**
   the error renders (the `.rtb-error` container), not only by its words, which is why Psi's catch-all pattern
   exists.

**A 2.7.x venue needs its own reference install first**: S-08's method, in WordPress Playground, offline. That
is about an evening **before** any 2.7.x venue can be mapped. P807mu recommends exactly this, after the meeting.

**So, before morning:** at best **one** more venue, **if** a detection pass finds an old-release install
tonight. The honest expectation is zero.

## 2. What "book anywhere" would actually take

| path | share of venues (measured) | what it takes | status |
|---|---|---|---|
| **platform hand-off**: TheFork, OpenTable, SevenRooms, CoverManager, Resy… | **most** | per-platform integrations: partner APIs and terms, or a platform-specific agent. They are widgets and accounts, not forms | none built |
| **phone and email** | the rest of the majority | `restaurant_agent.py` sends email and calls via Bland, **and nothing calls it** (S-26). It needs wiring, a confirmation loop and, for email, **a way to receive replies** (S-18: Sasha receives no email) | dead code |
| **first-party form fill** (what we built) | **about 1 in 30** | per plugin family: a reference install, per-venue maps and formats | **one venue, one release family** |
| **discovery**: which path a given venue uses | all | Magellan's detection (platform recognition from served markup, `registry.ts`) wired to Sasha | exists in the AD estate, not in Sasha |

**Distance: months.** Anywhere means the **platform** path first, since that is where most tables are, and
that is partnerships and terms before it is code. The form fill is real and works, and it is the smallest of the
four.

## 3. Every click, and whether it can go

| click | today | can it go? | how, and what it costs |
|---|---|---|---|
| **1. The chat card's link** that opens Sasha's booking tab | yes | ⚠ **not tonight** | Chrome blocks a tab a page opens without a click (a pop-up). It goes **if the booking happens inside `/vietnam` itself**: the helper accepts `/vietnam`, which is top-level on `project.kanoe.ai`. That moves the helper connection, read-back and yes into the CTO's page and chat: **the week** (S-26 §2) |
| **2. Pair** | once, already done | ✅ gone | done once per browser |
| **3. Prepare** | yes | ✅ **can go tonight**, small | when Sasha's link pre-fills every field (date, time, party, demo profile), the tab can prepare **on its own** and show the five lines |
| **4. The read-back yes** | yes | ⛔ **stays** | it **is** the authorisation, bound to the hash of the exact words. It could become a **spoken** yes later (the week; P807mv §5), but it is never removed |
| **5. Our grant window** (the helper's own small window naming the venue) | once per venue | ✅ **gone after the first grant** | it opens only when the venue's permission is missing |
| **6. Chrome's permission prompt** | once per venue | ✅ **can go for known venues, without the Web Store** — ⚠ **correcting the brief** | Chrome prompts because the helper asks for each venue at run time (`optional_host_permissions`), **by design**: per-venue consent. An **unpacked** extension that lists a host in `host_permissions` gets it **at load, with no prompt**. So listing Psi (or any known venue) removes the prompt. **The cost is a design choice, not a store listing**: the user no longer consents per venue, the manifest does. For the demo, granting Psi tonight achieves the same, with no code |
| **7. Resend pending reports** | only after a failed delivery | n/a | appears only when something went wrong, which is its purpose |

**So the minimum tomorrow is two clicks: open the tab, and yes.** With clicks 3 and 6 gone (§4), the room
sees one click in the chat and one yes in the tab. **One** click (the yes alone) needs the booking inside
`/vietnam`: the week.

## 4. What an evening can buy (the founder's choice)

| option | what it gives | cost | risk |
|---|---|---|---|
| **A · Auto-prepare** (click 3) | the tab reads the five lines back as soon as it opens pre-filled | small: page only, and the guard still runs | low; covered by the existing end-to-end run |
| **B · Grant Psi tonight** (click 6) | no Chrome prompt tomorrow | **zero code**: one Allow during rehearsal | none |
| **C · A second venue** | a different restaurant | a detection pass that may find none, plus the `venues.py` generalisation | **high**: likely no venue by morning |
| **D · A different venue on a platform** | "book anywhere" | partnership and terms | **not an evening** |

**Recommendation for tonight: A + B.** Psi as the one venue, as a dry run. The room sees a card click, the five
lines, a yes, the background fill, and the prepared reservation.

> ⚠ **The founder said he will not use Psi.** With no other mapped venue, **the only venue that can run
> tomorrow is Psi.** Anything else tonight is a detection pass with no promise of a result, or a different demo
> (the refusal on our own reference install, P807mu §0, which is not a venue the helper may open without new
> code).
