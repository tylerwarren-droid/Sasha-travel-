# S-33 — The phone rung, built. Report before committing

**Filed:** 29 September 2026, night. **Built and tested; not committed; nothing dialled.**

## 0. Blunt answer

- **Built:**
  - the call, placed with the founder's script from an approved read-back;
  - **Bland's answer read, never assumed**;
  - the finished call read into **yes / no / unclear, always with the venue's own words**;
  - she never accepts a fee, a deposit, a card or a different time: *"I'll need to check that with the
    Johnsons."*
  - No recording.
- **Tests:** 122 pass (46 new), in memory **and** on a real Postgres with `001`+`002`+`003` applied. Frontend `tsc`
  is clean, and the outcome-surface check covers the new panel.
- ⚠ **Nothing can ring until three things are done by the founder** (§3):
  - run `003_phone_calls.sql`;
  - set `SASHA_CALLS_ENABLED=1` and `SASHA_TEST_CALL_NUMBER` on Railway;
  - deploy.
- ⚠ **The only number it can call is the test line**: the founder's own phone, standing in for a restaurant.
  **No real venue is listed**, because no number in the codebase comes from a source a person checked (§4.2).

## 1. What was built

| file | what |
|---|---|
| `backend/booking_signer/calls.py` | the script in six languages; the brief; **`place_call`**, which reads Bland's answer; **`read_call`**, which reads the finished call |
| `backend/booking_signer/call_routes.py` | `POST /api/booking/calls` (read-back), `POST …/{id}/place` (the yes), `GET …/{id}` (poll; reads the call once, when finished) |
| `backend/booking_signer/call_store.py` | memory and Postgres stores. One call per approval, claimed **before** Bland is asked |
| `backend/booking_signer/sql/003_phone_calls.sql` | the `booking_calls` table, and `unclear` on `trip_items` and `booking_attempts`. **For the founder to run** |
| `backend/booking_signer/routes.py` | includes the call routes; `/health` gains `calls` (on or off, key present, number set; **never the number**) |
| `backend/tests/test_booking_calls.py` | 46 tests |
| `frontend/app/booking-helper/PhoneCall.tsx` | the panel: particulars → read-back → **Yes — call them** → what they said |
| `backend/requirements.txt` | `tzdata`, so "Thursday" is worked out in the venue's timezone on Railway too |

**The opening sentence, as built** (the test pins it):

> *"Hello, this is Sasha, an AI assistant, calling on behalf of the Johnson family to book a table for four on
> Thursday at eight in the evening. Is that possible?"*

- *"in the evening"* is the one addition, so "at eight" is never heard as morning.
- A date more than six days away is said with its date: *"on Tuesday, 20 October"*.
- There are templates in Portuguese, Spanish, French, German and Italian. Each puts the AI clause first.

**Bland's answer, read (`place_call`):**
- **placed** only on HTTP 200 **with** `status: success` **and** a call id;
- everything else is **not placed**, with Bland's own message, and the page says *"I couldn't place the call:
  Insufficient balance"*. That covers:
  - 400, 402, 429 and 500;
  - a 200 that says error;
  - a 200 with no call id;
  - a body that isn't JSON;
  - a network failure.
- Eight tests pin this. ⛔ **There is no path that reports a call Bland did not accept.**

**The reading (`read_call`):**

| Bland says | outcome |
|---|---|
| busy, no-answer, failed, cancelled, or a voicemail answered (**she hangs up; no message**) | **not reached**. Nothing agreed; the reservation stays `pending` |
| completed, and the venue spoke | a model reads the transcript. It may say **yes** or **no** only **by quoting the venue**, and **the quote must appear verbatim in a VENUE line**. Quoting Sasha, paraphrasing or inventing gives **unclear** |
| a "yes" with a deposit, fee or card (a regex over the venue's lines in six languages, **independent of the model**) or with a different time or date | **unclear**, with what they raised |
| "call back tomorrow", "maybe", a model error, a malformed reading, silence | **unclear**, with **every word the venue said** |

- **yes** → reservation `confirmed`; **no** → `declined`; **unclear** → `unclear`. Each adds a `booking_attempts` row
  with `method = 'phone'`.
- The outcome is labelled *"an AI reading of the call transcript"* wherever it is shown. The venue's words are
  verbatim.

## 2. What stands between a request and a ringing phone

Each of these refuses by name:
1. `SASHA_CALLS_ENABLED=1` (off unless set) **and** `BLAND_API_KEY`. When off, **no read-back is offered**: a Yes
   that cannot dial is not shown.
2. **The number comes from the server** (`CALL_VENUES`, from the environment), never from the request. A request
   carrying `number` or `phone_number` is refused.
3. The yes must name **this** read-back's hash, **within 15 minutes**, and a call row is **dialled once**. A second
   yes gives `call_already_placed`.
4. **At most `SASHA_CALLS_PER_DAY` calls (default 3) in 24 hours, across everyone**, counted inside a table lock.
5. The name that is spoken is limited to 2–60 letters. Anything else is refused rather than read to a stranger.

## 3. What the founder does to try it (in order)

1. Run `backend/booking_signer/sql/003_phone_calls.sql` in Sasha's Supabase. There is a preview `select` at the top,
   it refuses if already applied, and a checklist must say `ok = true`.
2. On Railway, set `SASHA_CALLS_ENABLED=1` and `SASHA_TEST_CALL_NUMBER` (**your own phone**, E.164). Optional:
   `SASHA_TEST_CALL_LANGUAGE` (`en` by default) and `SASHA_TEST_CALL_TIMEZONE`.
3. Commit and push. Stage E: `/api/booking/health` → `calls.enabled: true`, `number_set: true`.
4. On `/booking-helper`, "Phone a venue" → Prepare → **Yes — call them**. **Answer it as the restaurant**: say yes;
   then say no; then *"we can do 9:15"*; then *"we need a deposit"*.

## 4. What is genuinely in the way

1. **Bland's account.** International calls need **a completed credit purchase of at least $5**, and an Agent Phone
   Plan number calls US and Canada only (Bland's docs). **A Portuguese or Vietnamese number may be refused.** If
   so, the page will say **Bland's own words**. Not verified; I have not placed a call.
2. **No real venue has a number we may dial.**
   - The restaurant cards come from web search, and a searched number is what the deleted agent "best-guessed".
   - **A venue is added to `CALL_VENUES` by a person, with where its number came from.** That is minutes per venue,
     but it is a person's minutes.
3. **Nobody signs in.** These routes are as public as the page (the shared key ships in the JS bundle). **The daily
   ceiling is the protection**:
   - today, anyone who finds the page can spend three calls to **your** phone;
   - with real venues listed, **three prank bookings a day** is the exposure;
   - **the real fix is sign-in.**
4. **Vietnam, the demo's country:**
   - Bland's language list as fetched names ~17 codes plus "30+ others", and **Vietnamese is not confirmed**;
   - there is **no Vietnamese template**;
   - a Hanoi restaurant is also an international call (point 1).
5. **The non-English templates are mine.** They need a native speaker before a real venue hears them. Portuguese
   uses Bland's `pt-BR` voice: understood in Lisbon, and noticeably Brazilian.
6. **"Contact details are hers" cannot be honoured yet.** Sasha has no number or inbox that answers (S-32). So she
   gives **the guest's own number, only if the venue asks**, and **the read-back says so before the yes**. With no
   number given, she says the guest will confirm directly.
7. **The transcript.** No audio is recorded, but Bland transcribes the call, because that is how the agent hears.
   `booking_calls.bland_details` keeps the whole transcript.
   - If "no recording" should also mean no stored transcript, keeping **only the venue's lines** is a small change.
   - Whether a stored transcript needs consent is **the same legal read** as recording.
8. **The reading needs `ANTHROPIC_API_KEY` on Railway.** The chat uses it, so it is probably set; not verified.
   **Without it, every answered call is `unclear` with their words**, which is safe.
9. **Calls don't appear in `/api/booking/reservations` yet.** That query joins form intents. The call panel shows
   its own outcome, and the trip item and attempt are recorded. Listing calls is a small query change.

## 5. Checks run

**Backend** (in memory and on Postgres, with `001`+`002`+`003` on the live-schema fixture):
- `test_booking_calls` (46) plus the four existing suites: **122 tests OK, 0 skipped**;
- `003` refuses a second run.

**Frontend:**
- `tsc --noEmit`: 0 errors;
- `check-outcome-surfaces`: 2 surfaces clean, 5 fixtures caught;
- eslint on `PhoneCall.tsx`: clean;
- `page.tsx` has the same 4 problems as HEAD (none added).

**Not run:** `npm run build`, and **any real call**.
