# Sasha 311 — STOP-SHIP: the number confirmation looped

## What happened (Tyler's account, read-only: the server log 10:47–10:51 UTC, and AgAPI's record)

| UTC | He sent | What ran |
|---|---|---|
| 10:47:30 | the DiverXO request | `venue.submit_booking` 409: the read-back, his card |
| 10:47:54 | "Yes" | `approvals.in_app_tap` 403 (number not verified), `approvals.request` 422 → `confirm_number`: "send me this message: Kanoe link 119218" |
| 10:49:32 | "119218" | no AgAPI call: Sasha's code match (`_LINK`) needed the word "link". The bare code went to the model: "send the whole message" |
| 10:50:52 | "Kanoe Link 119218" | `users.confirm_whatsapp` → verified. AgAPI's record says so now: +346•••15 `verified` |
| 10:50:59 | "Yes" | **no tool call, no AgAPI call.** The model repeated the code request |

Nothing reached DiverXO.

## Root test (written before code)

1. **The ONE truth.** AgAPI's verified-number record for the person (`destinations.verified`, read with `users.register` and no destinations given).
   - Sasha says "confirmed" only after reading that record back as verified (`venue_submit.whatsapp_verified`).
   - It does not rely on `confirm_whatsapp`'s answer alone.
2. **The second copy.** "Confirmed" was a TwiML reply sent from the webhook, OUTSIDE her conversation history.
   - The model's history still ended on "send me this message: Kanoe link 119218", followed by "119218" and "send the whole message".
   - So his "yes" was read against the code request, and the model repeated it without calling a tool. The held read-back was never tried.
   - It wasn't the capital L: `_LINK` is case-insensitive. It wasn't a different end user: AgAPI's record shows the number verified.
3. **Whole class.** Confirm → read AgAPI's record back → only then "confirmed".
   - The exchange is written into her conversation, and the held read-back is marked `number_confirmed_at`.
   - His very next yes runs `book_venue` on that read-back **by code** (`sasha.turn`), not the model.
   - The bare code works in any case and any wrapping, but only a code waiting for THIS account. Another account's code is never consumed (`peek_code`).
   - A refusal AFTER confirmation is said plainly and the hold is dropped: never a loop.
