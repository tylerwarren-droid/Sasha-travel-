# Sasha 337 · planned_price on every group.book item (CR 164's ask)

## Root test (written first)

**The planned price lives in ONE place: the worker's ONE trip** (Sasha 332).

- Planning writes `trip_basket_items` rows on that trip: the flight out, the flight back, and the stay, each with its `price_amount` and `price_currency`.
- The master list reads those same rows. `group.book` reads them too, at the moment it builds the items.
- Each item's `planned_price` is `{amount_minor, currency}`:
  - the flight row whose day is the item's day (the out date, or the back date);
  - the stay row for the stay.
- AgAPI then re-prices at the airline and says "was €x when Sasha planned it" before the yes.

**No second copy.**

- Nothing is stored on the member, the card, or a cache.
- The value is read from the trip at prepare time, never remembered between calls.
- A row with no price sends no `planned_price`. Nothing is invented.

Copying the price anywhere else would be a PATCH.

**Test** (`tests/test_s337_planned_price.py`):

- every `group.book` item Sasha sends, for every worker, carries a `planned_price`;
- that price equals that worker's own trip row, as the master list shows it;
- change the trip row, and the next prepare sends the new price;
- the source holds no stored copy.
