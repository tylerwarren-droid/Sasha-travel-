# CR 25 · The hand-over page, demo-ready — 5 Oct 2026

The guest's page: `/api/booking/handover/{id}?t=…` (backend/booking_signer/handover.py). It's in Kanoe's colours: ink
#0a0a0f, cream #f0ede8, gold #DAA520/#E8B923, Inter, with green only for the press and the ✅. Screens:
`1-phone-open-instantly.jpg`, `2-phone-live.jpg`, `3-booked.jpg` (390-px phone, 366×561 frame).

| Asked | Built |
|---|---|
| Kanoe/Sasha branding | "kanoe · Sasha" bar with a green "live" dot; dark card; gold venue name |
| Venue, date, time, party, name on top | "Everything's filled in at **Sasha Test Venue** — Just press **"Reservar"** below." + chips "Tue 15 Dec · 21:00", "2 people", "Prueba Sasha" (from the reservation Sasha filled from) |
| Live view sized to the phone, button visible without scrolling | on open the page measures its frame and calls `GET …/fit?w&h` (token-keyed). The cloud browser takes **exactly** that size, so the live view is 1:1, not shrunk, and the venue's button is centred in it |
| A clear prompt toward their button | inside the venue's page (our cloud copy only): the button outlined in pulsing green, and a "↑ Press here" pill **below** it, so it never covers a field (above it only when there's no room). It ignores taps; they reach the button |
| ✅ Booked in Kanoe style, ref, Back to Sasha | green tick, "Booked", venue, "Tue 15 Dec · 21:00 · 2 people", the ref in gold mono, "Their own page confirms it.", gold "Back to Sasha" (the return address: kanoe.ai / wa.me only). The tick animates only in a visible tab |
| "Open it full screen" as a small fallback | a small link in the footer: "Their own website, live · nothing is sent until you press · Open it full screen" |
| Calm message when expired | "This link has expired — Nothing was sent to {venue}. Ask Sasha and she'll fill it in again in a few seconds." An unknown/ended link: "This link isn't active any more. Nothing was sent. Ask Sasha for a fresh one." Not-confirmed: "Sent to {venue} — it's a request until they do." |

**Found and fixed while rehearsing:**
- **Browserbase's viewer paints about 10 s after it loads.** That left a white box. Now the fit also returns a snapshot of
  the filled form, identical and 1:1, shown in the frame's place with "Connecting live…". Taps pass through to the live
  view. It stays until the guest's tap reaches the live view, or 20 s. A timer guess (4.5 s) showed white, so it's gone.
- **The ✅ froze on its first frame in a background tab.** It now animates only when visible, and the tick is drawn
  without the animation.
- **"Press here" covered the Name field at first;** it's now below the button.
- **A deploy ended a hand-over.** It was mine (d6c7214 deployed after I'd opened one). The "not active" screen showed
  correctly. Rule kept since: deploy only after checking `/ops/handovers` shows none live, and wait for SUCCESS before
  opening one.

**Rehearsal (Railway, test venue, fictional guest, phone size):**
- Link ready **2.5–2.9 s**; fit + snapshot **~0.2 s**.
- **Press → ✅: 0.09–0.10 s, 1 tap** (TV-EAD3F4-F1, TV-C99784-BD, TV-ED43D8-55, each cancelled with its own link).
- The press was made from the operator's live view: automated clicks can't reach the embedded one. The founder's real
  tap in the embedded view worked (TV-4BD724-23).

**Not changed:** real guests are still refused until the DPA is signed.
