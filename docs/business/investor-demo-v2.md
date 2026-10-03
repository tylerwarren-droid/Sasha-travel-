# Sasha — investor demo v2 (screen + phone)

*Sasha 121, 3 Oct 2026. For the meeting within six days. Rehearsed twice end to end on the founder's account on
3 Oct (timings below).*

**The rule from v1 still holds:** nothing is shown as live that isn't, and nothing is shown that isn't built. Our test
venue and Kanoe Demo Market are **ours**, and say so on screen.

---

## 0. The night before (founder)

1. **WhatsApp sandbox:** re-join it (the join expires after 3 days). Then **message Sasha once the morning of the
   demo**, because WhatsApp only lets Sasha write within 24 hours of your last message.
2. **Google:** Calendar and Gmail were connected on 2 Oct, and testing mode expires them after 7 days (≈ 9 Oct).
   **Reconnect both in You the day before.**
3. **You → WhatsApp → My starting point:** save one, e.g. the meeting's address. Beat E needs it, because Sasha never
   guesses a travel time.
4. **You → My accounts:** save the Kanoe Demo Market login.
   - Get it from the ops page (`/booking-helper` → *Investor demo* → *F · Demo shop login*).
   - Site "Kanoe Demo Market", kind "Password".
5. **The friendly venue (§2):** written consent in hand. Then switch calls on (`SASHA_CALLS_ENABLED=1` on Railway) for
   the demo window only.
6. **Reset and check:** on the ops page press *Reset the demo*, or run
   `railway run -- python backend/scripts/demo.py reset`, then `… demo.py status`. Status must say:
   - WhatsApp linked, Calendar connected, Gmail connected;
   - a starting point saved;
   - the Kanoe Demo Market login saved;
   - calls ON (only if the friendly venue agreed).
7. **Rehearsal card:** `SASHA_REHEARSAL=1` is set on Railway. It adds our test venue as the third card, on your
   account only, labelled "ours, not a real restaurant".

**Devices**
- **Laptop:** project.kanoe.ai (chat, then You), with Google Calendar open in a second tab, and ops in a third.
- **Phone:** WhatsApp, mirrored to the screen.
- **An investor's phone:** for beat D.

---

## 1. Run of show

The timings are from the two rehearsals on 3 Oct (each beat's wait, measured in seconds).

| # | Beat | Device | What you say / tap | What appears | Rehearsal 1 · 2 | Fallback |
|---|---|---|---|---|---|---|
| A | **Book by voice** | Laptop | 🎤 "Luxury dinner for two in Chamberí tonight at nine" | Cards (today): **Araia** · **Pilar Akaneya** · the friendly venue (or "Sasha Test Venue — ours, rehearsal"). Pick → read-back of exactly what she'll say (or send) → **one sentence** → **Yes** | 14.6 · 13.9 | Calls off or no answer within 60 s: the **test-venue card** → "✅ … Reserva confirmada … TV-…" |
| A | → the call (friendly venue) | Laptop speaker | — | "Hola, soy Sasha, una concierge de inteligencia artificial…" (the AI disclosure first) → the recap → "¿Correcto?" → their yes | not rehearsed (calls off) | Say: "real venues don't always pick up — that's the point of the ladder"; use the test venue |
| A | → receipt + calendar | Laptop | — | The result in the chat, the receipt email, and the event on **"Sasha bookings"** in Google Calendar | event after 17.6 · 11.8 | Skip the calendar if Google has expired (reconnect the night before) |
| B | **Cancel** | Phone | "Cancel tonight's dinner" → **Yes, cancel** | "Cancel …, Saturday … at 21:00, for 2, under Tyler Warren?" → "Sasha Test Venue has cancelled your booking." + **their words** ("Reserva cancelada … queda cancelada. Gracias.") | 9.1 + 7.7 · 8.7 + 7.0 | Several tonight → a numbered list; reply with its number (+4 s) |
| B | → the event disappears | Laptop (Calendar) | — | The event is gone | 23.1 · 23.2 | Refresh the Calendar tab |
| C | **Change of plan** | Phone | "Find us Japanese for two in Salamanca at 21:30 instead" | Cards with **photos** from each venue's own site: Ichikani · Akiro Hand Roll Bar · test venue → tap → read-back → **Yes, book it** → "✅ Booked … Their reference …" | 5.3 + 8.8 + 8.6 · 5.3 + 8.9 + 8.3 | — |
| C | → "You" updates | Laptop (/you) | — | **My bookings** shows it (it refreshes every 8 s) | ≤ 8 | Reload /you |
| D | **The investor picks** | Phone, then the investor's phone | "Book dinner with Ana this week near Retiro" → send the link to the investor | Their page shows only your first name, "dinner" and the times → they tap one → your phone: "Ana picked … The booking is yours…" + cards → tap → **Yes** → booked | 10.1 + 8.9 + 17.5 · 9.4 + 10.2 + 17.5 | Late in the week, "this week" may leave 1–2 times; say "next week" |
| E | **"Time to leave"** | Phone | Ops: *E · Send "time to leave" now* | "(Demo — sent early.) When it's time, this is what arrives: Time to leave for …: 22 min by public transport from …, for 21:00." The time is real (Routes API) | 9.4 · 9.4 | No starting point saved → it refuses rather than guess |
| F | **The vault** | Phone, then laptop | "Reorder my usual from Kanoe Demo Market" → **Yes, order it** | The read-back names **the saved login** and the basket (2 × Café de Colombia, 1 × Pan de masa madre, 1 × Aceite de oliva — **€27,40**; "nothing is paid") → "✅ Ordered … KDM-… I used your saved login once, for this order — it's in your vault's log." → laptop **/vault**: the use listed → **Revoke** (one tap) | 1.8 + 3.1 · 2.0 + 3.4 | A wrong or missing login → "❌ Not ordered", nothing placed |
| G | **Gmail** | Phone | Ops: *G · Gmail find* — press it **one minute before** this beat | "Your inbox has a booking at Sasha Test Venue, Friday 9 October 21:00 for 2. Add it to your itinerary?" → **Yes** | 61.5 · 62.0 | A real booking you made yourself works the same: You → Gmail → *Check my email now* |

**After the demo:** press *Reset the demo*. It cancels every test-venue booking (their calendar events go within a
minute), withdraws the Gmail finds and closes any open WhatsApp question; real bookings are untouched. Then cancel the
friendly venue's booking, if one was made, the same day.

---

## 2. The friendly venue (beat A, live call)

For "luxury dinner for two in Chamberí tonight at nine", the cards on 3 Oct were **Araia** (4.8★) and **Pilar
Akaneya** (4.8★), so a friendly venue among them needs no change to the line. Three proposals:

1. **Araia** (Chamberí): the first card.
2. **Pilar Akaneya** (Chamberí): the second card.
3. **Smithers Restaurant** (S-50 list): publishes phone, WhatsApp and email. The line then names it: "dinner for two at
   Smithers tonight at nine".

**The request (Spanish, from the founder):**

> Hola, soy Tyler Warren, fundador de Kanoe Technologies, en Madrid. Hemos creado Sasha, una concierge de inteligencia
> artificial que reserva por teléfono y siempre dice que es una IA. El [día] la presentamos a inversores y nos gustaría
> hacer una demostración en directo con vosotros: hacia las [hora], Sasha os llamaría para reservar una mesa para dos a
> nombre de Warren, y poco después la cancelaríamos. La llamada se escucharía en directo en la sala; no se grabaría ni se
> difundiría. Sería una reserva de prueba, cancelada en el momento y sin ningún coste para vosotros. ¿Nos dais vuestro
> permiso por escrito (un sí a este mensaje basta)? Muchas gracias. Tyler — +34 608 44 57 15

**Rules:**
- Their written yes must be in hand before calls are switched on.
- **No recording is played.**
- The demo booking is cancelled the same day.

---

## 3. What is NOT live, and is said so on stage

- **WhatsApp:** Twilio's sandbox (it shows the sandbox number), until Meta verifies Kanoe.
- **Voice (beat A):** the laptop's microphone transcribes it; this was not part of the rehearsal. Test it on the
  laptop the night before. Typing the same sentence works the same.
- **Calls:** off on the server except during the demo window. A guest's calls are off until the founder switches them
  on per account.
- **Gmail:** a beta by invitation (Google testing mode).
- **Our test venue and Kanoe Demo Market** are ours: they book, sell and charge nothing, and say so.
- **Confirmation rate:** 1 of 7 real booking calls was confirmed against the recap. Re-read under 3 Oct's rule it would
  be 2 of 7. **It is too small a sample to publish.**

---

## 4. Controls

| How | What |
|---|---|
| Ops page → *Investor demo* | Reset · E "time to leave" now · G Gmail find · F the demo shop's login |
| `railway run -- python backend/scripts/demo.py reset \| status \| leave-now \| gmail \| shop-login` | The same, from the command line |

---

## 5. The rehearsals (3 Oct)

**How they were run**
- On the founder's account, in-process.
- **WhatsApp was captured**: nothing reached his phone. Receipt emails were captured too.
- **Real:** Google Places; the test venue's form; the Google Calendar mirror; the Routes API; the demo shop over
  HTTPS; one email from our test venue into his Gmail per rehearsal (beat G).
- **Stood in:**
  - calls were off, so the test venue stood in for the friendly venue;
  - E used a stand-in starting point (none was saved);
  - F used a vault in the process's memory against the live shop (the login wasn't saved yet).

**What the rehearsals broke, fixed the same morning**

| Beat | What broke | Fix |
|---|---|---|
| B | "cancel tonight's dinner" read as a booking called "'s" | The day is now a filter on the bookings |
| C | After a pick, "Japanese" asked "What should I book there?" | A cuisine now means a table |
| G | The reset deleted Gmail finds, so the old seed email was offered again | Finds are withdrawn, not deleted |

**Known rough edge:** the form read-back is long, and it quotes the form's address twice.
