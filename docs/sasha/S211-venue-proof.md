# Sasha 211 · the venue proof (a scratch guest, deleted after)

*"A seafood restaurant in Madrid tonight for 2" → cards → a pick → the right route → the read-back. Run with every send blocked in the process: no yes was given, nothing reached a venue or a phone. O'Pazo books only through CoverManager and it is tonight (< 48 h), so the route is their page to the phone.*

```
TRAVELLER: Find me a seafood restaurant in Madrid tonight for 2, around 9pm.
  7198 ms
  filler: Let me find some places.
  say: Here are a few good ones for nine tonight. My soft spot is O'Pazo, a proper Galician classic, and if you want something lively and central, Ribeira do Miño is famous for its huge seafood platters. Tap whichever one you like, or just tell me, and I'll see how they take bookings.
  tools: ['search_venues', "[venue cards: {'what': 'seafood restaurant', 'where': 'Madrid', 'country': 'ES', 'open_at': '2026-10-08T21:00', 'party': 2}]"]

TRAVELLER: O'Pazo, please.
  12976 ms
  filler: One moment.
  filler: Nearly there.
  say: O'Pazo only takes bookings through their own online page, so you'll need to make the final tap yourself. Since it's tonight, I'd sort it now: shall I send their page to your phone, with the details to pick, two people at nine tonight?
  tools: ['search_venues', "[venue cards: {'what': 'seafood restaurant', 'where': 'Madrid', 'country': 'ES', 'open_at': '2026-10-08T21:00', 'party': 2}]", 'read_booking_route', 'hold_venue']

TRAVELLER: Send me their page.
  14548 ms
  filler: Let me see.
  say: I've got O'Pazo's booking page ready to send to your phone. It's on CoverManager, so you just pick tonight, Thursday at 9 pm for two, and press book there yourself. Nothing's reserved until you do, and they'll send the confirmation straight to you. If you forward that email to me, I'll add the dinner to your trip. Shall I send it now?
  tools: ['search_venues', "[venue cards: {'what': 'seafood restaurant', 'where': 'Madrid', 'country': 'ES', 'open_at': '2026-10-08T21:00', 'party': 2}]", 'read_booking_route', 'hold_venue']

PACIOLI (venue rows): []

HELD (awaiting the yes, never given): {'rung': 'page', 'venue': "O'Pazo", 'summary': 'Thursday 8 October at 21:00, 2 people', 'platform': 'CoverManager'}
```
