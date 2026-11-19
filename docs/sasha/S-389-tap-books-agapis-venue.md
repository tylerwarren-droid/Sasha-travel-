# Sasha 389 · a tapped alternative books the venue AgAPI already resolved

## Measured (19 Nov, Tyler's WhatsApp; agapi-live logs, Twilio, sasha-prod, all read-only)

- **06:29:45** Sasha listed three Peñalver listings (Twilio content `9f250dd9`). Tyler typed "1 tomorrow", which is listing 1 (`ChIJnx_fKOApQg0RlDK1xQwDUBI`).
- **06:34:03** `venue.prepare_booking` decided `platform_book`, through the CoverManager widget, zero-touch.
- **06:34:34** `submit_booking` found no table at 21:30 and returned **four** alternatives.
- **06:34:28** Because there were four, Sasha sent them as a **list picker** (Twilio content `919be439`). Its rows carried the ids `card:alt_a0586c2f…:alt:1…4`.
- **06:37:10** Tyler tapped "21:45". The list row arrived as `ListId = card:alt_…:alt:1`.
- **Fault:** `products.tools.own_id` (Sasha 344) kept a list row's id only when it started with `kanoe:`. It dropped Sasha's own `card:` id, so the tap reached the **model** as the words "21:45".
- **What followed:** agapi-live then received only `venue.profile` (06:37:16). There was no `prepare_booking`, mandate or `submit_booking`. The model re-resolved the venue **by name**: the booking measure shows `venue = "name:…"` and stop `platform_handover`. `venues.floor` then built a **Google Maps search** link as "Tap to finish".

AgAPI is not at fault here, so there is no FOR CR for this tap. One related AgAPI item: its own route-`none` floor button can point at the venue's map listing. Sasha now refuses it (`own_page`).

## The root

**(a) One id namespace.** `products.tools.OWN_IDS` lists Sasha's own tap ids: `kanoe:`, `card:`, `pick:`, `say:`, `yn:`, `photo:` and `keep:`. Both `own_id` and `wa_agent.ours` read it, so a button and a list row are the same tap.

**(b) A tap never re-resolves.** `venues.option_place` builds the place from AgAPI's own `book` terms (its `place_id` and `url`). It adds the held venue's place only when AgAPI's option kind says it is the same venue (`same_venue_time`, `same_time_other_day`, `other_service_time`). There is no name comparison. If AgAPI decides an option another way, Sasha gives AgAPI's own answer for it (`option_not_booked`) and never falls back to `hold_venue` by name.

**(c) One fallback (KANOE_DECISIONS 12 Nov 20:21): the venue's own page.**
- `venues.own_page` is the one rule: a web page that is not a map or a search.
- `_link_out`, the one constructor of a hand-over link, and `floor` both use it.
- With no own page, Sasha says so plainly (`voice.NO_OWN_PAGE`) and offers nothing to tap.

## Tests

`tests/test_s389_tap_books_agapis_venue.py` covers:
- the real webhook, where a list row and a button with the same id both reach `card_tap`;
- every alternative kind (same evening, other day, other service, nearby), each prepared with AgAPI's identity and no re-resolve;
- AgAPI deciding an option another way, which gives its answer and never a map;
- a ratchet: no module on the booking path builds a google.com/maps or search URL.

Sasha 286's floor tests now follow the current decision. "Their listing" (a map) was the 24 Oct floor, replaced on 12 Nov.
