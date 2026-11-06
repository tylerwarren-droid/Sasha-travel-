# Sasha 349 · the conversation has ONE owner, and her words travel WITH her cards

FINISH LIST line 4 (the SME demo). This ticket follows the NO PATCHES rule. Tyler, 6 Nov 07:06–07:13.

## What was seen, and the cause of each

**(a) WhatsApp: "Carry on" went to AD.** "Picking up: Flight Madrid → London…" was sent by Travel: S2's "Continue on my phone" (`handoff_phone` → `guest_whatsapp._tell`). His space was Due diligence at the time, and in that space `diligence.claims` takes every message, so "Carry on" was handed to AD.
- **Cause:** no message out named the tool that sent it, so a reply could only follow the space.

**(b) S2: switching tabs and back, the chat was gone.** It was not SQLite, as the ticket supposed. S2 restores from `s2_memory` in Postgres. But `recall()` returned the conversation only when there was a "welcome back" line (a `thing` from the last 24 h), and the page also stopped at `if (!line) return`. Even when it did restore, the record held only masked text and the last venue cards.

**(c) S2: "listed on your screen", with no cards.** S2 drew none of `flights`, `stays`, `flight_chosen`, `total`, `pay` or `trip`. Sasha 236/283 had turned each of them into a one-tap trip-board card. The server still counted them as drawn, so neither the 251 nor the 345 honesty guard fired.

**(c′) The Trip tab's placeholder** ("0 days, 2 travellers, Planner's guess $0, Continue on my phone"), shown on his phone.
- A flight search created a trip record to hold its offers (`_offer_flights` → `plan_store.single`).
- `passengers` defaulted silently to 2.
- The summary showed the CTO itinerary's US-dollar guess when the trip record had no priced line.
- "Continue on my phone" didn't check the device.

## The one source for each

**The conversation: one record per person in sasha-prod.**
- It is `s2_memory.messages`: every message in and out, on S2, /next and WhatsApp. Each message is `{at, dir, ch, tool, text, cards?}`.
- An outbound message names the tool that sent it: a space, where "sasha" is travel.
- `recent` (what the model hears) is read from it, not kept as a copy.
- `recall()` always returns it.
- WhatsApp writes to it where messages arrive (`turn`) and leave (`deliver` and `_tell`). AD's reply is written when Sasha hands the message to AgAPI.

**A reply is ONE payload: its text and its cards.**
- The S2 stream keeps each reply's card events with its text in the record.
- The page draws a live turn and a returning conversation through one mapping, `cardsOf`.
- What /s2 can draw is one list: `sasha.S2_DRAWS`, which a test holds equal to S2App's `S2_KINDS`. A card kind the surface can't draw never counts as shown, and the model's tool result says "nothing from this was shown on their screen".
- 345's phrase guard is retired.

**A reply answers the tool that spoke last** (`guest_whatsapp._follow_last_tool`). The record names the tool of the last message sent on WhatsApp. Unless the message itself picks a tool (a tapped row, or its word), the space moves to that tool: the current product steps aside (kept), and the other resumes.

**No trip until one is chosen.** A search that belongs to no trip keeps its offers on the record (kind `offers`). Those offers are the cards she shows. `choose_offer` makes the single-flight trip from the one picked; "book it" before a pick asks which. The Trip tab therefore holds only what was chosen or booked. `passengers` defaults to 1, the person asking.

**Money in the record's own currency.** The Trip summary shows the record's € total, or "—" until something is priced. The CTO itinerary's own figures say "US$" plainly.

**One phone rule.** `lib/device.ts` `usePhone`, used by /next and the Trip panel. "Continue on my phone" is never shown on the phone.

**Silent mode.** One switch on S2, labelled "Silent mode", with the 🔊 icon folded into it. It is kept on the person (record kind `silent`) and read by `voice.silent`:
- no spoken line leaves an S2 turn;
- WhatsApp answers a voice note in text.

## Retired, or not done (said plainly)

- **Retired:** 345's `promises_card` phrase guard; the trip-board card as a stand-in for options; S2's localStorage mute.
- **Existing placeholder trips** made by the old rule are repaired by the SQL FOR CHAT in the report: delete draft single-flight trips whose basket holds only suggestions.
- **AgAPI's own unsolicited sends** (an AD notification it sends by itself) are not in Sasha's record. Sasha records each hand-over to AD, but not a message AgAPI starts. The root fix is a CR: AgAPI reports each send to the person's record.

Tests: `backend/tests/test_s349_one_conversation.py`, plus 280, 249 and 253 rewritten to the new rule (the pick makes the trip).
