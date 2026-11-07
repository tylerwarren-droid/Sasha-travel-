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

## One level in (Tyler, 7 Nov 08:02–08:03)

The live proof showed the header once ✅. But each tool's own greeting re-stated it:
- Due diligence: "Applied Diligence — who should I investigate?" under "Sasha · 🔍 Due diligence — who should I investigate?"
- España: "🇪🇸 España — Spain's public processes, done with you." under "Sasha · 🇪🇸 España — what do you need done in Spain?"
- Relocation (found by the test): "🏠 Relocation — I fill Spain's residence forms…"

**Source:** all three came from Sasha's own code (`products/diligence.LINE`, `products/health/turn.ES_MENU`, `products/relocation/turn.py`). AgAPI's code has neither line (checked on agapi main), so nothing goes to CR/AD.

**Fix (at the source):**
- The composer owns the tool's identity and its question, both from the registry. A tool's body carries only what is new: España's list, Relocation's "first application or renewal?", "Back to your EX-01. …".
- Due diligence's greeting *was* the identity and the question, so it now declares it (`diligence.asks`: the header is the whole message), on entering and on resume.
- The switch header is now declared for everyone, WhatsApp and the web chat (`switching.declare_space`). Before, it was only for the switching accounts, and other guests would have lost the tool's name. The label on every message inside a tool stays for the switching accounts (Sasha 194).
- A message with nothing of its own (AgAPI answers AD from Kanoe's number) gets no header-only message.

**Whole class:**
- The WhatsApp walk fails if a body under a header repeats that header's tool name or question. Messages with buttons are now read too.
- A scan fails if any `products/` or `booking_signer/` string opens with a tool's identity ("🇪🇸 España —") or carries a tool's question. It catches all three old greetings.

**Suite:** 3371 tests. The only failures are the 2 baseline ones.
