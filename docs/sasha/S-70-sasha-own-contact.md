# S-70 — Sasha's own contact on every booking: her email and her phone, so changes reach the reservation

*1 Oct 2026, the Sasha tab. Renumbered from S-69 (Sasha 69). Founder's rule (Sasha 60), non-negotiable.*

## The rule
On **every** booking Sasha gives the venue, alongside the guest's name, **her own** contact:
- **email:** `sasha@booking.kanoe.ai` — live once Resend verifies the domain (the GoDaddy DNS, US tab);
- **phone:** a **UK mobile** with **voice and SMS** — not bought yet.

So a venue's confirmation or change reaches Sasha, lands **on the reservation**, and then goes to the guest.

⛔ **Honesty (S-32):** a number or address is given out **only once something answers it** — an inbound email that
lands on the reservation, and an inbound SMS/voice handler that does the same. Until then the read-back says what is
given, and nothing else.

## Buying the number: the founder's unavoidable steps (Sasha 75)

**Read at source, 1 Oct 2026** (twilio.com/en-us/guidelines/gb/regulatory). For a UK **mobile** number held by a
**business**:
- **no supporting documents** are required;
- **the address may be anywhere in the world**, so Kanoe's Spanish address is fine. A UK address is needed only for
  local/national numbers, not mobile;
- the bundle needs: business name; registration authority and number; website; business address; an authorised
  representative's name, mobile phone and work email; the business classification (direct customer).

**The founder does three things:**

1. **Twilio account for Kanoe Technologies SL**, upgraded from trial (twilio.com/console). Sign-up, identity check and
   payment method are his alone. A trial account cannot buy a UK mobile.
2. **On Railway (Sasha-travel-, backend service), set two variables himself:** `TWILIO_ACCOUNT_SID` and
   `TWILIO_AUTH_TOKEN`, from the Twilio Console's front page (rule 17: never pasted in chat). Then he says "Twilio set".
3. **Tell this tab, in chat, the four facts it cannot know.** None of them is a secret:
   - Kanoe Technologies SL's **NIF/CIF**;
   - its **registered address**;
   - the **authorised representative** (him, presumably: name and title);
   - the representative's **mobile number**. Twilio may contact them on it; Twilio requires one that is not a Twilio
     number. The work email is taken to be `tyler@kanoe.ai` unless he says otherwise.

**Given by the founder, 1 Oct 2026 (bundle input, not secrets):**
- Kanoe Technologies SL, NIF **B23942923**;
- registered address **Calle del Padre Damián 41, 28036 Madrid, Spain**;
- authorised representative **Tyler Warren**, +34 608 445 715, tyler@kanoe.ai;
- the Twilio Account SID, set on Railway by this tab as `TWILIO_ACCOUNT_SID` (kept out of the repo: GitHub's push
  protection treats it as sensitive).
- **Still needed:** `TWILIO_AUTH_TOKEN`, set on Railway by the founder himself. Both of his messages carried the
  placeholder `<paste token>`, so nothing has been sent to Twilio yet.

**This tab does the rest, through Twilio's API under `railway run`, with no credential printed:**
- create the End-User (business, direct customer) and the Address;
- create the GB-mobile business regulatory bundle, attach both, and submit it;
- watch its status, and say when Twilio approves it or what it asks for;
- on approval, buy a UK **mobile** number with **Voice + SMS**, attached to the bundle;
- record it as `SASHA_PHONE_NUMBER` on Railway (not a secret).

**Not until something answers it (S-32):** the number is not given to venues, and its webhooks are not pointed, until
this tab's inbound SMS and voice handlers record on the reservation. Those are built while the bundle is in review.

## What this tab builds (after the number and the domain exist)
1. **The brief and the email carry Sasha's contact** (her email; her number once inbound works), next to the guest's
   name — in the read-back too, word for word.
2. **Inbound SMS and voicemail → the reservation** (matched by the venue's number), shown to the guest verbatim.
3. **The confirmation email after every phone booking** (point 3): to the venue's published address, Sasha copied,
   the guest BCC'd — restating what, when, how many and the name. **Unclear outcome:** the *"I just spoke with you…
   can you confirm…"* version. A reply lands on the same reservation.
4. **The after-hours email to the same reservation** (S-67 follow-up).

## Built ahead of the number (Sasha 77)

- **`booking_signer/inbound_phone.py`.** Each route is Twilio-signed and verified:
  - `POST /api/booking/twilio/sms`: the SMS lands on the reservation of the most recent call Sasha placed to that number
    (matched by digits, or by a listing number's hash). It is read with the field checks: a clear yes restating day,
    time and number confirms; another time proposes; a stop ends every channel. There is never an automatic reply;
  - `POST /api/booking/twilio/voice`: a Spanish and English greeting that says the message is recorded and goes to the
    booking, then `<Record>`;
  - `POST /api/booking/twilio/recording`: files the recording with that call.
  - The sender is kept only as a sha256 key.
- **`sql/016_inbound_phone.sql`** (`booking_inbound`): drafted, **not applied**, waiting for the founder's approval.
- Tests: `tests/test_inbound_phone.py` (memory and Postgres).
- The number is given to venues only once 016 is applied, the number is bought, and its webhooks point at these routes.
