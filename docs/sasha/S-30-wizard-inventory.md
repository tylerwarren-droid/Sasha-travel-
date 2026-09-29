# S-30 addendum — What of the wizard walk already exists

**Filed:** 29 September 2026, night. **Report only.** Every line below was read from the code tonight.

| piece | verdict | where |
|---|---|---|
| a read-only survey on the device | **partly, and not usable as one** | `extension-sasha/lib/page.js:101`, `sw.js:189–253` |
| clicking inside a page (calendar, time, "next") | **not at all** | `page.js:15`, `portable/originates.js:22`, `issue.py:47` |
| reading the slots a page offers | **partly: select options server-side; calendars not at all** | `lib/agapi/forms/form-map.ts:68, 268–281` |
| two passes with the approval between them | **not at all** | `sw.js:106–107, 189–234`; `issue.py:201` |

## 1. The read op: could it survey a page before a task is signed? No, as built

**What exists:**
- `page.js` has `op: "read"` (line 101). It returns the URL, the **full markup**, a payment check and a challenge
  check.
- It clicks nothing and fills nothing, so as a function it is read-only.

**Why it cannot survey:**
- **The only caller is step 7 of a signed run** (`sw.js:253`), **after** submit.
- There is **no message that runs it alone.** The port accepts `HELLO`, `PAIR`, `RUN`, `PENDING` and `ACK`
  (`sw.js:96–114`), and `RUN` goes straight to `verifyBookingTask` (`sw.js:191`). An unsigned or unverified
  message **opens no tab**.
- The **venue permission is asked only after verify** (`sw.js:198`).

**So it is a reusable part, not a survey.** A survey needs a new message, a rule for what may be read unsigned,
the permission step moved, and a decision on how much markup leaves the device.

## 2. Clicking: there is no step that clicks anything but submit

**In the helper:**
- `page.js` has **three ops only: `fill`, `submit`, `read`**. Its header says so in words (line 15): *"THERE IS
  NO OPERATION THAT CLICKS A LINK, CHOOSES A URL, OR PRESSES PAY"*.
- `submit` calls `requestSubmit` on the form (line 170). No element is ever clicked.
- `fill` sets values through the native setter and fires `input` and `change` (lines 134–136). That picks a
  `<select>` option. **It cannot choose a calendar day, a time button or a "next" control.**

**In the step vocabulary:**
- It is **fixed** and enforced in three places:
  - `lib/agapi/portable/originates.js:22` (plus its vendored copy);
  - `backend/booking_signer/issue.py:47`, which refuses unknown steps at line 190.
- **It holds `navigate`, `await_form`, `fill_fields`, `submit`, `read_page_after`, `report`, and nothing
  else. None of them clicks.**
- The render policy also forbids clicks on the server: `lib/agapi/forms/render.ts:14`, *"GET only, no form
  submission, no click"*.

## 3. Reading the offered slots

**`<select>` options: built, on the server.**
- `form-map.ts` records every option's value and label with a hash, and whether there is an empty choice
  (lines 68, 268–281).
- **That is how Psi's served times are known.**

**At fill time: the check exists, the reading does not.**
- `page.js:130` refuses a value the select does not serve (`option_not_served`).
- It checks one value. **It does not return the list.**

**Calendar enabled days (`aria-disabled`, date-picker cells): not at all.** Nothing in `lib/agapi/forms` or the
helper reads a calendar.

**Related, and useful for Patara:** `lib/agapi/forms/rendered-form.ts` already reads controls **outside any
`<form>`** on a rendered page. It is server-side, and it is used by the register classifier, not by the booking
roles.

## 4. The two-pass shape

**Nothing in the signer or the helper supports it.** Both are one pass:
- **The signer:** `issue_booking_task` (`issue.py:201`) signs one task that already carries every
  selector = value and `filled_values_sha256`. It has no survey mode and no "phase 1".
- **The helper:** one `RUN`, verify → permission → claim the intent → open a tab → fill → dry-run stop or submit
  (`sw.js:189–243`). **The intent is claimed once, before the tab opens** (`sw.js:206`). So a second pass under
  the same intent is refused by design: a replay is refused as `intent_already_run`.

**What exists that a two-pass run would reuse:**
- the dry run already fills, captures and stops **without sending**;
- `mode: "dry_run"` then a separate `mode: "live"` intent is the nearest thing to two passes today;
- ⚠ but both passes are signed, and the first already needs the values. **It is "rehearse, then act", not
  "survey, then read back".**

## 5. In one line

**Built:** reading markup (after a submit), select options (server-side), and a no-send fill-and-capture.

**Not at all:**
- a survey before signing;
- any click other than submit;
- calendar reading;
- a two-phase task with the approval between the passes.
