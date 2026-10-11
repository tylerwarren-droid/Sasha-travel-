# Sasha 235 — report (11 Oct 2026)

## Live
- Backend **662e696** · Railway 521dae74 SUCCESS · frontend a5b3b87 Vercel **READY** (sasha-travel-hdyp)
- Commits:
  - 8014224: merge CR 79 (cr/79-s2 @ f9c78ce)
  - a5b3b87: My Keep, loyalty applied, upgrade my room, hours check
  - 8301d96, fcae6df, fd6811f, 662e696: four fixes, each found live (see below)
- Units 1943 OK (146 skipped, 1 expected failure) · `npx next build` OK · eslint clean on the 3 changed frontend files
- **S1 fingerprint: byte-identical to 228's baseline** after every commit (system 4e2560d4bdfd, tools 5334edda76ee, 24 tools).
  No S1 change was needed:
  - My Keep on S1 is the existing /keep page, now with the shared screen and uses.
  - S1's loyalty runs in booking code, not in the prompt or tools.
  - `hotel_request` is /s2-only (MANAGE_TOOLS + S2_TOOLS, not v0.TOOLS).

## Gate (service key `sk-ant-… bc1e05b8d099` — SASHA_GATE_ANTHROPIC_API_KEY still unset)
| deploy | commit | suites | $ |
|---|---|---|---|
| c35515e8 | a5b3b87 | 149/149 (demo safety 338) | $1.06 / 241 calls |
| af214f78 | 8301d96 | 149/149 | $1.04 / 243 |
| d3a8ae8b | fcae6df | 149/149 (demo safety 339) | $0.94 / 245 |
| 6094675d | fd6811f | 149/149 | $1.02 / 235 |
| 521dae74 | 662e696 | 149/149 | $1.05 / 244 |

## 1 · Arrival cards (CR 79), on production /s2 → agapi-sandbox
Setup: a scratch guest, with a FICTIONAL specimen passport (Passport ES ••••456) in Sasha's Keep and the sandbox's.
- **"Spanish passport, Madrid → London 2 Nov, Madrid → Bangkok landing 20 Nov. What do I need?"**
  - UK: an ETA, GBP 20 on the official site, decisions up to 3 working days, so **apply by 28 October**.
  - Thailand: the Digital Arrival Card, **submit from 17 November**, three days before landing.
- **"Prepare my Thai arrival card — TG949, Hotel Example, Bangkok"**
  - 3 of 5 sections filled: the passport from the Keep (••••456), the flight and the hotel from the trip.
  - Personal Information and the Health Declaration are left for them.
  - "You submit the card on the official site, https://tdac.immigration.go.th … I can't submit or pay for you."
- **"Prepare the UK one"**
  - The official address is https://www.gov.uk/eta/apply, and they submit and pay there.
  - The sandbox's ETA lists no field it can fill from the Keep yet. That is AgAPI's field list, not Sasha.

## 2 · My Keep (/s2 tab "My Keep" + S1's /keep — one shared screen, `app/keep/KeepScreen.tsx`)
- `GET /api/agent/keep` now returns each item's **uses**: what it was used for and when, from the Activity rows the Keep writes.
- The proof went through the site's own proxy, the same call the screen makes:
  > • Passport ES ••••456 [yes] — Saved · 07:27 UTC
  > • Iberia Plus ••••432 [free] — Used — British Airways BA 0107 booking UZL23N (sent; not shown back on the airline's booking) · …
  > • Marriott Bonvoy ••••567 [free] — Used — Bankside Hotel, Autograph Collection booking TEST-51A52C · 07:54 UTC …
- Add and delete are the existing /keep form and buttons, now also on /s2.
- **"What's in my Keep?"** → "three things… a Spanish passport, ending 456… Iberia Plus, ending 432… Marriott Bonvoy, ending 567.
  I only ever see the masked versions."
- No screenshot: signing in to production as the guest would mean typing its password.

## 3 · Loyalty applied (booking code, shared by S1 and /s2)
- **Hotel:** the stay's booking record carries the group's programme (mask only). The test hotel has no system to receive the number.
  Live: Bankside Hotel, Autograph Collection (a Marriott brand) → **"I've added your Marriott Bonvoy ••••567 to this booking."**
  The record reads `{"loyalty": {"program": "Marriott Bonvoy", "masked": "Marriott Bonvoy ••••567"}}`.
- **Airline:** the number goes on Duffel's `loyalty_programme_accounts`, but only for programmes the offer itself lists.
- **Found live (1):** Duffel's TEST Iberia offers support **no** loyalty programme. Its BA and AA offers support IB.
  So the match follows the offer, and Iberia Plus goes on a BA flight (8301d96).
- **Found live (2):** Duffel's TEST orders accept the field but **show an empty list back**. I checked twice: once sent at order time,
  once at offer-request time. The first BA proof said "added" from what was *sent*. That was a false success, fixed in fd6811f.
  - "Added" is now said only when Duffel's ORDER shows the account. Otherwise she says:
    **"I sent your Iberia Plus ••••432 to British Airways with this booking, but their booking doesn't show it back yet — check
    it's on your boarding pass."** (live, trip 3)
- **How the bookings were made:** each TEST trip reached the pay card in chat. The Stripe TEST page was **not** paid (no card is ever
  typed). The after-payment step (`book_paid`) was run as the server runs it: Duffel TEST orders, the TEST hotel recorded.

## 4 · Upgrade my room (`hotel_request`, /s2)
- "Upgrade my room at the Bankside for my 2 November stay" → the read-back:
  > "Kanoe Test Hotel's own website lists recepcion-prueba@booking.kanoe.ai for guests' requests. This stay is a TEST booking, so it goes
  > to our test hotel — captured, it never leaves Kanoe." + the email, in Spanish, with reserva TEST-A31E55.
- The address was READ from the test hotel's own page through the ladder (`venues/read`).
- "Yes, send it." → delivered to our test hotel. Its reply, word for word:
  > "Buenos días: gracias por su mensaje. Para su estancia podemos ofrecerle una habitación superior con vistas por 25 € más por noche,
  > o sin coste si a su llegada queda alguna libre… Recepción · Kanoe Test Hotel (hotel de pruebas de Kanoe: no es un hotel real)."
- **Found live:** the first run said "not sent" beside a reply, then "it clearly did reach them". Fixed in 662e696: it is said as
  delivered to our test hotel inside Kanoe, never the real hotel.

## 5 · Hours check (the page route)
- Método Javier Panizo (Treatwell), Sat 17 Oct 17:00, said before the link:
  > "Heads up: by their listed hours they're closed on Saturday 17 October at 17:00 (Closed Sat 17:00 (no later opening that day);
  > Sat: 08:00–14:00). Pick a time inside their hours on their page, or tell me another time."
- **Found live:** Google's hours are never stored (its terms), so the first run said nothing. Fixed in fcae6df: the listing is
  re-read for this response only, at one Places call (a ticket proof).

## Cleanup
- Scratch guest c3325257 deleted (200).
- **Found:** deleting a guest leaves its **Keep** (3 items + its key) and its **Activity** (12 rows). I removed them by hand for this
  scratch account; there are now 0 rows in every public/auth table.
- Duffel TEST orders (no money) and the sandbox's end user (fictional passport) were left as test data.

## Still open
- **Gate key:** paste the `sasha-gate` key here. I'll set it as SASHA_GATE_ANTHROPIC_API_KEY (fingerprint only), and the next gate log will name it.
- **Deletion on request:** an account's deletion must also shred its Keep and its Activity. It doesn't today. This is a code fix (the
  guest delete path); tell me to make it.
- **Two Keeps:** /s2's entry check reads AgAPI's Keep, not Sasha's, so a passport saved on /keep isn't seen by `entry_documents`
  until it's also in AgAPI's Keep.
- **Duffel loyalty:** whether Duffel applies the number in LIVE mode can only be known from a live order. TEST mode doesn't show it back.
