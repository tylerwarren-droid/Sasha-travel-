# CR 27 · The Guestcentric hand-over — two taps, built and rehearsed READ-ONLY (5 Oct 2026)

The founder's YES: every information field pre-filled; the "I accept the Terms" box left for the guest (☐ + Book Now);
only pay-at-hotel rates whose own terms show no card; stop before any card page; the rate stays the guest's choice.

## Built — `backend/booking_signer/handover_guestcentric.py` (+ the shared hand-over page)
- `POST /api/booking/handover/guestcentric/rates` (keyed): every (rate, room) for the stay with its price and
  cancellation, its OWN terms (the rate's "View details"), and **eligible / why**. No guest data is involved.
- `POST /api/booking/handover/guestcentric` (keyed): the guest's (rate, room) and details → ONE link, `taps_left: 2`.
- `POST /api/booking/ops/handovers/rehearse-guestcentric` (founder only): always READ-ONLY, with a fictional guest.

| Rule | Enforced by |
|---|---|
| Every information field pre-filled | missing name, email, phone, country, address, city or zip → refused **before any session** ("Sasha needs these first"). On the page: Country (its own list), First/Last name, Email, Country code, Phone, Address, City, Zip, Motive (the guest's, or "Leisure"), Notes. A custom question the hotel adds (e.g. "Check-in Time") is filled only from the guest's answer, otherwise no link. Each value read back, then any visible empty information field → no link |
| Terms box left for the guest | never ticked; the offers box never ticked; any other box → no link. The page says "Tick 'I accept the Terms', then press 'Book Now'"; the cloud page outlines both, "① Tick the box above" (below the terms row, away from the offers box) and "② Then press Book Now" |
| Only pay-at-hotel, no card | the rate's own terms must say pay at the hotel ("Pay at the hotel", "pago en el hotel"…) and mention no card, guarantee, prepayment, deposit or non-refundable. Silence = not eligible |
| Never a card page in our browser | card fields or payment frames on the details page → refused. Payment providers' hosts are **blocked** in the cloud browser, so a card form can't load there. If a card page still appears after Book Now, the session ends at once and the guest sees "The hotel asked for a card — finish on their own page" with the prefilled link |
| The rate is the guest's | exactly the named (rate, room), found by the card's own H2/H3. Then the hotel's own **Reservation Summary** must name it, or no link |
| Hotel's own engine, real guests | built only from the hotel's book.php?apikey / ?gc= link (engine_library); robots first; real guests still wait for the DPA |

## Rehearsed READ-ONLY (fictional guest; every outgoing write aborted in the cloud browser; Book Now never pressed)
- **Emporium Lisbon Suites, 16–18 Nov, 2 adults:**
  - Rates: Non-Refundable €280 → refused ("its terms mention Non-Refundable"); **Standard Rate €400 → eligible** ("Pay at the hotel.", no card).
  - Hand-over (`1-emporium-filled-two-taps.png`): the hotel's summary "Family Suite City View · Standard Rate · 2 Persons · €416.00"; every field filled (Spain, Prueba Sasha, prueba@example.com, +34 600000000, Calle de Ejemplo 12, Madrid 28013, Leisure, notes); the terms box and Book Now outlined; offers box unticked.
  - **From Railway (EU): link ready in 8.4–8.5 s** (page 3.3 · rate 1.5 · summary check 0.8 · country 0.4 · live view 1.0). Locally it was 27–45 s; fixed waits were replaced by "until it appears".
  - Phone (390-px, frame 366×466): both taps visible without scrolling (`2-phone-guest-page.jpg`), "Rehearsal: the last press is blocked".
- **Memmo Alfama, same dates:** six (rate, room) pairs, **none eligible**. Their terms say "Fully refundable" but not where you pay, so silence means no. Memmo stays on the prefilled link.

## Caught while rehearsing (each fixed, each now a test)
1. **The wrong rate.** My first matcher took the first Select under a container holding both rates. The hotel's summary
   then read "Non-Refundable Rate — To be paid €296.00" (`x-caught-wrong-rate-non-refundable.png`). Now: the card's
   own H2/H3, plus the Reservation Summary check (no link on mismatch).
2. **"tion" as a booking reference** ("reserva" inside "reservation"). References now need whole words and a digit.
3. **On Railway the summary drew after the form**, so the check refused. It now waits for it, up to ~5 s, and says what
   it saw.
4. **Sized to the phone, the terms box scrolled away.** The resize now re-points both taps.
5. **The "①" label sat over the offers box.** It's now below the terms row.

## Founder's answer on link 6
Not received at the time of writing. The Sasha tab has a watcher on and will forward his exact words; engine_library
records it then.
