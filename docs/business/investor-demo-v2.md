# Sasha — investor demo v2 (screen + phone)

*Sasha 121, 3 Oct 2026. For the meeting within six days. Rehearsed twice end to end on the founder's account on
3 Oct (timings below).*

**The rule from v1 still holds:** nothing is shown as live that isn't, and nothing is shown that isn't built. Our test
venue and Kanoe Demo Market are **ours**, and say so on screen.

---

## v3 · Vietnam → "and Madrid next week" (Sasha 126, 3 Oct)

The storyline for Wednesday. It sits **before** beats A–G (§1), which stay as the Madrid follow-on if there is time.

### v3.0 Extra setup the night before

- **You → My accounts:** save the **Kanoe Demo Spa** membership.
  - Get it from the ops page (*Spa · Demo spa membership*) or `demo.py spa-login`.
  - Site "Kanoe Demo Spa", kind "Password".
  - `demo.py status` now reports both saved logins.
- **Changed from the brief:** the storyline said "use my **Calma** membership". Calma Madrid is a real spa, and a portal
  in its name would impersonate it. The member portal is therefore **Kanoe Demo Spa**: ours, labelled as ours, it charges
  nothing. The real Calma is asked separately (§v3.4).

### v3.1 Run of show (phone, WhatsApp)

Timings are the wait after each message, from rehearsal 1 · rehearsal 2 (both 3 Oct).

| # | Say / tap | What appears | R1 · R2 (s) |
|---|---|---|---|
| V1 | "dinner for 2 in Hoi An, Vietnam tomorrow at 7pm" | Cards: Red Bean Hoi An · Nhan's kitchen · test venue (rehearsal card) | 9.0 · 5.2 |
| V2 | "dinner for 2 in Hanoi, Vietnam tomorrow at 7pm" | Cards: L'essence de Cuisine · Hoang's · test venue | 9.8 · 9.4 |
| V3 | Tap **Sasha Test Venue** → **Yes, book it** | Read-back of the form → "✅ Booked … Their reference: TV-…" | 8.6 + 8.5 · 8.9 + 8.7 |
| M1 | "Book a restaurant and a spa in Madrid when I arrive next week" | "Which day, and what time for each?" | 1.9 · 2.0 |
| M2 | "Tuesday — spa at 18:00, dinner at 21:00" | Restaurant cards with photos (D-Sunset · Los Montes de Galicia · test venue) | 5.2 · 4.7 |
| M3 | Tap **Sasha Test Venue** | The form is prepared and held, then spa cards (Bruma Head Spa · Wellness Boutique · **Kanoe Demo Spa**) | 25.8 · 14.3 |
| M4 | Tap **Kanoe Demo Spa** | **One** read-back of both, including "I'll sign in to Kanoe Demo Spa with your saved … membership", then **one** sentence: "Book both? …" | 1.8 · 1.9 |
| M5 | **Yes, book both** | "✅ 1) Booked: Sasha Test Venue … TV-…" and "✅ 2) Booked: a 60-minute relaxing massage at Kanoe Demo Spa … Ref KDS-… I used your saved membership once" | 11.3 · 11.8 |
| M6 | Laptop: Google Calendar | Two events on "Sasha bookings" | ≤ 29 · ≤ 12 |
| M7 | Laptop: **/vault** | One use of the spa login listed → **Revoke** (one tap) | — |

- **Two receipts:** both are sent by email. In rehearsal they were captured, not sent.
- **One sentence still works on its own:** "use my spa membership to book a massage on Tuesday at 18:00" gives the same
  read-back, yes and booking for the spa alone.
- **Combining only works with our spa today:** a real spa card can't be booked together with the restaurant. Sasha says
  so and sends nothing.
- **After the demo:** *Reset the demo* now also cancels the Kanoe Demo Spa bookings and their calendar events.

### v3.2 Vietnam: what truthfully works today

| | Works? | Detail |
|---|---|---|
| Discovery cards (Hoi An, Hanoi) | **Yes** | From Google Maps, ranked. 19–20 of 20 were open at 19:00. |
| Photos on those cards | **Partly** | A photo is the venue's own share image from its own site. **About 1 in 3** of the top Vietnamese venues publish one (e.g. MẸT, The Soul, MIAs, VIET Restaurant). The first two cards in rehearsal had none, so they show as text. Madrid's cards had photos. |
| Booking by the venue's own form | **Via the test venue only** | The forms found at real VN venues aren't mapped or approved. Our test venue stood in, and the booking was confirmed. |
| Booking by email, in English | **Built, not sent** | The email rung is available at, for example, Mate (contact@materes.com), L'essence de Cuisine and MIAs. There is no Vietnamese template, so it writes in English (below). It was not sent to any venue: none has agreed. |
| An English **call** to Vietnam | **No, not today** | See below. |

**The English email Sasha would send to Mate** (composed in rehearsal, not sent):
> Hello, this is Sasha, an AI concierge operated by Kanoe Technologies SL, writing on behalf of the Warren family to ask
> for a table for 2 on 2026-10-04 at 19:00. Could you reply to this email to confirm, or to tell us if that isn't
> possible? …

**Why an English call to Vietnam is not feasible on Wednesday:**
1. **Code:** Vietnam is mapped to Vietnamese ('vi'), and the call engine has no 'vi' and no "call in English abroad"
   option. It refuses rather than guess. This is a small change, but it is untested.
2. **Time zone:** Vietnam is UTC+7, Madrid + 5 h. Most restaurants open about 10:00–22:00 local, which is 05:00–17:00 in
   Madrid. A morning demo works; an evening one reaches closed venues.
3. **Language at the venue:** English is likely at tourist-area restaurants in Hoi An and Hanoi, but nothing we read
   confirms it.
4. **Calling +84:** international dialling through Bland is untested, and its cost is unknown.

**Verdict:** say "in Vietnam Sasha books by the venue's form or email today"; calls there come later.

### v3.3 Bugs the rehearsals found, fixed the same morning

| Found | Fix |
|---|---|
| R1: the two-booking plan was lost between messages, because the live store keeps only four columns | The plan now travels inside the open question. The test store now behaves like production. |
| R1: "in Hoi An, Vietnam" searched for "Vietnam dinner" | A country named after the place is the country. |
| R2: Hanoi, said while Hoi An's cards were open, searched for "Hanoi Vietnam tomorrow at dinner" | A whole new request names its own kind. |

Rehearsal 2 was re-run clean after the last fix; its timings are in v3.1. Commits: c43b1b9, 11237f8, d81573c, eb19fc9.

### v3.4 The friendly spa: a Spanish request to Calma Madrid

**Calma Madrid Masajes** ("SPA Calma"), C. de Domenico Scarlatti 5, Chamberí. Read on 3 Oct:
- **Phones:** +34 91 989 19 16 and +34 660 39 09 10, both from their website (calmadrid.com).
- **No email and no booking form** on their homepage.

So the founder calls, or sends a WhatsApp to the mobile if it takes WhatsApp (not verified). He already has a booking
with them on 5 Oct, which is a natural moment to ask in person.

> Hola, soy Tyler Warren, fundador de Kanoe Technologies, en Madrid (y cliente vuestro). Hemos creado Sasha, una
> concierge de inteligencia artificial que reserva por teléfono y que siempre dice, en la primera frase, que es una IA.
>
> El [día] a las [hora] la presentamos a inversores y nos encantaría hacerlo con vosotros:
> - Sasha os llamaría al 91 989 19 16 para reservar un masaje relajante de 60 minutos a nombre de Warren.
> - La cancelaríamos enseguida, el mismo día.
> - La llamada se escucharía en directo en la sala, sin grabarla ni difundirla.
> - En pantalla solo aparecería vuestra ficha pública de Google Maps.
> - No usaríamos vuestro nombre para nada más.
> - Sin ningún coste para vosotros.
>
> ¿Nos dais permiso por escrito? Un "sí" por WhatsApp o por email basta.
>
> ¡Muchas gracias! Tyler Warren — Kanoe Technologies SL — +34 608 44 57 15

**Rules:**
- Calma's written yes must be in hand before calls are switched on.
- The vault beat stays on Kanoe Demo Spa either way: we have no access to any real member portal.

### v3.5 Fallback recordings

- **Phone beats:** these are WhatsApp, and I can't screen-record a phone from here. The fallback is the word-for-word
  transcript of each rehearsal, which can be read out or shown:
  - `docs/business/demo-v3-fallback/rehearsal-1-transcript.txt`
  - `docs/business/demo-v3-fallback/rehearsal-2-transcript.txt`
  - The founder's email and mobile are redacted in both.
- **Browser beats (Calendar, /vault):** not recorded. A GIF from the browser means a file download, and I didn't take
  one without asking. **Recommended:** the founder screen-records one run on his phone (iOS: Control Centre → Screen
  Recording) during the dress rehearsal the evening before. That also captures WhatsApp exactly as investors will see it.

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

**Their public routes, read from their own sites and listings on 3 Oct.** Both take bookings through a platform, so on
the laptop Sasha first offers the platform link. **For the live call, tap "or have Sasha call them instead".**

| Venue | Address | Write to | Phone (Sasha calls this one) | Books via |
|---|---|---|---|---|
| **Araia** | C/ de Murillo 3, Chamberí | **gestion@araia.es** (their website) | +34 610 869 537 (their Google listing) | Restoo |
| **Pilar Akaneya** | C. de Espronceda 33, Chamberí | No email, form or WhatsApp published (their group site, akaneyajapan.com) | **+34 913 307 699** (their website, Madrid) | CoverManager |

### 2.1 Araia: by email to gestion@araia.es

**Asunto:** Demostración con inversores: una reserva de prueba por teléfono (Kanoe / Sasha)

> Hola, equipo de Araia:
>
> Soy Tyler Warren, fundador de Kanoe Technologies, en Madrid. Hemos creado Sasha, una concierge de inteligencia
> artificial que reserva restaurantes por teléfono y que siempre dice, en la primera frase, que es una IA.
>
> El [día] a las [hora] presentamos Sasha a inversores y nos encantaría hacerlo con vosotros:
> - Sasha os llamaría al 610 869 537 para reservar una mesa para dos a nombre de Warren.
> - Poco después cancelaríamos la reserva por email, en el mismo momento.
> - La llamada se escucharía en directo en la sala. No se grabaría ni se difundiría.
> - Es una reserva de prueba, sin ningún coste para vosotros y sin ocupar una mesa real.
>
> ¿Nos dais permiso por escrito? Un "sí" en respuesta a este correo basta. Si preferís otra hora u otro número,
> decídnoslo.
>
> Muchas gracias,
> Tyler Warren — Kanoe Technologies SL — +34 608 44 57 15

### 2.2 Pilar Akaneya: by phone to +34 913 307 699

They publish no email or WhatsApp, so the founder calls, then asks for their yes in writing. If they give an email or
WhatsApp, he sends the text below there.

**Said on the phone:**

> Hola, soy Tyler Warren, de Kanoe Technologies. Hemos creado Sasha, una concierge de inteligencia artificial que reserva
> por teléfono y siempre dice que es una IA. El [día] la presentamos a inversores: ¿nos dejaríais hacer una reserva de
> prueba con vosotros? Sasha os llamaría a las [hora] para reservar una mesa para dos a nombre de Warren, y la
> cancelaríamos enseguida. La llamada se escucharía en directo en la sala, sin grabarla. ¿A qué email o WhatsApp os
> mando los detalles para que nos digáis que sí por escrito?

**Then sent, to the address they give:**

> Hola, soy Tyler Warren (Kanoe Technologies), como hablamos por teléfono:
> - El [día] a las [hora], Sasha, nuestra concierge de IA, os llamaría al 913 307 699 para reservar una mesa para dos
>   a nombre de Warren.
> - La cancelaríamos enseguida.
> - La llamada se escucharía en directo ante inversores, sin grabarla ni difundirla.
> - Sin ningún coste para vosotros.
>
> ¿Nos confirmáis por escrito que estáis de acuerdo? Un "sí" basta.
>
> ¡Gracias! Tyler — +34 608 44 57 15

**Rules:**
- Their written yes must be in hand before calls are switched on.
- **No recording is played.**
- The demo booking is cancelled the same day.
- **Rehearse beat A against their real cards the evening before:** the first two cards change with the day and the
  hour.

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
