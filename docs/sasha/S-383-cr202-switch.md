# Sasha 383 — CR 202's Sasha half: every product switch goes to AgAPI's ONE writer

AgAPI owns which product a shared WhatsApp conversation is in (`wa_conversation`, agapi CR 202, v1.93.0). Sasha's half: every time the
person switches product on Kanoe's shared number — a keyword, a tool's menu row, the back row, either direction — Sasha calls
`messages.whatsapp_switch {from, product, message_id}` (the inbound's own MessageSid), once.

## The one place
- **`products.space.conversation_switched(product)`** — the ONLY caller of `venue_submit.whatsapp_switch` (a test pins it). The number and
  the message come from THIS turn's signed WhatsApp message (the door: `venue_submit.WA`); no WhatsApp door → nothing (a switch on the
  web is not a WhatsApp conversation's). Once per message and product.
- **Its two callers:**
  - the webhook (`inbound_phone._sms`): an EXPLICIT switch — `products.tools.switched_to(p)`, the registry's recognition (the back row,
    a tool's row tapped or typed, a tool's keyword at the start: "sasha", "diligence …", "campus …", "españa") — BEFORE AgAPI's inbound
    reads the message. Entering Applied Diligence never reaches Sasha's turn (AgAPI takes AD's words), so this is where it is told.
  - `products.space.set_space`: every switch Sasha's own turn makes (a product entered or left in `product_turn`, a reply to a
    product's message, "switch to RelocateMe" in the chat) — when the space CHANGES on a WhatsApp turn.
- The product is the registry's (`travel` for Sasha's own; `diligence`, `health` for España, `relocation`, `campus`).

## Product state Sasha still holds (listed, as CR 202 asked) — none of it is "which product the conversation is in"
1. **`products/space.py`** (`s2_memory` kind "space", per ACCOUNT): which of Sasha's spaces an account is in, across the web, S2 and
   WhatsApp — `sasha.turn` reads it for its context line. Per account, not per number; AgAPI has no read of its record. Every change of
   it on a WhatsApp turn now tells AgAPI (above). Applied Diligence is never written here (Sasha 379b retired AD's space).
2. **`guest_wa_state.pending {kind: "product", product, step, touched, parked}`** (`products/whatsapp.product_turn`): the STEP of a
   dialogue inside Sasha's own tools (España, Relocation, Campus) and the ones set aside (parked) — the dialogue's own state, which AgAPI
   doesn't run.
3. **`app/agent/sasha.py` `GET /api/agent/space`** (`space_now`): the web's read of (1).
4. **`products/tools.py`**: the registry that RECOGNISES a switch (its words and rows). It keeps that; it keeps no state.
- No Sasha path forwards AD context of its own: `inbound_phone.for_ad` sends only this message's files, the message it replies to and
  a linked guest's email — never AD's held tokens or case (AgAPI's `ad_door.held()` is their one reader).

## Tests
`backend/tests/test_s383_one_switch_writer.py` — through the real `/twilio/sms` route: every switch path (the back row, Due diligence's
row, Campus visits' row, "diligence", "diligence <question>", "Sasha", "campus", "españa") → exactly ONE `whatsapp_switch` with the
inbound's message id, BEFORE AgAPI's inbound; a switch Sasha's turn makes → once; a message that switches nothing → none; Tyler's proof
sequence → two switches (diligence, then travel). One writer (only `products/space.py` calls it). ONE TRUTH T98.
