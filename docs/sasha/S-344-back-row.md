# Sasha 344 · "← All tools" inside Diligence reached AD as text (Tyler, WhatsApp, 5 Nov 06:09)

## Root test (written first)

**What happened.** The webhook (`inbound_phone.sms`) hands EVERY WhatsApp message to AgAPI's inbound door FIRST (Sasha 285 / 294). That door is what lets a venue's reply or an "investigate …" reach AD. In AD's space, AgAPI took the Menu row's tap "← All tools" as AD text and answered "I can open a case if you tell me the company". Sasha's switch never saw it.

At 06:09, Sasha's switch would have recognised it: the title "← All tools" was still Sasha's back-row title. But it ran AFTER AgAPI's door, and it read a tap's id only from `ButtonPayload` (a quick reply's field), never from a list row's `ListId`.

**The ONE switch runs before any tool's door.** `products/tools.switch_tap(p)` recognises the back row (or a tool's row):

- by its id, `kanoe:tools`;
- or by its title text ("← Everything I can do", or AgAPI's "← All tools" on AD's menu);
- from WHATEVER field Twilio put the tap in: `ButtonPayload` / `ButtonText` (a quick reply), `ListId` / `ListTitle` (a list row), and `Body`.

`tap_fields(p)` is the ONE reader, and every path uses it: the webhook, the turn's tap, the payload and the body. The webhook asks the switch FIRST. A switch tap is Sasha's own: the guest flow answers it with the tools, and AgAPI's door is never called with it.

Not done: an exception for Diligence, or for any one tool. That would be a PATCH.

**Said PATCH.** AD's menu row title is AgAPI's and still reads "← All tools". It is accepted by its title only when no id came with the tap. It is dropped once CR retitles `ad_menu.BACK` to "← Everything I can do" (Sasha 343's ask).

**Field check.** Twilio's documentation doesn't name the inbound fields of a list-row reply, and Sasha logs no request fields, so the field that arrived at 06:09 can't be read back. The fix reads all of them. The test proves each shape.

**Proof** (`tests/test_s344_back_row.py`): the real `/twilio/sms` route, a linked number inside 🔍 Due diligence (the product is open), and the tap in each shape (`ListId`, `ButtonPayload`, title in `Body`, AgAPI's old title in `Body`). Each time:

- the tools list is sent ("I can help you with: …");
- AgAPI's door (`whatsapp_inbound`) is never called;
- AD's door is never called.

An ordinary message in AD's space still goes to AgAPI first, as before.

## The whole class (Tyler, 06:30)

Tapping "Show my cases" in Diligence sent AD "Show my cases\nYour cases, and the status of the one you pick". On a list reply, Twilio's `Body` is the row's title AND its description, joined. So AD answered with its default.

**The one reader.** `tools.tap_fields` reads a list row ONLY from `ListId` / `ListTitle`; if `ListTitle` is missing, it takes the title line, never the joined Body. `tools.normalized(p)` rewrites the message ONCE where it enters (the webhook and the turn) so that `Body` is the row's exact title. Every tool's door therefore receives the row as its exact title (AD) or its id (Sasha's own `kanoe:` rows). Twilio's `ListId` / `ListTitle` pass through untouched to the tool.

**By namespace, never by row.** `kanoe:` ids are Sasha's: the switch, a tool's row, a sentence row. Any other id is its own tool's (AD's `ad_…`) and reaches that tool by its title. A per-row workaround would be a PATCH; there is none.

**Proved** with real list replies: Body joined, `ListId`, `ListTitle`, AD's rows exactly as AgAPI's `ad_menu.rows()` sends them.

- "← All tools": the tools, and no door is called.
- "Show my cases", "Open a case", "Next steps": AgAPI's door, and AD's own door inside the space, each receive EXACTLY the title.
- Sasha's rows ("Start again", a tool's row) by their id.

**For CR.** `ad_menu`'s docstring says "a Menu tap arrives as its row's words (Twilio: Body = the item's title)". In fact Body is the title AND the description joined. AgAPI reading Body itself, outside Sasha's hand-off, would see the joined text; it should read `ListTitle` / `ListId` from the `twilio` params Sasha passes.
