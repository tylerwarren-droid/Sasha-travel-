# Sasha 130: test calls, the decision workflow, one-tap confirmation

*3 Oct 2026. Commits: d0bde3b, d46d449. CR 7 hooks: 0e6a889 (CR's).*

## 1. The 6 scripted-language test calls

- **Setup:** `SASHA_TEST_CALL_NUMBER` was set on Railway (CLI, value not printed) to the founder's mobile, with his
  approval. He got one WhatsApp heads-up beforehand.
- **Calls:** 13:08–13:17, one per language, with each script's real opening and a 1-minute cap. Nothing was recorded or
  booked.
- **Result:** **6 of 6** were placed, answered and completed, at about 1 minute each. Bland transcribed his replies in
  each language (Bland ids in the matrix).
- **What's left:** how each voice sounded is **his verdict**, to mark ✅ / ⚠ / ❌ in
  `docs/sasha/Sasha-129-call-language-matrix.md`.
- **The other 11:** later. CR 7 has put their disclosures in `wordings.DISCLOSURE`; the calls will use them verbatim.

## 2. The decision workflow: `booking_signer/decide.py`

One pure function, `decide(Venue, prefer)`, returns the route, the **reason the guest is shown first**, the follow-up,
and the alternatives.

| The venue | Route | What the guest reads |
|---|---|---|
| Own form | form | "They take bookings on their own website's form — I'll fill it in after your yes." |
| Platform only | **one-tap** | "They book only through CoverManager. I'll send you their booking page, filled in where CoverManager allows — you press confirm (I can't press it for you), and I'll file their confirmation email from your Gmail." (+ "Or I can call them" when a call is possible) |
| No form, open now, phone, scripted language | call | "They have no booking form, and they're open now — I'll call them, after your yes." |
| Closed / email only / unscripted language | email | "I'll email them — they're closed right now" (or the real reason) + "If they haven't replied by their opening (13:00), I'll ask you here whether to call them." |
| The guest's override | any route that exists | "call them instead" / "email them" / "send me the link" → "As you asked: …". An impossible wish is said ("I can't call them: they publish no number."). |

**Wired into WhatsApp:**
- The reason is sent first, then that route's own read-back and yes.
- If a route is refused, the next one is tried.
- The email route is new on WhatsApp. It is honest that a sent email is not a booking: "✉️ Emailed … Not booked yet."
- An override works while a yes question or a one-tap page is open.

**Tests:** 19 in `tests/test_decide_s130.py`. The full suite is **849 OK**.

**Email, then a call at opening:** built, but **off until migration 030** is applied (see §6). Until then, Sasha neither
offers the call nor promises it. When it's on:
- **When:** a still-unanswered email booking whose venue opened in the last 2 hours.
- **What:** ONE WhatsApp question, "No reply yet … They've just opened — shall I call them?"
- **Yes:** leads to the call's **own** read-back and yes. Nothing is dialled from the question.

**Found and fixed on the way:**
- **The phone rung was still closed** for unscripted languages. That made Sasha 128's English-abroad call impossible to
  offer. Only "calls off" closes it now. The old test, superseded, was rewritten.

## 3. Vietnamese venue emails: English, and said so

- The email read-back says: **"I'll write in English: I have no Vietnamese template."**
- Since CR 7 (0e6a889), the line becomes "I'll write in Vietnamese — an unreviewed draft, to our own test address only"
  or "(reviewed by …)" when that is what's sent. For a real Vietnamese venue it stays English until a native speaker
  signs off.

## 4. The one-tap rehearsals

WhatsApp was simulated; nothing reached his phone.

**A · our test venue standing in for a platform**

| Step | Result | Time |
|---|---|---|
| One-tap page offered | ✅ | 5 s |
| The guest presses | Stood in: the test venue's confirmation email was sent to his Gmail, as its page would | — |
| "BOOKED" → Sasha searches his Gmail | ✅ "Sasha Test Venue's email confirms Wednesday 7 October 21:00 for 2 (ref TV-B224F1). Mark it confirmed?" | 74 s |
| Yes → filed | ✅ status **confirmed**, booking_reference **TV-B224F1**, channel link | 4 s |

- **First run, a defect:** the email WAS found and matched by venue and time, but never offered. The status of a
  booking the guest pressed for (`guest_booked`) wasn't one that `offer()` accepts. Fixed (d46d449), with a regression
  test.
- **Cleanup:** the reset afterwards cancelled the test booking.

**B · one real platform page, read-only: Akaneya (CoverManager)**
- Only their own site, akaneyajapan.com, was read through our venue read. **covermanager.com was never requested.**
- **Decision:** one-tap ("They book only through CoverManager…").
- **Page:** built from their site's link, but **not pre-filled.** No CoverManager pre-fill recipe has been verified yet,
  so the guest picks Wednesday 7 October 21:00 for 2 on the page.
- **⚠ Check before using it in the demo:** the venue read was for **Pilar** Akaneya, but the page linked from the
  group's site is `restaurante-carlotaakaneyamadrid`. That may be the **Carlota** Akaneya sister restaurant. One-tap
  would then send the guest to the wrong restaurant's page. It needs one look by the founder (or the group's site
  structure fixed in the read) before Pilar is shown.

## 5. Decisions for the founder

1. **The 6 voices:** mark each language ✅ / ⚠ / ❌ (§1).
2. **Migration 030** (§6): apply it, then set `SASHA_NO_REPLY_CALL=1`, to switch on "email, then a call offered at
   their opening".
3. **The Akaneya page** (§4 B): Pilar or Carlota?
4. **The site link** for CR 8's case-officer queue, on Relocation: OK to publish while the site is held for your
   signed-out walk?

## 6. Migration 030 (for chat to apply)

- **File:** `backend/booking_signer/sql/030_no_reply_call.sql`.
- **What it does:** adds `no_reply_call` to `proactive_sent_kind_check`. The live constraint was read on 3 Oct from
  `pg_constraint`.
- **Preview:** read-only SELECTs first, then the change in one transaction.
