# Sasha 355 · one inbound message is handled exactly once

FROZEN BETA LIST: SME demo. This ticket follows the NO PATCHES rule.

## Found (Sasha 350's live log, 7 Nov)

Every WhatsApp logged "MessageSid not checked: CheckViolationError … guest_inbound_sids_message_sid_check".
- **Cause:** Sasha 294 wrote derived keys (`agapi-in:<sid>`, `agapi-took:<sid>`) into `guest_inbound_sids`, whose check accepts only a plain Twilio SID.
- **Effect:** every key was refused, and `first_time()` failed OPEN. Every Twilio retry was handed to AgAPI again, and "AgAPI took it" was never recorded.

## The root

**A record of its own** for each message's processing steps: `guest_message_steps`, created by `sql/058` (applied 7 Nov 07:37).
- Its columns are `message_sid`, with Twilio's own check, and `step` (`agapi_in` | `agapi_took`).
- It is keyed as written, one row per step.

**`guest_inbound_sids` keeps exactly its own job:** one turn per MessageSid.

**`guest_whatsapp.first_step(sid, step)`:**
- records a step once; a retry gets False;
- a database error FAILS CLOSED and is named in the log: "step … NOT recorded (…) — not done again: the check fails closed".

**`step_done()`** reads, and is named on error.

**`inbound_phone._sms`** hands a message to AgAPI only on its first `agapi_in`. A retry of a message AgAPI took (`agapi_took`) stops there.

## Proven live (7 Nov, production's code and sasha-prod's table, a fresh test SID, its rows deleted after)

| Case | Result |
|---|---|
| First delivery: hand to AgAPI | True |
| Twilio retry: hand again | False |
| AgAPI took it | recorded; the retry sees it |
| On the record | `agapi_in`, `agapi_took` |
| A database error (simulated) | False, named in the log as above |

The deployed service (35579b0f) logs no "MessageSid not checked".

## Tests

`backend/tests/test_s355_one_message_once.py`: each step once; a database error fails closed and is named; a retry through the webhook reaches AgAPI once; no derived keys anywhere; 058 on real Postgres (applied twice; a derived key is refused).
