"""Sasha booking-task signer — FOUNDATION ONLY.

Mints the signed booking tasks the Sasha booking helper (a Chrome extension) runs on the user's own
machine. The full contract is docs/sasha-contract/README.md.

What exists today:
  * keys.load_signing_key()  — reads SASHA_BOOKING_TASK_SIGNING_KEY and refuses anything that is not
                               base64 of exactly 32 bytes (an Ed25519 seed)
  * canonical.canonical_json — the exact bytes a task signature is computed over, matching the
                               helper's canonical form byte for byte

What does NOT exist yet, on purpose: nothing here signs a task, and nothing is mounted in app/main.py.

⚠ This package lives in backend/, OUTSIDE backend/app/, because a CTO drop rsyncs backend/app/ with
--delete: anything inside it that is not in the CTO's zip is deleted.
"""
