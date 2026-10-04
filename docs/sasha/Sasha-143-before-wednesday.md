# Sasha 143: before Wednesday

*4 Oct 2026. Commit 270bd94 (gate green), plus the commit carrying this report.*

## 1. Bland

**The balance, read via the API:** `current_balance = 19.91` (it was −0.087). Auto-refill is still not set.

**One test call to the test line** (`SASHA_TEST_CALL_NUMBER`, the founder's mobile; English; 1-minute cap; not
recorded):
- Call id `ed4770da-0c8c-4d09-8102-db4bad081535`.
- **Completed**, answered by a human, 0.67 min.
- Opening said: "Hello, this is Sasha, an AI concierge from Kanoe Technologies SL, calling on behalf of the Warren family
  to book a table for two on Monday at nine in the evening. Is that possible?"
- Heard from the line: "Yes." · "Yes." · (a number) · "Bye."
- Calls work again.

## 2. Open items, fixed and live

1. **/voice acts for the founder.** It now resolves the account as the chat does:
   - signed in with the founder passphrase → through `/api/sasha/…` → his account;
   - a guest → their token;
   - anyone else → the public demo.
   - Test: `test_public_demo_s142.TheVoicePage`.
   - **Also found and fixed:** the page called `/voice/conductor` and `/voice/tts`, which were **404 live**. The backend
     mounts them under `/api`, so the page's microphone and spoken reply had not worked.
2. **The web hotel hand-off** ("a hotel in Madrid, Spain from 2027-03-01 to 2027-03-04 for 1").
   - **Cause:** the web's hotel cards came only from a curated list (and a model-written one) with no Madrid. The turn
     fell to the general chat, which either failed (CR's "brief connection issue") or, with a conversation behind it,
     **promised cards that never came** (reproduced: "you'll see them in a moment", 0 cards).
   - **Now** (`booking_signer/hotel_web.py`):
     - The stay is read as WhatsApp reads it (shared `stay_of`) and found as WhatsApp finds it (Google, `/venues/find`).
     - Three real hotels, each with "Reserve (TEST)" pre-filled with the stay's check-in, nights and party.
     - The card shows Google's rating and address. **No price is shown, because none is known.**
     - When nothing is found, it says so.
   - Live: Madrid → GARDEN HOUSE MADRID, ARTIEM Madrid, Catalonia Plaza España, in 1.4 s.
   - Test: `test_hotel_web_s143` (4).
3. **The empty opening bubble.** A product tab's opening turn is an empty user line in the server's history; it is no
   longer drawn. Checked live on /preview/relocateme: only Sasha's line shows.

## 3. The six-tab pages → their /agapi tab

| Old page | Now redirects to |
|---|---|
| /sasha | /agapi#sasha |
| /applied-diligence | /agapi#applied-diligence |
| /campusme | /agapi#campusme |
| /relocation | /agapi#relocateme |
| /spain-services | /agapi#espaname |

- The redirects are `next.config.ts`, temporary (302). Each one was checked live.
- **CR:** its preview banner already reads "linked from the AgAPI hub" (9751d4d); it ships with CR 17.

## 4. Places after f72174d

- Railway's active deployment, with f72174d and everything after it, went live at **10:23 UTC**. The fixes in this turn
  redeployed several times before that, so earlier buckets are pre-fix.
- One watcher cycle run DRY on the live code (nothing sent, called or claimed) made **0 Google listing reads**.
- The mailbox sync (every 6 h) now reads no names either.
- The post-deploy 10-minute counts are in the readout. The overnight figure is to be read on the morning of 5 Oct.

**For Wednesday:** every deploy empties the photo cache. **Pre-warm after the last deploy**, never before
(Sasha 140).
