# Sasha 117 · Dress rehearsal of `docs/business/investor-demo.md`

*2 Oct 2026, 22:20–23:12 Madrid. The founder's account (the demo account), the Twilio sandbox WhatsApp, calls off.*

**How it was run**
- Every message from the founder was sent through the real, Twilio-signed webhook on production (`s117_say.py`). His
  phone received every answer live; Twilio showed the messages "read".
- Every answer below is quoted from Twilio's own record. Times are seconds from the founder's message.
- Bookings went only to **our test venue**. A rehearsal-only card (`SASHA_REHEARSAL=1`, founder's account only) makes it
  the third card; nobody real was contacted.

**The flood, owned:** this rehearsal sent **62 real WhatsApp messages** to the founder's phone (21:55–23:10). The
founder stopped it. From then on, every run is **simulated** (`s117_sim.py`):
- The real turn handler (`guest_whatsapp.turn`, as the webhook calls it) runs on his channel and on production data.
- The sender is a capture, so **nothing reaches Twilio**.
- Watchers are cancelled before the capture is removed, and his conversation state is put back afterwards.
- No further live message was needed. The one beat that needs him (reminders) needs **his own reply**, YES REMINDERS,
  to an offer already on his phone. It is his consent, not something to show him.

## Beat by beat

| # | Beat | Live? | What the founder's phone showed (exact) | Time | Broke or read wrong → fixed |
|---|---|---|---|---|---|
| 1 | WhatsApp booking with photos | **live** | "Dinner for 2 tomorrow at 9 near Retiro, something special." → "Special Dinner in Retiro, Madrid — 20 of 20 open at 21:00 by their listed hours. From Google Maps; nobody has been contacted." · "Sasha's pick · Gaditana Retiro · ★ 4.8 (2257 Google reviews)" · "Erre Que Erre Retiro · ★ 4.7…" (photo on the venues whose site has one) · "Rehearsal · Sasha Test Venue — ours…" · **Which one?** [3 buttons] | header 7 s, buttons 21 s | **(a)** every turn crashed: "Something went wrong on my side" (reminders-offer SQL type error) → `5db01f1`. **(b)** "Which one?" failed at WhatsApp, error 63013 (button titles cut at 25 characters; WhatsApp allows 20) → `64db27c`. **(c)** "distance not known" on every card; lower-case header → `64db27c` |
| 1 | → one sentence | **live** | tap "Sasha Test Venue" → "Exactly what I'll send: …" (the form's fields) → **"Book Sasha Test Venue for 2, Saturday 3 October at 21:00, under WARREN?"** [Yes, book it / No] | 10 s | **(d)** "I can't book Sasha Test Venue from here right now" — the form needs an email and WhatsApp sent only the mobile → `ff97b6c`. **(e)** read-back bullets "• ·" → `93f7b3f` |
| 1 | → yes → result → receipt | **live** | **"✅ Booked: Sasha Test Venue, Saturday 3 October at 21:00, 2 people. Their reference: TV-95A2C2-A2."** · "Their page said: “Reserva confirmada … Localizador: TV-95A2C2-A2 …”" · "Your receipt is in your email." | 7 s / 10 s / 13 s | **(f)** run 1 said **"⚠ Not confirmed yet … their page didn't say it's booked"** over a confirmed booking → `93f7b3f`. **(g)** the receipt named the web host, not the venue → `93f7b3f` |
| 2 | Proactive: day-before | **blocked** | nothing sent. The tick "as of 18:00" returned nothing: the account is on WhatsApp consent v2, so reminders stay off until he replies **YES REMINDERS**. The offer reached his phone at 22:25 | — | not a bug: his consent. Once he replies, `s117_state.py --tick 2026-10-02T18:00:00+02:00` sends it |
| 2 | Proactive: "confirmed in writing ✅" | **not possible tonight** | — | — | **gap:** Sasha files a venue's email onto a **phone** booking only (`inbound_phone.match_written` looks at booking calls). A form booking's emailed confirmation is quarantined. With calls off there is no booking it can land on |
| 3 | Calendar | **live** | the event "Sasha Test Venue · Booked by Sasha · 2 people · ref TV-95A2C2-A2", 21:00 Europe/Madrid, on "Sasha bookings" | 18 s after the yes | — |
| 4 | Invite Jon | **live** | "Book dinner with Jon this week near Retiro." → "Times you're free: • Sunday 4 October, 21:00" · the wa.me share link · "When they pick, I'll tell you here…". Jon's page: only Tyler, dinner, the time. Jon taps → **"Jon picked Sunday 4 October, 21:00. The booking is yours…"** + cards for Retiro | 7–13 s; inviter told 9 s after the tap | **(h)** Jon's tap took **23.7 s** to answer (it waited for the founder's place search) → `310abb4`. One time only: late Friday "this week" leaves Sunday (Saturday 21:00 was busy with the test booking). On stage say "next week" for three |
| 5 | Deposit (Tier 0) | **not live** | its sentence, rendered: "Casa Lucio needs €20 deposit for Saturday 3 October at 21:00, 2 people. Their words: …" / "I'll ask Casa Lucio to send you their own payment link, by text or email. You pay them directly — I never see your card…" / **"Ask Casa Lucio for the payment link?"** [Yes, ask them / No] | — | starts only after a call where the venue asks for a deposit (calls off). **(i)** the sentence said "for 2026-10-03" → `33709f7` |
| 6 | Gmail found-booking | **live, nothing to show** | "Check my email now": 0 new emails, nothing waiting (the 4 past finds were withdrawn by S-82's fix) | 54 s from this machine | needs one real upcoming booking email in his Gmail that he made himself (the demo plan's own condition) |
| 7 | Cancel | **live** | "Cancel the Retiro dinner." → "I can't find a booking called “Retiro dinner”." + a numbered list (status and reference on each) → "1" → "Cancel Sasha Test Venue, Saturday 3 October at 21:00, for 2, under TYLER WARREN?" → Yes → **"Sasha Test Venue has cancelled your booking."** · "Their words: “Reserva cancelada La reserva TV-95A2C2-A2 … queda cancelada. Gracias.”" | 10 s / 7 s / 6–9 s; calendar event removed 10 s later | Run 1 broke four times: **(j)** with cards on screen it searched "Cancel Retiro dinner dinner" → `e45a3b3`; **(k)** "I can't find an upcoming booking of yours at Retiro dinner" → `3ad5ab3`; **(l)** the list held today's 13:00 bookings and two identical lines → `352e857`; asking again over the old list got "Reply with the number" → `0e6ae3f`; **(m)** a redeploy emptied the test venue's book, so its cancel page said "No encontramos", and WhatsApp said "their words are below" with nothing below → `75c8771` |

**13 commits, all shipped through the full gate:**
`3207aee` (the rehearsal card), `5db01f1`, `64db27c`, `ff97b6c`, `93f7b3f`, `310abb4`, `e45a3b3`, `3ad5ab3`, `352e857`,
`0e6ae3f`, `75c8771`, `33709f7`, `7d292a2`.

**`7d292a2`: cancel wins over search.**
- The cards case was closed in `e45a3b3`. A named cancel still failed, because the name kept the meal and the day
  ("dinner Hanakura", "lunch Botavara tomorrow").
- Tests cover "cancel the X dinner", "my X booking", "the dinner at X" and the Spanish forms, each with and without cards
  on screen.
- **Simulated against his real bookings:**
  - "Cancel the Retiro dinner." with cards on screen → the cancel list, no search.
  - "cancel the dinner at Hanakura" → "Cancel Hanakura, Saturday 3 October at 21:00, for 2, under Tyler Warren?"
    (answered No).
  - "cancel my Calma booking" → "I can't reach them to cancel it right now: … phone calls are off." This is honest. Calma
    can only be cancelled by phone.

## Still reads wrong (not fixed tonight)

- **The read-back is long:**
  - the form's URL appears twice;
  - "Shall I send it?" sits right above the yes question.
- **The name is in capitals** ("under WARREN", "TYLER WARREN"): his saved contact is stored in capitals. Fix by
  re-saving the contact on the web page.
- **The header is clumsy:** "Special Dinner" (his "something special" plus "Dinner").
- **The demo account still holds bookings from earlier tests.** Not touched, because some are real:
  - Botavara, 3 Oct, unclear.
  - **Hanakura**, 3 Oct, requested. **It is a real venue.** The day-before "not confirmed" message would go out about it.
  - Two test-venue bookings, TV-62BB32 (3 Oct) and TV-592F2D (10 Oct).
  - **Calma**, 5 Oct, confirmed. **It is real.**
- **WhatsApp's 24-hour window:** his last real message was 19:38 Madrid. Sasha can write to him only until **3 Oct
  19:38**. On demo day he messages Sasha first.

## The confirmation rate, from the real calls (30 Sep – 2 Oct)

There were 7 booking calls placed:

| | count | share |
|---|---|---|
| Answered by a person | 4 | **57%** |
| Confirmed: an explicit yes to Sasha's closing recap | 1 | **14%** (25% of those answered) |
| Written confirmation that reached Sasha | 0 | **0%** |
| Not reached (2 voicemail, 1 no answer) | 3 | 43% |

- One written confirmation exists but **never reached Sasha**: Calma's text message to the guest, noted by the founder.
- There were also 2 cancellation calls. 1 was answered, and that one was confirmed ("Ok, está cancelado").
- **Sample: 7 calls.** That is not a rate to publish.

## Clean-up

- Run 2's booking was cancelled through the venue's own link.
- Run 1's booking (TV-FE41E1) uses the old reference format, so its link no longer knows it. That one row was set to
  cancelled.
- Both calendar events are gone; a check of Google's own records shows none left.
- The +34 bundle watch was restarted, once a day for 30 days. At 22:21 it was still `pending-review`.
