# Sasha 350 · every WhatsApp message shows it's being worked on, from its arrival until its reply lands

FROZEN BETA LIST: SME demo. This ticket follows the NO PATCHES rule. Unblocked by CR 174: AgAPI's ONE typing sender, the op
`messages.typing {message_id}`. It works only on a message this account's inbound op has seen; the dots last until a reply or 25 s; AgAPI keeps no timer.

## The one place

`backend/booking_signer/wa_working.py`, started in `inbound_phone.sms`, where every WhatsApp message first arrives, before any tool's door.

- **At once:** `messages.typing` on its MessageSid.
  - AgAPI's inbound op records the message first thing (autocommit), so a call made while the op is still working (AD's action included) shows the dots.
  - Until the op has recorded it, the call is retried for a few seconds.
- **Refreshed** every 20 s, tied to THAT message.
- **Ends when its reply leaves:**
  - The webhook's own answer: a TwiML reply, AgAPI having answered in its op, or nothing to say. The hold settles as the webhook returns.
  - A guest's turn in the background: `dispatch` keeps the hold, and `deliver` ends it as the reply leaves. Every reply goes through `deliver`, including the told failure (348). The turn's end ends it too, when it had nothing to send.
  - Never longer than 5 minutes.
- **Twilio's retry of the same message** is the same hold.
- **A newer message from the same person** supersedes the older one's hold (Twilio shows the dots on the latest).
- **Every call is logged** with Twilio's status, or AgAPI's refusal and its words.

There is no typing call anywhere else, no second sender, and no "working on it…" text. A test scans for each.

## Not covered (said)

Sasha 344's switch taps ("← Everything I can do", a tool's row) are answered at once by Sasha's own menu and never reach AgAPI's inbound op. AgAPI refuses dots on them (`not_found`, logged). Their reply is immediate.

## Tests

- `backend/tests/test_s350_working.py` covers:
  - the hold: at once; refreshed; settled; kept until deliver; retried until seen; a refusal said and not retried; retry and supersede; the cap;
  - the one place;
  - no second sender, no per-tool call, no working text.
