# Sasha 343 · Naming (Tyler, 5 Nov 06:07, DECIDED)

**Sasha IS the assistant on every channel.** Travel, Due diligence (Applied Diligence), España, Relocation and Campus visits are things she does. No tool speaks as anyone but her.

## Root test (written first)

ONE place holds the words: the tool registry, `products/tools.py`. It has each tool's name, its one question on the switch, and its row's line. Everything else reads from it:

- **The welcome:** "Hi, I'm Sasha. I can help you with: ✈️ Travel · 🔍 Due diligence · 🇪🇸 España · 🏠 Relocation · 🎓 Campus visits". The rows are taps.
- **The switch:** "Sasha · 🔍 Due diligence — who should I investigate?" On every later reply in that space: "Sasha · 🔍 Due diligence".
- **The way back:** "← Everything I can do" (id `kanoe:tools`, the contract with AgAPI's AD menu).
- **Going back to travel:** "Sasha · ✈️ Travel — where would you like to go?"
- **Pointing to another tool:** "tap Menu → 🏠 Relocation". Never a word to type.

The second name lists are gone; each now reads the registry:

- `switching.SPACE_NAME` / `PRODUCT_LABEL`;
- `products/space.NAME`;
- `products/whatsapp.PRODUCT_NAME`;
- `me3.NAME`;
- `products/web.SIGN_IN`.

A hard-coded tool name or sentence would be a PATCH.

The tools' own sentences now speak as Sasha, for example:

- "CampusMe here 🎓 I read…" became "🎓 I read…";
- "RelocateMe gets your…" became "I get your…";
- "EspañaMe helps you…" became "I help you…";
- "CampusMe never submits it" became "I never submit it";
- "isn't read by CampusMe yet" became "isn't one I read yet".

**The whole class** (`tests/test_s343_naming.py`):

- the welcome, the switch line, the way back and the travel line are exact;
- every name map equals the registry;
- a scan of every string Sasha can send (`products`, `booking_signer`, `agapi`, `app`) finds no "You're in", no "say “<tool word>”", and no tool speaking as itself ("CampusMe here", "<brand> helps / plans / gets / reads / fills / never / needs…", "isn't read by <brand>").

## Kept, said

- **AgAPI's AD menu** still titles its back row "← All tools". Same id; Sasha answers the tap by its id. CR: retitle `ad_menu.BACK` to "← Everything I can do".
- **Brand names as labels, not speakers:** the web trip tabs ("Campus visits (CampusMe)"), Keep item labels ("CampusMe student details"), and HTTP user agents. A next step if Tyler wants them renamed.
- **Exception, not built now:** AD's messages to SUBJECTS will come from a separate, neutral Applied Diligence number.
