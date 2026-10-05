# CR 26 · Guestcentric, rebuilt from what the engine actually does — 5 Oct 2026

Everything was run read-only, in a Browserbase session (eu-central-1, unrecorded): nothing was booked, nothing was
typed into a guest form, and cookies were rejected. Screenshots are in this folder.

## Why the founder's link 6 didn't fill
It pointed at the hotel group's **marketing page** (`smallportuguesehotels.com/en/property-details/…`). That page has
no `apikey` and isn't the booking engine, so the parameters never reached it. The 2012 parameter names were right
all along.

## What the engine does (its own search, run in the page)
- **Robots first.** www.emporiumlisbonsuites.com robots: `Content-Signal: ai-input=no`, so **not used** (the hotel asks
  that its content not be fed to AI). The same property on its group's site (smallportuguesehotels.com, `ai-input=yes`)
  and on the group's booking domain (book.smallportuguesehotels.com, no robots.txt) was used instead.
- **The property page's own "Check Availability"** goes to
  `https://hypercommerce.guestcentric.net/?gc={apikey}&l=en&channelKey={key}&startDay=YYYY/MM/DD&nrNights=N`. Its
  "Our rooms" goes to `https://book.smallportuguesehotels.com/api/bg/book.php?apikey={apikey}&s=default&channelKey={key}&l=en`.
- **Picking 22–24 Nov in the engine's own calendar** changed its URL to `…&startDay=2026-11-22&nrNights=2` (ISO dates).
  Its "View Rates" went to `/search?gc=…&channelKey=…&startDay=2026-11-22&nrNights=2`.
- **Occupancy (3 adults) is never written to the URL**, but `nrAdults` IS read from it: `&nrAdults=3` opened as
  "1 Room, 3 Adults".
- **Both date formats are read:** `2026-11-22` and `2026/11/22` both selected 22–24 Nov.
- **The documented form on the venue's own booking domain**,
  `book.smallportuguesehotels.com/api/bg/book.php?apikey=…&startDay=2026-11-16&nrNights=2&amount=1&nrAdults=2&nrChildren=0`,
  redirects to `/search` with every parameter kept and opens on the rates. Mon 16 – Wed 18 Nov (2 nights), 1 Room,
  2 Adults, two rates with Select (`1-emporium-bookphp-filled.png`).
- **A second Guestcentric hotel, Memmo Alfama (Lisbon, memmohotels.com: `ai-input=yes`):** same HyperCommerce version,
  on its own domain `book.memmoalfama.com/?gc=…`. Its own room links use ISO `startDay`. The same `/search` link opens
  filled (`2-memmo-alfama-search-filled.png`).
- **Guestcentric's current help page** ("How to develop a custom hotel Booking Engine URL") matches: `startDay`
  yyyy-mm-dd, `nrNights`, `amount`, `nrAdults`, `nrChildren`.
- **Lisboa Carmo Hotel** (named by Guestcentric as a HyperCommerce hotel): its domain now serves an unrelated spam page.
  Not used.

## The rebuilt template (backend/booking_signer/engine_library.py)
- **Guestcentric links are built only from the hotel's own engine link.** Either `book.php?apikey=…`, kept (it
  redirects with every parameter), or the SPA's `?gc=…`, turned into `/search?gc=…`.
- **A marketing page carries nothing.** No dates get added to a page that ignores them.
- **Nights come from check-in/check-out** when only those are given.
- **The founder's ONE new link (verify-once.json, entry 6):**
  `https://book.smallportuguesehotels.com/api/bg/book.php?apikey=718b5ce5fcf26a16e6b8d80d90941bef&s=default&channelKey=39ed7b7b7dae559eb40276305db50f97&l=en&startDay=2026-11-16&nrNights=2&amount=1&nrAdults=2&nrChildren=0`.
  Expect: "Mon, Nov 16 – Wed, Nov 18 (2 Nights)", "1 Room, 2 Adults", rates with Select. This is exactly the link the
  rehearsal opened filled.

## Part (2) — Guestcentric through the live hand-over: what stands in the way
The checkout was read on Memmo Alfama, typing nothing, never pressing the last "Book Now":
**search → Select a rate → /extras (add-ons, "Book Now") → /guest**. Neither step held inventory: the only server call
on each was the page's chat widget (hovrapi), not Guestcentric's.
- **/guest asks for** first/last name, email, country code, phone, address, city, zip, motive (radio), check-in time,
  notes, an optional offers box, **"I accept the Terms and Conditions…" (a checkbox)** and **Book Now**
  (`3-memmo-guest-details-terms-box.png`).

Against the founder's absolute rules:
1. **The terms box is the guest's.** Sasha never ticks consent for anyone, and the hand-over refuses a page that needs
   one. A Guestcentric hand-over is therefore **2 taps** (☐ + Book Now), not 1, and it breaks "every field
   pre-filled, or we don't send that link". → **Founder decision.**
2. **The card step depends on each hotel's rate setup.** Guestcentric's docs show the hotel sets per rate whether a card
   is required ("Pay at the hotel" by default; "100% at time of booking"; "Non refundable"). Emporium's non-refundable
   rate says "Pay now". A card page after Book Now would open **inside our cloud browser**, which the founder's rule
   forbids. A hand-over could only be offered for a rate whose own terms say pay-at-hotel with no card, and that can
   only be confirmed by a booking reaching that page (not done here).
3. **Rate choice** (refundable or not, add-ons) is the guest's. Sasha can carry it only if the guest named it.
4. **Real guests** wait for the DPA in any case.

What is safe now, and built: the **prefilled link**. The guest lands on the hotel's rates for their dates and party,
then picks the rate, gives their details, ticks the terms and pays on the hotel's own page in their own browser
(estimate ~11 taps).
