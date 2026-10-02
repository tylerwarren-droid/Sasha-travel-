# S-74 — CoverManager: the slot link, hardened (and what pre-fill still needs)

*Sasha tab, 2 Oct 2026 (Sasha 95). ⛔ **covermanager.com was never requested** (S-35: TheFork blocked the founder's
home IP over platform probing). Everything below comes from the links Madrid venues publish on their **own** sites.*

## The finding that makes this the priority

Madrid survey (S-73), 384 restaurant sites:
- **142 book through a platform widget.** CoverManager is the largest, at **96**, then TheFork 29, Restoo 9 and Resy 4.
- **Only 6 have a clean form of their own.**

A guest's restaurant is therefore far more likely to need a slot link than a form.

## What venues' own sites show about CoverManager (40 sites read)

- **A booking page:** `covermanager.com/{reservation|reserve}/module_restaurant/<slug>/<language>` (spanish,
  english, french, chinese), or a short link `covermanager.com/go/<slug>/<xx>`.
- **Not a booking page:**
  - `/js/iframeResizer…` (the widget's script, the commonest string on these sites);
  - `/eco/buy_products/<slug>/…` (**gift vouchers**);
  - `/marketplace/…`;
  - `/reserve/gtmcrossdomain/…`.
- **Query strings seen:** tracking (`fbclid`, `source`, `utm_*`) or widget display (`day=1…7`, `timefix`,
  `template`). **No date, time or party pre-fill parameter appears anywhere.**
- **Only 11 of 40 produced a usable link** before this fix. Most venues *embed* the widget (an iframe or a script),
  and the reader kept only the first link per platform, which could be the gift shop.

## What the code now does (commit below; tests in `test_booking_ladder.CoverManagerPage`)

1. The read keeps **every** link and embed to a platform, not only the first.
2. `slot_link.covermanager_page()` accepts only a booking page, canonicalised, with tracking and display parameters
   dropped. A linked page beats an embedded one. A site that links **several different** restaurants (a group, such
   as Saona's 60) gives **no link**: which one is the guest's is theirs to say, never guessed.
3. **Ladder:** when a platform is their booking route, Sasha leads with the slot link and says it plainly: *"They
   book only through CoverManager, so you make the final press there. I can't press it for you."* The read-back:
   *"…takes bookings only through CoverManager, so you make the final press — I can't press their button for you."*
4. **Chat:** for such a venue the chat shows the slot-link card first. It prepares the page with the exact day, time
   and number to pick, has *Open their CoverManager page*, *I booked it* and *Check for the confirmation*, and offers
   *"or have Sasha call them instead"* only when a call is possible.

## Pre-fill (the founder's one capture; until then the page opens unfilled and Sasha says what to pick)

`slot_link.RECIPES` stays **empty for CoverManager**. A recipe exists only from the founder's own browser, verified once.

1. 👤 **On his phone, on mobile data, not home WiFi** (bot protection scores the network).
2. Open one venue's page, for example `https://www.covermanager.com/reservation/module_restaurant/restaurante-coque/spanish`.
3. Choose a day, a number of people and a time, **without** confirming. Copy the address bar's URL each time it changes.
4. Paste the URLs into the tab.
   - **If the URL carries the choices** (e.g. `?date=…&people=…`), the tab writes the recipe and he opens one built
     link to verify it.
   - **If the URL never changes**, CoverManager keeps the choice inside the page. No link can pre-fill it, and the
     honest words stay as they are.
