# Sasha 300 → CR 131 · what AgAPI must add so a booking is managed after it's made (slice 1)

Sasha 300 builds the Sasha side against THIS contract: one itinerary, change / cancel / running late by the route the booking was made
on, and reminders. Each item below is called by Sasha already; until AgAPI answers it, Sasha says plainly that it can't be done
from here yet, and nothing is sent. Nothing here is built in AgAPI by the Sasha tab.

The ONE record is AgAPI's booking record: the act (`act_id`) on venue_sent / venue_requests. Sasha keeps only a pointer to it
(s2_memory "venue_acts": the act_id, which trip it's on, the venue's place_id), never a second truth about its state.

## (a) Every route is an act on the record — the hand-overs too

Today a platform hand-over (venue_prepared, gone after 24 h) and an own-WhatsApp hand-over (wa.me from his phone) never become acts,
so Sasha keeps them in its own prepared_pages. Ask: when Sasha hands one over, it becomes an act.

```
venue.handed_over {end_user, prepared_id, how: "platform" | "whatsapp_person" | "their_page", link?: url}
  → {act_id, state: "handed_over"}
```
- No approval (nothing is sent by Kanoe). Idempotent per (end_user, prepared_id, how).
- The act keeps the slot (at, party, person_name) past venue_prepared's 24 h.
- Its later states come from what exists: `venue.person_report` (sent_by_person / booked / changed / not_booked), a platform
  confirmation (`venue.confirmation`), and the venue's reply to his own WhatsApp when he forwards it.

## (b) One list: the person's bookings, from the record

```
venue.bookings {end_user, from?: "YYYY-MM-DD", include_cancelled?: bool}
  → {bookings: [{
       act_id, state,                          // sent | confirmed | proposed | declined | cancelled | failed | calling |
                                               // no_answer | handed_over | sent_by_person | booked_by_person | opted_out
       route,                                  // "email" | "whatsapp" (Kanoe's) | "whatsapp_person" | "platform" | "their_page" |
                                               // "call" | "form"
       platform?: "CoverManager" | …,
       venue: {name, place_id?, address?, maps_url?},   // address/maps_url: the listing's, as AgAPI may keep them
       at: "YYYY-MM-DDTHH:MM" (venue local), party, reference?,
       venue_words?: {untrusted_text, at},     // their last reply
       manage: {change: how, cancel: how, late: how},   // how: "message" | "their_page" | "call" | "not_possible"
       manage_url?: url,                        // a platform's / their page's own change-cancel page, when known
       external_ref?: string                    // whatever Sasha passed (its trip id), echoed
     }]}
```
- `venue.prepare_booking` and `venue.handed_over` accept `external_ref` (≤ 80 chars; Sasha sends `trip:<uuid>`), kept on the act.

## (c) Change and running late: one op, by the act's own route

```
venue.change_booking {end_user, act_id, kind: "change" | "late", at?: "YYYY-MM-DDTHH:MM", party?: int, arrive?: "HH:MM"}
  → without AgAPI-Approval-Id: error approval_required {read_back_id, read_back_sha256, lines}
  → with it: {status: "sent", change_act_id, say}   (email / Kanoe WhatsApp / call — the ROUTE the act went by)
           | {status: "not_allowed", say, takeover?: {kind: their_page|their_listing, link?, phone?}}
           | {status: "person_sends", message: {text, link}}            (whatsapp_person: the wa.me text, for HIM to send)
```
- Never a route the act didn't go by. A call act's late/change is a call; an email act's, an email (in the venue's language).
- Kanoe's WhatsApp outside the 24 h window: an approved template for change / late / cancel (none exists today: the T1 send
  fails with "date and time aren't on its record").
- The venue's answer to a change comes back on the change act, classified AGAINST THE CHANGE (`proposed` / `confirmed` /
  `declined`): a yes to 21:30 → the original act's `at` becomes 21:30 (apply_outcome already moves venue_sent.at_when and the
  calendar event); a no → the original stands, said.
- `venue.booking_status {act_id}` of the ORIGINAL act carries `change: {state, at?, party?, venue_words?}` while one is open.

## (d) Cancel: the same, per route — and the gaps found

`venue.cancel_booking` exists. Asks:
1. Email subject "Cancellation: …" (today the cancel email goes as "Booking request").
2. Kanoe's WhatsApp outside 24 h: the cancel template (as (c)); today the cancel's data has no `at`, so it fails.
3. `whatsapp_person` → `{status: "person_sends", message: {text, link}}` (the wa.me text, in the venue's language).
4. `platform` / `their_page` → `not_allowed` WITH `manage_url` when known (today: no URL, only "their confirmation says how").
5. The venue's reply to a cancellation is CANCELLED, not `declined`: NO_IN matches "booking cancelled" / "has been cancelled" and
   labels it declined; Sasha only treats a cancel act as done when it reads `confirmed`. Ask: a reply to a cancel act that says
   it's cancelled → `cancelled` on the original act.
6. Two open acts to one WhatsApp number (the booking and its cancellation): `_only_open` finds two and leaves the reply unmatched.
   Ask: a cancel / change act is matched first.

## (e) What reminders need

`venue.bookings` rows carry `venue.address` and `maps_url` (the listing's, as the terms allow; today the .ics is built with
address=None). Sasha builds the map link from `place_id` meanwhile (a Google Maps search link: no API call).

## What Sasha 300 calls today

- `venue.change_booking`, on his ask only. It is answered `unknown_operation` today, which Sasha says plainly; nothing is sent.
- `venue.cancel_booking`, as before.
- `venue.bookings` and `venue.handed_over` are NOT called yet (an unknown op on every itinerary read would only add a request).
  The itinerary reads the acts Sasha points to (`venue.booking_status`, each act) and its own hand-over rows. When (a) and (b)
  land, `agapi/itinerary.py` is the one place that switches.
