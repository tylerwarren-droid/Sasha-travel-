# Sasha 309 — one read-back, one yes, it goes (WhatsApp)

## What happened (Tyler's account, read-only: his WhatsApp history and the server log, 29 Oct)

- **10:00:34 — "Book DiverXO for 2 people on Friday 13 November at 21:00 hrs".**
  - His words named the venue, the day, the time and the party, so Sasha 287's rule took **his request as the yes** (`venues.kanoe_card` → `_kanoe_now`). Nothing was shown to him first.
  - `venue.submit_booking` returned 409 `approval_required`: AgAPI made the read-back.
  - His typed WhatsApp yes was tried as the approval (`approvals.in_app_tap`, session kind `whatsapp`) and refused, 403 `approval_untrusted_origin`.
  - The fallback, AgAPI's one-tap link (`approvals.request`), was refused too, 422 `invalid_input`: "That WhatsApp number isn't verified yet".
  - Sasha still returned `waiting_for_their_tap` and said "Tap Yes on your phone and it goes". Nothing had been delivered. The place cards ("See the places", an image) came with it.
- **10:02 — "Yes".** The model apologised and wrote a second confirmation.
- **10:06 — "Yes" again.** The same refusals, then "tap Yes there … Do you want me to ring them as well?"

Nothing went to DiverXO.

**THE CAUSE.** AgAPI takes a WhatsApp yes only from the person's **verified** number (CR 99, `in_app.verify_whatsapp`). Tyler's number was linked before CR 100, and on agapi-live it is `NOT verified` (read with `users.register`, no destinations given). So no yes on WhatsApp could ever count. Sasha ignored the refused link and said "tap Yes".

## The decision: a typed yes, or the button, from the person's verified number IS the approval (CR 99)

The ticket asks to pick EITHER a real interactive Yes button whose reply is the signed approval, OR a typed yes from the verified number. They are the same path: a quick-reply tap on WhatsApp arrives as a reply message from that number, exactly like a typed "yes". So both stand on one binding:

- **The message.** Twilio's signature proves it came from that WhatsApp number.
- **The binding.** Sasha HMAC-signs (`SASHA_AGAPI_TAP_SECRET`) the sender's number, that message's id, the read-back id and **the read-back's own sha256**.
- **AgAPI's checks.** The number is the read-back's person's VERIFIED number. The tap is fresh. Its nonce and its message id are used once.

**You can't approve a read-back you weren't shown.** The read-back goes to that WhatsApp chat, and the yes must come from the verified number of the person it was made for. It is bound to that read-back's hash: a changed read-back voids it (`approval_void`), and a used one can't be used again.

A number linked before CR 100 is verified **once**, the CR 100 way: `users.link_whatsapp`'s code, sent FROM the number (`users.confirm_whatsapp`, Sasha-signed). Sasha now asks for it at the moment it's needed, and accepts it from an already-linked number. A code Sasha wrote itself is never accepted: possession must come from the number.

## Root test (written before code)

1. **ONE truth: the prepared request.**
   - The request is AgAPI's read-back of the exact message (`venue.submit_booking` → `approval_required` + `read_back_id` + lines + `read_back_sha256`). It exists BEFORE she says anything.
   - The card she shows IS those lines.
2. **No copy.**
   - "Shall I send?" and the button come from the same step that made the read-back (`kanoe_card`).
   - Nothing prepared → no card and no "ready".
   - A yes that can't go yet is said as it is (`confirm_number`, `NUMBER_*`), by code, and the turn ends on it. Never "tap Yes" with nothing to tap, and no call offered on top.
3. **Whole class.**
   - Every route that reads back through `kanoe_card` (Kanoe's email, Kanoe's WhatsApp) shows the complete request first. One yes (tap or typed) sends it, through the one send (`_agapi_send` → `venue_submit.submit`).
   - `test_s309` fails if a yes leads to a second confirmation, or if a refused link is said as "tap Yes".
