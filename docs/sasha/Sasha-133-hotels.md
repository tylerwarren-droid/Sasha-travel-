# Sasha 133: could Sasha ever reserve hotel rooms?

*3 Oct 2026. I searched the whole repo and its git history (`git log -S/-G` and deleted files) for: hotel, stays, Duffel,
RateHawk/worldota, HotelsPro, Travolutionary, Amadeus, Hotelbeds, Booking.com, Expedia, room, reserve, prebook, finish.*

## Answer: no. Sasha never reserved a hotel room with any provider.

What the founder saw, and why it looked real: the **web chat's "Reserve · $X" button** on a hotel card. It called
`/api/payments/reserve`, which only writes a row in Sasha's own database and makes up a `resv-` reference. **No hotel
and no provider was ever contacted.** The page then said **"Stay reserved! … Your reservation is confirmed."**

That was a false success state (client feedback of 11 Aug: "Sasha simply takes the reservation"). **Fixed today** (§3).

## 1. Timeline

| When | Commit | What |
|---|---|---|
| 15 May 2026 | `90ba4e0` | Hotel cards and the HotelResults component (display only) |
| 16 May 2026 | `a12a6e1` | `backend/app/services/ratehawk.py`, `api/search.py` and `api/bookings.py` appear (from former submodules) |
| 28 May 2026 | `3177210` | Last change to `ratehawk.py` (residency/currency GB→US) |
| 12–13 Jun 2026 | docs | `hotels_agent — RateHawk` listed under "Next agents to build (**post-API approval**)" |
| 29 Jul 2026 | `8338744` | "RateHawk hotel cards" in the message only. The cards come from `hotels_db.py`, a curated list. |
| 11 Aug 2026 | `payments.py` /reserve | "Reservation-only booking — no payment": a row and a minted reference, nobody contacted |
| 3 Oct 2026 | `5936ca2` | Duffel Stays: **403 "not enabled for your account"**. RateHawk: **no credentials**. Hotels → requested from the hotel itself. |

## 2. The only hotel-booking code: RateHawk (ETG / worldota), never switched on

- **Where:** `backend/app/services/ratehawk.py`. The API base defaults to the **sandbox**,
  `https://api-sandbox.worldota.net`.
- **Credentials:** Basic auth from `RATEHAWK_KEY_ID` + `RATEHAWK_API_KEY`. **Neither has ever been set.**
- **What it has:**
  - search;
  - a rate check (`/api/b2b/v3/search/check/` — not sure this path exists in ETG v3; their prebook is normally
    `/hotel/prebook/`);
  - `create_booking` → `/order/booking/form/`;
  - booking info and cancel.
- **⚠ It never had `/order/booking/finish/`.** In ETG's flow, `form` only starts an order and `finish` completes it.
  **Even with credentials, this code could not have finished a reservation.**
- **Callers:** only `api/conversation.py`, which catches the failure as "RateHawk API error (expected without
  credentials)".
- **Evidence of a completed reservation:** **none.** No order id or booking id appears in tests, logs or docs.
- **Other providers** (HotelsPro, Travolutionary, Amadeus, Hotelbeds, Expedia): **never in the code.** Expedia env names
  appear in one handoff doc only.

## 3. Fixed today: the web no longer claims a reservation that didn't happen

| Before | Now |
|---|---|
| "Stay reserved!" / "Your reservation is confirmed." / "Reservation · resv-…" | "Stay saved to your trip" / "Not booked: no hotel, airline or venue has been contacted. Ask Sasha to book it, and she will tell you how." / "Saved · …" |
| "Trip reserved! Your reservation is confirmed" | "Trip saved — not booked: no hotel, airline or venue has been contacted…" |
| Trip tab "✓ Reserved" | "✓ Saved · not booked yet" |
| (with payments on) "Booking confirmed and paid" | "Payment received, but nobody has been contacted to book it yet" |

## 4. To make "reserve a hotel room" real, the founder requests ONE of these

1. **RateHawk / Emerging Travel Group (ETG) B2B API.** Ask ETG's partner team for **sandbox API credentials** (a key id
   and an API key). Set `RATEHAWK_KEY_ID` and `RATEHAWK_API_KEY` yourself.
   - Before it works, I'd add: prebook, then `/order/booking/form/` → `/order/booking/finish/` → status polling. Then
     wire "Book it (TEST)" to it, as for flights.
   - Live use later needs production credentials and the production URL.
2. **Duffel Stays.** Ask Duffel sales to **enable Stays on the existing account** (today: 403 "not enabled for your
   account"). The Duffel TEST token we already use would then cover hotels too. That is the shortest path: the same
   provider and flow as flights.

**Until one of them answers,** the honest fallback stays: hotels are found as cards, and the room is requested from
the hotel itself by its form or email (English, or Spanish in Spain).
