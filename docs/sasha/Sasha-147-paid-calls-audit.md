# Sasha 147: test receipts, and an audit of every background loop for paid calls

*5 Oct 2026. Commit f1b3c95 (gate green, 1,092 backend tests).*

## 1. Test bookings no longer email the founder

**What happened:** on 4 Oct, 08:22–08:34, my speed harness booked our own test venue five times. Each booking emailed
"Your booking at Sasha Test Venue: Confirmed by the venue" to the founder.

**Now** (`guest_receipt.test_reason`), a receipt is **recorded as `test: not emailed (…)`** in `booking_receipts_sent`
and **never sent** when the booking is any of:
- at **our test venue** (by its name, and by the form's host);
- at the **Kanoe Demo Spa** or **Kanoe Demo Market** (marked `test` by the demo flows);
- a **call to the test line** (`venue_key test-line`, `is_test`, or a brief marked test).

A real venue's receipt is unchanged, and the test suite still drives the real email path end to end.

**Tests:**
- `test_ops_log_s144.TestReceiptsAreNeverEmailed`;
- `test_form_rung.test_the_test_venue_s_receipt_is_never_emailed`.

## 2. The audit: every background loop

| Loop | How often | Paid calls when idle | Paid calls when working |
|---|---|---|---|
| Proactive: reminders, day-before, morning brief | 60 s | **0** (names re-read only for a message sent; Sasha 141/142) | 1 listing read per message actually sent; Twilio per message |
| Proactive: **leave now** | 60 s | **0** | **Google Routes, every minute for a confirmed booking's last 3 h, and on after leave-now was sent; plus a listing re-read per minute when it had no address.** Fixed: the stored place ID (695c5da); Routes at most **every 5 min** per booking (the 10-minute window still always holds an ask) and **none after leave-now is sent** (f1b3c95). Worst case 12 an hour per booking, inside its last 3 h only |
| Proactive: no-reply offer, tap offer | 60 s | 0 | Bland or an email only on the guest's own yes, or a plan line covering it |
| Invitations watcher | 60 s | 0 (status only, no names; Sasha 142) | WhatsApp when a status changes |
| Call sweeper (+ scheduled calls, + email-reply re-reader) | 60 s | 0 (no placed call, nothing scheduled, no unread reply) | Bland GET (free) per placed call; **one** AI reading of each finished call |
| Calendar drain | 20 s | 0 (empty outbox) | Google Calendar (free) per change |
| Mailbox (Gmail) | 6 h | 0 | Gmail (free); rules only — the AI reader is off unless SASHA_MAILBOX_MODEL=1, and then only for a matched email the rules can't read |
| Products: expiry and reminders | 24 h | 0 | WhatsApp when a reminder is due |
| Campus watch | 24 h | 0 | the universities' own pages (free); WhatsApp when a session opens |
| Retention | 24 h | 0 (database only) | 0 |

**Not background:** the model agents' `while True` loops (golf, car rental, credit card, Smart Sasha) are per-request tool
loops, so they run only when someone asks.

**Edge left as it is, with its limit stated:** if recording a finished call's reading keeps failing, the sweeper retries
it every minute, and each retry re-runs the AI reading. It's bounded to calls in that state, and it's logged each time
("sweep could not read call …").

## 3. The test: an idle hour makes zero paid calls

`tests/test_idle_hour_s147.py`:
- **What it runs:** every loop body above that runs more often than daily, once a minute for 60 minutes, over an account
  with a confirmed phone booking in two days and an email request one hour old.
- **What it watches:** every outbound request, caught at `httpx` itself (Google Places and Routes, Bland, Anthropic,
  OpenAI, Twilio and Resend all go through it), plus every in-process listing read.
- **Idle result:** **0 requests of any kind**, 0 listing reads, 0 WhatsApp messages.
- **Second case:** a confirmed booking in its last 3 hours asks Routes at most 12 times an hour, and **0** after
  leave-now is sent.

## 4. Places, 30 minutes after 695c5da

The figures follow in the readout. 695c5da went live at 06:29 UTC.
