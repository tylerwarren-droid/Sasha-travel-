# Sasha 331 · How she'll book and why, in one line

Tyler, 3 Nov 19:50: "she doesn't say the place has no form or WhatsApp, or why or how she decided to send the request."

Decision (Tyler, 3 Nov), amending rule 15 (15 Oct): before the one booking question, she says ONCE, in one short positive line, HOW
she'll book and WHY. It comes from AgAPI's own decision, never her guess. There are no lists of what she checked, and the rest of the
15 Oct rule stands.

## Root test (written before the code)

### 1. The one source

The one source is AgAPI's decision (`venue.profile` → `handoff.decide`, CR 107 and the CRs after it).

**Its fields:**
- `route`
- `channel`: the platform's name, or the message channel (email, WhatsApp, Instagram)
- `sender`: kanoe or the person
- `row`: `call_at_opening` or `call_no_voice`
- `hours.opens_at`

**The reason** is AgAPI's ordering. `decide()` takes the first route that applies:
1. their own form;
2. its robot check;
3. a phone booking page;
4. Google;
5. a platform;
6. a message;
7. no reservations;
8. a call;
9. the floor.

So the route itself is the reason. For example, "message by email" means no form and no platform, and "call" means no form, no platform
and no message channel. Sasha decides nothing.

**The line, in one place for every channel:** `voice.route_line(decision)`. It is ONE table keyed by AgAPI's (route, channel, sender,
row).
- **The line reaches the person** as a told line: `venues.hold_venue` puts it on the booking question's result (`route_line`), once
  per booking. `sasha.turn` then puts it in front of her reply, said by code, on S2, WhatsApp and voice. It is the same text
  everywhere, and voice gets it through `spoken.speakable`.
- **The checks accept only this line:** `voice.is_route_line` recognises exactly those sentences. The channel-word and
  limits-the-channel checks (`faults` and the turn's guard) let them through and nothing else.

### 2. PATCH check

- **No sentence is written per channel.** WhatsApp, S2 and voice say the same line; voice only makes it speakable.
- **The wording table lives in Sasha, not in AgAPI.** It isn't a second decision, because every line is keyed by AgAPI's fields and
  Sasha decides nothing. Still, AgAPI's `say_text` is the root for her words: **PATCH (said):** the "how + why" line is Sasha's
  wording of AgAPI's route. The follow-up is for AgAPI's decision to carry this line itself as its `say_text` (proposed CR).

### 3. Whole class

- Every route AgAPI can return has its line (a test walks AgAPI's ROUTES).
- The floor (`none` / `none_listing`) says its own words: no line is added.
- No route is said without AgAPI's decision: no decision means no line.
- The line passes `speakable` with no marks left.
- The line is said once per booking: a second hold of the same booking adds nothing.
