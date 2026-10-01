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

## Buying the number — steps for the founder (in Twilio's console; check each screen as it appears)
1. **Twilio account** for Kanoe Technologies SL (console.twilio.com), upgraded from trial (a trial account cannot
   buy a UK mobile or send to unverified numbers).
2. **Regulatory compliance → Bundles:** UK **mobile** numbers need an approved **regulatory bundle**: the business
   (Kanoe Technologies SL, its registered address, its NIF) and the documents Twilio asks for at that screen. Approval
   can take a few working days — this is the long pole; start it first.
3. **Phone Numbers → Buy a number:** country **United Kingdom**, type **Mobile**, capabilities **Voice + SMS**; attach the
   approved bundle; buy.
4. **Tell this tab the number** (it is not a secret). For the credentials, **set them yourself** (standing rule 17 —
   never pasted in chat): on Railway `Sasha-travel-`, `TWILIO_ACCOUNT_SID` and `TWILIO_AUTH_TOKEN`; and
   `SASHA_PHONE_NUMBER` = the number in E.164 (+44…).
5. **Do not point its webhooks anywhere yet** — this tab builds the inbound SMS/voice handlers (they record on the
   reservation, never reply on their own) and gives you the two URLs to paste in.

## What this tab builds (after the number and the domain exist)
1. **The brief and the email carry Sasha's contact** (her email; her number once inbound works), next to the guest's
   name — in the read-back too, word for word.
2. **Inbound SMS and voicemail → the reservation** (matched by the venue's number), shown to the guest verbatim.
3. **The confirmation email after every phone booking** (point 3): to the venue's published address, Sasha copied,
   the guest BCC'd — restating what, when, how many and the name. **Unclear outcome:** the *"I just spoke with you…
   can you confirm…"* version. A reply lands on the same reservation.
4. **The after-hours email to the same reservation** (S-67 follow-up).
