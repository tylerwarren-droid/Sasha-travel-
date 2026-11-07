# Sasha 356 — every message's header is composed in ONE place

**Found (Tyler, 7 Nov 06:57):** "Sasha · ✈️ Travel — where would you like to go?" came twice in one WhatsApp message, once in italics and once plain.

**Root cause:** the header had two writers. The product wrote it as the body text (`products/whatsapp.py`: the "Kept —" hand-off and the exit back to Travel appended `space_line`), and `switching.label_space` wrote it again as the italic label on the same message.

**Fix (one source, one composer):**
- A message *declares* its header: `Out.header = ("space", product, entering)`, which is the tool registry's line (Sasha 343), or `("now", label)`, the journey's "Now: …". `label_space` / `label_first` only declare it.
- `booking_signer/switching.compose(out)` is the only code that writes a header. It writes it once, in italics, at the top of the first text, or as its own line if the message has no text. It is idempotent.
- It is called in `guest_whatsapp._send`, which every outbound WhatsApp message passes through, and in `products/web.web_turn` (plain, because the web chat has no WhatsApp italics).

**Whole class (tests/test_s356_one_header.py):**
- It switches into every tool from the Menu and back to Travel, plus Campus visits → "later" (the "Kept —" hand-off). No message carries two headers, and each header is composed at the top.
- A scan fails if any file in `products/` or `booking_signer/` writes a header into a text itself.
- On main's code the test fails (the double header is reproduced). On 356 it passes.

**Suite:** 3370 tests. The only failures are the 2 baseline ones (test_venue_pick_230, test_stage_b_hooks booking_find).

**Deploy:** commit 16d9a688, Railway de2cf195, preDeploy replay gate PASS.
