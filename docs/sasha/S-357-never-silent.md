# Sasha 357 — no inbound message is ever dropped silently

**Found:** Sasha 355 failed CLOSED on a database error: the step wasn't recorded, so nothing was handed to AgAPI. That was logged, but the person heard nothing. A storage error in `dispatch` also returned an empty answer. 348's rule is that nothing is silent.

## The ONE outcome — `booking_signer/inbound_outcome.py`

This is the server side of 348's `lib/outcome`. Every WhatsApp message ends in exactly one of:

| Outcome | What the person reads |
|---|---|
| handled | its reply |
| refused | a reason: the model's daily cap is `CAPPED` ("…try again tomorrow", never "send it again"); not linked, AD's closed beta and the credit line keep their own reasons |
| failed | "I couldn't take that just now — please send it again.", in their language (en, es, fr, it, pt, de, read from their own words) |

A failure **after an act** (a table asked for, a payment opened) never says "send it again", because resending could repeat it. It says what was already done (`sasha.what_happened`).

**Failure points raise their cause; they never write a line of their own:**
- the message's step record: `first_step` / `step_done` raise `Failed`. It is still closed, never handed on.
- the guest's record (`dispatch`): no more silent empty answer.
- AgAPI down in AD's space (`diligence.hand_over`): its `DOWN` line is gone.
- the model (`turn_with_quiver`): its "Sorry — something went wrong" is gone.
- a tool error.

**Two boundaries, one source of words (`words_for`, which names the cause in the log once):**
- the webhook (`inbound_phone.sms`): the line goes in its TwiML and onto the conversation record.
- the background turn (`guest_whatsapp._turn`): the line goes through `deliver`, which records it (349).

**A reply is words, or another's answer** (`Out.answered_by`, e.g. AgAPI answering AD from Kanoe's number). An empty delivery is not a reply. The outcome knows a reply left by its own count (`replied` / `replies`), not by the typing dots, which may not exist. That was the silent path for a model that returned no words.

**Deliberately no message (unchanged rules):**
- a venue is never answered (S-75);
- nothing is sent to an unverified number (CR 100 / 269);
- an unknown sender hears the link line at most every ten minutes;
- STOP is silence.

## Tests — `tests/test_s357_never_silent.py`

Every failure point goes through the real webhook:
- the database (the message's step; the guest's record);
- AgAPI down in AD's space;
- the model capped;
- the model refusing (no words);
- a tool error;
- in Spanish.

Each ends in exactly one message to the person, with its cause named in the log and the line on the conversation record. Nothing reaches AgAPI twice. A scan fails if any of the old one-place failure lines is still in the code.

Suite: 3381 tests. The only failures are the 2 baseline ones.

## Proven (7 Nov, production's code f8d25057 and production's settings)

Run through the real signed webhook route, on the sandbox number. The person is a fictional guest (+15005550142, an in-memory link). AgAPI and the model were stood in; agapi-live was never called.

| Forced failure | The person receives | The log names |
|---|---|---|
| 1 · database: the message's step | the failed line · AgAPI reached 0 times | `step agapi_in … not recorded in guest_message_steps (ConnectionError …) — fails closed` |
| 2 · database: the guest's record | the failed line | `StorageUnavailable: db_down …` |
| 3 · AgAPI down, in Due diligence | the failed line | `AgAPI didn't take a message in AD's space: upstream_unreachable` |
| 4 · the model's daily cap | the capped line | `ModelBudgetExceeded …` |
| 5 · the model refuses (no words) | the failed line | `a turn ended without its reply` |
| 6 · a tool error | the failed line | `RuntimeError: search_flights failed` |
| 6b · the same, in Spanish | "No he podido recibir eso ahora mismo — por favor, envíamelo otra vez." | — |
| 7 · 355 on sasha-prod's `guest_message_steps` | first delivery → AgAPI True; Twilio retry → False | the test SID's rows deleted (0 left) |

On the conversation record: 5 failed lines and 1 capped line. Case 2's line could not be recorded, because its record was what failed.
