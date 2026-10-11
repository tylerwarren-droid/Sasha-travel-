# Sasha 239 — report (11 Oct 2026) · CR 82, the memory slip, WhatsApp for Tyler + Jon

## Live
- Backend **62d11f0**, Railway **a0d36d66** SUCCESS, DEPLOY GATE: PASS (149/149, $1.06 / 243 calls). One deploy, pushed with none running.
- Vercel production for 62d11f0: **ERROR** (dpl_FZXtnP3u6TjS8AfqUh2P3fjVAsy3). The same sha built **READY** as the branch preview (dpl_AC9GU1a5y7zcbaLjs51dN2iKEd7S), and `npx next build` passed here, so the code builds.
  - The production log isn't retrievable ("deployment not found" from Vercel's API).
  - This report's commit re-triggers the production build; its result is in the mailbox row.
- Units 2011 OK. **S1 fingerprint byte-identical.**
- Commits: a1bc584 (merge CR 82) · 62d11f0 (the memory handover).

## 1 · CR 82 merged: DONE
`cr/82-s2` @ 0ecab11 (stacked on cr/81-s2); no conflicts. It adds activity sources, price "for", "Free for", and `form_prepared` for claims to airlines that take only web forms. WhatsApp's activity lines now name the source too.

**Proof** on /s2, scratch guest: "What should we do in Madrid on Saturday 17 October?" The ActivityCards from the render event:
- Museo Nacional del Prado · open 10am–8pm · general admission: 15 EUR · **SOURCE: esmadrid.com — Madrid city council's tourism site**
- Real Madrid · no event that day · **SOURCE: laliga.com — the league's own fixtures** (she: "They play Sevilla at 19:00" on Sunday)
- Reina Sofía · 10:00–21:00 · entrada individual general: 12 EUR · free for Mayores de 65 años · its own site
- Thyssen · 10:00–23:00 · entrada general: 14 EUR · free for menores de 18 · its own site
- Palacio Real · 10am–6pm · esmadrid.com

**For CR:** the Palacio Real's "free for" text is really a free *window* ("Monday to Thursday from 5pm to 7pm…"), which CR 82 meant to keep separate.

## 2 · Memory handover: DONE
- **The change:** memory now keeps `decided`. It is set only by a real choice (a tap → `read_booking_route` with that card's place_id, or a held read-back), and cleared by a new search.
  - The welcome line says "you'd chosen X" only then; otherwise "we were looking at…".
  - On the first turn back, the model is told exactly what was and wasn't chosen, for /s2 and WhatsApp alike.
- **Proof**, scratch guest 7d4b181d on production /s2, coming back as the page does (memory, then the first turn on a new session):
  - **Browsed 5, picked none:**
    > LINE: "Welcome back — we were looking at restaurant in Gran Vía, Madrid, Saturday 17 October 21:00. Want to carry on?"
    > she: "We were on a table for two near Gran Vía, Saturday 17 October at 9pm. **You haven't picked a place yet, so nothing's booked.**"
  - **Tapped Beata Pasta** (`read_booking_route`, then the route question):
    > LINE: "Welcome back — **you'd chosen Beata Pasta - Gran Vía** (restaurant in Gran Vía, Madrid, Saturday 17 October 21:00). Want to carry on?"
    > she: "You'd picked Beata Pasta - Gran Vía for two, Saturday 17 October at 9pm. Nothing's booked yet…"

## 3 · Tyler + Jon on WhatsApp: DONE (Jon's link is his to do)
- **Tyler:** linked (number ending 715, not opted out, consent v3), and on the agent brain (`SASHA_WA_BRAIN=agent_for:` founder + Jon).
- **Jon:** still no linked channel. His steps on his phone (/you → "WhatsApp — link my number" → tick → "Get my link code" →
  "Open WhatsApp ↗" → send `LINK <code>`) and a 5-message test for both of them are posted in mailbox row **724**.
  - The test: a table, the Keep, a passport photo, a voice note, "thanks".
  - It warns that [Yes] on their real accounts really contacts the restaurant.
- No message was sent to either number.

## Cleanup
Scratch guest 7d4b181d deleted (200), with 0 rows left in any public/auth table.
