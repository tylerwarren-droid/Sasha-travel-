"""Sasha booking-task signer.

Mints the signed booking tasks the Sasha booking helper (a Chrome extension) runs on the user's own
machine. The full contract is docs/sasha-contract/README.md.

  * keys      — reads SASHA_BOOKING_TASK_SIGNING_KEY; refuses anything but base64 of exactly 32 bytes
  * canonical — the exact bytes a signature covers, matching the helper byte for byte
  * issue     — the issue path, refusals in contract order (parity-tested against the reference signer)
  * verify    — pairings and device reports
  * venues    — the one specified venue (Restaurante Psi): particulars → task, read-back, hashes
  * outcome   — a verified report → the contract's outcome and words
  * store     — where intents, devices, task digests, reports and reservations live (sql/ is the schema)
  * account   — whose booking it is: today, always the one demo account
  * routes    — /api/booking/*, MOUNTED in app/main.py (S-17) by a line Stage B re-applies

⛔ Live submission is off here as well as in the helper: only dry runs can be recorded or signed.

⚠ This package lives in backend/, OUTSIDE backend/app/, because a CTO drop rsyncs backend/app/ with
--delete: anything inside it that is not in the CTO's zip is deleted.
"""
