# Sasha 138: the hotel booking ladder

*4 Oct 2026. Commits 82eef18, 3f22a16, ad0b487. 980 tests OK. (Sasha 137 was the CR 13 web wording fixes; this ladder
had not been built until now.)*

## 1. The ladder (WhatsApp: pick a hotel → "Book with hotel"; "Test booking" is kept alongside)

| The hotel | What Sasha does |
|---|---|
| **Its own booking engine is linked from its own site** | **One tap on the guest's phone.** The engine's page, with the dates added where the engine's usual URL takes them (said to be unverified); the guest pays there with Apple Pay or a card. Sasha never sees the card, and files the confirmation from Gmail. |
| Its engine is only a **widget** on its own site | One tap to the **hotel's own page** that carries it ("booking through Mews on their own site"). Nothing is added to its URL. |
| No engine | A **room request by email** ("Room request — 2, 2026-10-20 for 2 nights", English or Spanish). |
| No reply in 24 h | **A call**, covered by the first yes (the plan is in its read-back). The call says the stay: "una habitación para 2 noches (salida el …)". |
| Arriving within 24 h | **Call + email at once**, on one yes. |

**Engines recognised** (from the hotel's own site; their pages are **never fetched**, under the platform rule):
- SiteMinder, Little Hotelier, Cloudbeds, Mews, SynXis, D-Edge, Roiback;
- Neobookings, Bookassist, GuestCentric, Omnibees, Simple Booking, WebHotelier, iHotelier, Hotetec.

**Dates in the link:**
- **Added for** SynXis, Cloudbeds, Mews, SiteMinder and Little Hotelier, using each engine's usual URL parameters.
- **Not verified:** no built link has been opened here. The read-back says "check them on their page before you pay",
  never "filled in".
- **Other engines:** the page opens without dates, and the read-back lists the dates to choose.

## 2. The read-only rehearsal

Real hotels (Google), each hotel's own site read, the link and read-back built, stopped before the payment step.
Transcript: `docs/business/demo-v6-hotel-ladder/read-only-rehearsal.txt`.

| Hotel | Engine | One-tap page (built, **not opened**) |
|---|---|---|
| **UMusic Hotel Madrid** | Neobookings (on their own site) | their hotel page (tracking dropped); dates listed to choose |
| **The Hat Madrid** | Mews (widget on their own site) | thehatmadrid.com/contacto/; dates listed to choose |
| **The Signature Hoi An** | **D-Edge**, a real booking URL (secure-hotel-booking.com/d-edge/The-Signature-Hoi-An/…) | that page; dates listed to choose (D-Edge has no known URL parameters) |

- **Engines seen across 28 hotels:** D-Edge ×4, Mews ×1, Neobookings ×1. None of the 28 used SiteMinder, Cloudbeds,
  SynXis, Roiback or Little Hotelier.
- **The rest:** most had email and/or phone only, and would go to the email room request (then the call).

## 3. Found by the rehearsal, fixed

1. **Three Hoi An hotels' only "D-Edge link" was the vendor's homepage** (a "powered by D-Edge" footer). One tap would
   have sent the guest to d-edge.com. A vendor homepage is now never a booking page.
2. **Widgets** (Mews, Neobookings) now use the hotel's own page, and Google's tracking parameters are dropped from it.
3. The read-back used the **web page's title** ("Contacto UMusic Hotels") instead of the hotel's name; it now uses the
   name.
4. **The date rolled to 4 Oct, and 4 tests broke on a real-clock weekday parse.**
   - Mine: WhatsApp parsed "Saturday" on the real clock, but measured urgency on the turn's clock. It now uses one
     clock.
   - CR fixed its campus tests (8cdc87d).

## 4. For the founder

- **To make the dates verified:** open one built link per engine (SynXis, Cloudbeds, Mews, SiteMinder) and say whether
  the dates show filled. Each one you confirm becomes a verified recipe, and the read-back can then say "filled in".
- **Instant hotel booking via an API** still waits for Duffel Stays or RateHawk credentials.
