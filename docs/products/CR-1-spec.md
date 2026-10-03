# CR 1 — spec: CampusMe and Spain relocation on Sasha's chassis

*Fourth build tab. Plan: `CR-1-plan.md`. Code: `backend/products/` (repo-only: outside `backend/app/`, so Stage A never
touches it). Tests: `backend/tests/test_campusme_cr1.py` (+ relocation's at M2).*

## §1 One WhatsApp number, three products — demo only

- **Demo (sandbox):** one Twilio sandbox number serves Sasha, CampusMe and relocation by **mode**.
  - "campus…" enters CampusMe; "relocation…" (or "relocate", "EX-01") enters relocation.
  - "exit", "sasha" or "back" returns to Sasha. A mode idle for 6 hours ends by itself.
  - The mode lives in the guest's existing `pending` (`{"kind": "product", …}`), so it needs no new column.
- **One hook** sits in `booking_signer/guest_whatsapp.turn()`, marked `CR 1 products`.
  - It runs after STOP, START and the reminder words, which therefore always work, and before the media-only refusal,
    since relocation reads photos.
  - Not in a mode and no keyword: it returns at once, and Sasha's turn runs byte for byte as before.
  - Product turns are **never** written into Sasha's history, because relocation answers carry passport facts.
- ⚠ **Production needs one number per product.** Meta ties a verified business **display name** to a number, and that
  name is what the person sees and opts into. "Sasha by Kanoe" can't truthfully be the sender of CampusMe's school
  registrations or of a residence-permit file. So each product gets its own sender, display name, opt-in wording and
  templates, and the mode switch is retired.
- Production also waits on F-1 (counsel) and Meta verification, as Sasha's own sender does (S-61).

## §2 CampusMe

**Reader** (`campus/slate.py`). Each school's own visit calendar, on its own domain:
- robots.txt read first per host and obeyed, both for `KanoeCampusMe` and for `*`; a robots file that can't be read means
  the host stays unread;
- at most 1 request every 4 s per host, with 15-minute caching;
- every read kept as a receipt (url, HTTP status, sha256, time).

Two Slate variants were found in the schools' own scripts on 3 Oct 2026:

| Variant | Dates | Sessions | Full? |
|---|---|---|---|
| widget (Yale) | `…/portal/widget/event?…&cmd=event_dates` | `cmd=event_list` (HTML) | "Spaces Available: N" shown |
| register (Penn) | `/portal/campus-visit?cmd=getDates` | `cmd=getEvents` → each event's form page | `/register/form?cmd=counts`: `exceed` = "1" means full *for that many attendees*. The visible "Full" text is a hidden template, not a fact |

- **Proven live:** Yale and Penn. Live run: `backend/scripts/campusme_live_read.py`; output: `docs/campusme/READS.md`.
- **Configured, not proven:** Williams and Pomona. The family is told so, and no sessions are shown for them.
- **Not readable:** Harvard (503; its terms), Amherst (robots), Berkeley tours, Ohio State. The family is told why.

**Flow** (`campus/turn.py`):
1. The ask is parsed in words. One missing thing gets one question.
2. "Reading Yale's own visit calendar…" goes out first.
3. Cards follow: at most 3 per school, one per day, open sessions only.
4. A month the school hasn't published gets *"Yale hasn't published April 2027 yet — its calendar runs to 30 November 2026.
   I'll check it daily and message you the day April opens"*, and a watch is kept (`campus/watch.py`).
5. **Pick.** The student's details come from the **vault** (an `identifier` item, provider `CampusMe`), or five questions
   asked once, with an offer to keep them in the vault.
6. **The read-back, hash-bound:**
   - the vault's access line: *"I'll use your saved student details (Sam) from your vault, for CampusMe only."*;
   - the session, as read, with its spaces;
   - who's registering;
   - *"I'll prepare Yale's own registration form and stop before its Register button: you press it. I send nothing to
     Yale."*;
   - *"Registering creates a record for the student in Yale's admissions system, and the school will email them"* (P807on
     §3).
7. **The yes** must be the button of this question, or a typed yes, within 15 minutes. Then:
   - the session is re-read, and a session that has just filled stops here;
   - the vault opens once, logged;
   - the school's form is read, a CAPTCHA marker noted, and every question planned (`campus/handover.py`).
8. **The hand-over page** `/campus-handover/{id}` shows the school's form question by question:
   - what to enter, and where it came from;
   - **every statement or consent marked "yours to tick"**: "By submitting this form, you understand…" and the SMS opt-in;
   - educator-only questions marked "not for you";
   - the school's own rules, quoted;
   - "Open Yale's registration page ↗".
   - ⛔ No submit exists anywhere in CampusMe.
9. **"REGISTERED"** adds the visit to the account's bookings as a `trip_items` row (`experience`, `pending`). The S-83
   reminders and "You" then see it, and the family gets a Google Calendar "add" link plus an `.ics`.
10. **The school's confirmation email, pasted**, confirms the visit, but only if it names the school **and** the day.
    Otherwise it stays "registered on your word". Confirmed sets the trip item to `confirmed`, which S-79's calendar
    trigger picks up.

**Live registration:** none. Read-only until the founder approves one real registration, which a person presses (P807on §4).

## §3 Storage

- `sql/028_products.sql` creates `product_cases`. The id is a 22-character capability; state is jsonb; RLS is on with no
  policy, so only the server role can reach it; rows expire after 30 days and are deleted daily, logged in `retention_log`.
- Until 028 is applied, cases live in this server's memory, and `/api/booking/products/health` says `memory`.
- ⚠ **Open:** account deletion (`vault/gdpr.py`, the Sasha tab's) doesn't yet delete `product_cases`. The 30-day expiry
  bounds it. For the Sasha tab, or for me with their OK.

## §4 Relocation — M2 (this section is filled when it's built)

## §5 Never

- Submit to a university or a government site.
- Sign, tick a consent or statement, or declare an intent for anyone.
- Hold a Cl@ve or a portal password.
- Fetch a bot-protected host from the founder's network.
- Call the model on WhatsApp, except to read a document the person sent (relocation, M3), with each value read back for
  their confirmation.
