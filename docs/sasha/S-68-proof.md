# S-68 — proof against the live API (1 Oct 2026)

*Sasha tab. The calls went through the founder's session on project.kanoe.ai (`/api/booking-proxy/venues/*`), from a
browser console. The chat UI itself was **not** driven: its input starts a live avatar session (mic and camera), so I
started one by accident and ended it at once. The cards and chips (step 8) are verified by build and types only. They
have not been seen on screen.*

## The proof sentence, in two parts

**"a tattoo parlour in Madrid, open Tuesday 17:00, near my hotel"**: `near: "my hotel"`, `open_at: 2026-10-06T17:00`

- HTTP 200 · 20 results · `near: {found: false, why: "which hotel? — tell me its name or address and I'll measure from it"}`
- chips: rated, price, open. **No "Closest" chip.** In the chat it shows what it needs; the hotel is not guessed (no
  itinerary holds a hotel today).
- count: **"19 of 20 open at 17:00 by their listed hours"**

**The same, with "near Hotel Urban"**

- HTTP 200 · `near: {asked: "Hotel Urban", found: true}` · chips: rated, price, open, closest
- **★ Best rated (default), top 5**: 5.0 (574) 1.2 km · 5.0 (3701) 1.7 km · 5.0 (620) 2.2 km · 4.9 (1088) 380 m ·
  4.9 (139) 650 m. All have 20+ reviews; ties at the same rating go to the closer place.
- **📍 Closest, top 5**: 360 m · 380 m · 510 m · 530 m · 650 m, each with its rating.
- **€ Price**: €€ first, and "price level not listed" last. The one place closed then sits at the very end, greyed:
  "★ 4.9 (447) · 980 m · price level not listed · Closed Tue 17:00 (no later opening that day) · closed_then".
- Every card says how Sasha books, for example "Sasha will check their site for a form or an email", or "a phone
  number is listed, but Sasha's calls are off right now — you'd phone them". Calls are off, and the card says so.
- **Split days:** none of the 20 listings has a split Tuesday, so no gap was seen live. The tests prove the gap:
  "Closed Tue 15:00 (opens 17:00)" (`tests/test_hours.py`, `tests/test_find_venues.py`).

## Pick → venue read (Sasha 64 storage, verified in the database)

A pick by `place_id` with `asked_for: "tattoo studio"` returned 200. The venue's own site was read: phone, email,
WhatsApp, hours and name. The listing was shown with its "Google Maps" attribution. The stored row
(`venue_reads 1ab8a0b1-…`) holds:

- the name from the venue's own site;
- `query` = city, country, place_id and asked_for, with no listing name;
- `listing = {place_id}`;
- every listing fact with `value: null`;
- no street text;
- a Places source of URL, result and time only.

The name's page-title tail ("| Mejor estudio…") was trimmed in step 4's commit. That row is a scratch read from this
check; it holds no listing content.

## Not done

- **→ S-66 booking from the pick:** calls are off. The live in-chat call is held for the founder's venue pick (Sasha 62).
- **Step 9 (style):** waiting on a decision. See the reply.
- **013 purge:** written and dry-run, **not applied**. The founder runs it.
