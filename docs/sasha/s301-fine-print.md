# Sasha 301 · booking management slice 2: THE FINE PRINT ON EVERY BOOKING

Tyler, 28 Oct: "the fine print: card perks, deposits, cancellation terms, loyalty numbers".

## Root test (written before code)

1. **One itinerary, one Keep.**
   - Every fine-print line hangs on THE ONE ITINERARY's row (`agapi/itinerary.py`).
   - The venue's terms are read at view time from the venue's own words already on that row:
     - an AgAPI act's `venue_said` (venue.booking_status `venue_words`);
     - the old ladder's `venue_words`.
   - Nothing is copied into a store of its own.
   - His cards and loyalty numbers live in ONE place: his Keep (`agapi/s2_keep.py` on `agapi/keep.py`).
     - Loyalty: type `loyalty`, programme + number.
     - Cards: new type `my_card`, which holds the name, the last 4, and a perk in his words.
2. **PATCH if:**
   - a second store holds terms or his cards;
   - a term is typed by Sasha rather than the venue (each term is the venue's own sentence, and `quote in source` is checked in code);
   - a card number is kept in full. `keep.normalise` refuses one in any field, `last4` is exactly 4 digits, and any field with
     8+ digits is refused.
3. **After it:**
   - The itinerary can't show a term nobody stated.
     - Each term is a sentence of the venue's text.
     - A "by <date/time>" is computed only from a number of hours or days in that same sentence and the booking's own start.
   - It can't reveal a full card number: the Keep never holds one, and the row shows `•••• 1234`.
   - A loyalty number is shown by its mask only (`Marriott Bonvoy ••••789`), never in full.

## Build

- `agapi/booking_terms.py`: `terms_of(text, start)`. It finds deposit · cancellation (with "by" when stated) · no-show ·
  table time limit, in English and Spanish, plus the common words in PT/FR/IT.
- `itinerary.venue_rows` adds `terms`; `itinerary.of` adds `perks` (Keep matches); `as_reservation` carries `terms` (Trip tab,
  reminders).
- Matching:
  - A loyalty programme matches a booking through `booking_signer/loyalty.matches`, which is a fixed list (major hotel chains
    added), never a guess.
  - A card perk matches on the kind he said it's for (hotel / restaurant / spa / flight / car / any) and, when he named one, the
    chain or venue in the booking's name.
- Reminder `cancel_by`: due 6 h before a stated cancellation deadline, for a confirmed booking, once (ledger `booking_key`).
  It needs SQL 044 (kind check). Before 044 the claim is refused, it's logged once, and nothing is sent.
- Tools (/s2 · voice · WhatsApp, the one brain):
  - `booking_fine_print {on?, venue?}`: the row's terms and perks, `say` built in code.
  - `keep_note {kind: loyalty|card, …}`: what he tells her, saved in the Keep, mask returned.

## Known, not hidden

- **The vault's identifiers** (Sasha 131, `/vault` "Membership or loyalty number", read by `loyalty.find_for` for a form's
  comments box) were a second loyalty store before 301.
  - 301 neither reads nor writes them: the itinerary reads the Keep.
  - Retiring them is a separate ticket, because `venues._loyalty` is on CR 132's side of the branch.
- **AgAPI's `cards.mine`** (CR 74) holds card PRODUCTS so AgAPI can quote the issuer's terms. These are AgAPI's records, not his
  words; `my_card` holds his words.
- **An act's venue words are cut at 240 characters** (`venue_submit._words`). A term past the cut is a broken sentence, and a
  broken sentence is never shown.

## Asks for CR (AgAPI), not built here

- (a) `venue.bookings` / `venue.booking_status` carry the venue's full words (not cut), and the booking PAGE's own terms when the
  page read states them: `page_terms: [{untrusted_text, source_url}]`. Sasha reads `page_terms` the day it appears.
- (b) A platform's confirmation (`venue.confirmation`) carries its cancellation terms as the platform's words.
