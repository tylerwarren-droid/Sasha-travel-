# Fine print, steps 4–5 + the beta set of 12 cards

*CR 74b · 10 Oct 2026 · branch `cr/agapi-api`. Builds on steps 1–3 (`steps-1-3.md`) and EU 216 (`docs/sasha/s2-money-and-cover.md`
in the AD repo).*

## The beta set

**Exactly the 12 cards Tyler named** (seeds `beta: true`), plus the labelled "Example Bank" fixtures:
- **US:** Chase Sapphire Preferred, Chase Sapphire Reserve, Citi AAdvantage Executive, Capital One Venture X, Amex Gold, Amex Platinum.
- **Europe:** Revolut Metal (EEA), American Express Platinum (Spain).
- **UK:** British Airways American Express Premium Plus, Barclaycard Avios Plus.
- **Spain:** BBVA and Santander, the premium card with the fullest official travel-insurance terms (see Results).

**Other cards** (Discover, Bank of America, Bilt, Wells Fargo Autograph) are **kept but never used**:
- `cards.products` and the review page list only the beta set;
- `cards.ask` says "isn't in the cards I answer for yet";
- `cards.which` and `cards.rental_cover` skip them, saying so.

**Claims scoped to their benefit:** the reader now marks which benefit a claims fact belongs to (`notice_deadline_days@car_rental`, …).
The six US beta cards were re-read for it: one card's terms give different deadlines for baggage, trips and rentals.

## Step 4 · rental cover: the counter card (`cards.rental_cover`, `fineprint/rental.py`)

**Input:** country + rental company (+ days, vehicle) + the person's cards.

**Sources:**
- the cards' claims;
- **the rental company's own terms for that country**, read like card terms (purpose `card_terms`, kind `rental`): the excess, the
  CDW and the cover that removes the excess (name, price), the liability included, the deposit, the licence / IDP rule, and the
  accident-report deadline.

**Rental terms seeds:** Sixt (Portugal, Spain), Europcar (Portugal), Hertz (Spain), and "Example Rentals" (Portugal, a labelled test
fixture). They're checked on the same review page.

**The counter card:**

| Line | When | From |
|---|---|---|
| **Decline** the CDW/LDW | only if the card's terms say it covers damage AND theft, say the rental company's CDW must be declined, AND list the excluded countries without this one | the card's quotes |
| **Check** first | any of those missing: "ask the card's claims line before you decline" | the card's quotes |
| **Keep** the included liability | always shown; "the terms don't say" if they don't | the rental's quote + the card's "liability isn't covered" quote |
| **Optional:** the excess cover | when the rental terms name it | its name, price and the excess it removes, quoted |
| **Conditions**, **bring**, **report** | pay with the card, decline the CDW, the maximum days · the IDP / licence, the deposit · the rental's report deadline, the card's notice deadline and claims line | quotes |

**Never "you don't need insurance":** a guard refuses any such line, and the vectors assert it.

**Vectors:** `spec/ext/vectors/rental.json` (7 cases):
- a primary card in Portugal;
- an excluded country;
- no excluded-country list;
- no must-decline term;
- a rental too long for the card;
- rental terms not read;
- a card with no rental terms.

## Step 5 · claims (`cards.claim_*`, `fineprint/claims.py`)

| Operation | What it does |
|---|---|
| `cards.claim_start` | the claims administrator's route (administrator, email, portal URL, phone) and the **deadlines** (notice / documents, scoped to the benefit), quoted, with due dates from the incident date and reminders at −14 / −3 / −1 days. **A deadline the terms don't give is said missing, never assumed.** **No clause in the terms → no claim:** "I won't file a claim they don't support". The evidence checklist: each missing item says where to get it (the PIR from the baggage desk, …). The Keep's booking references count |
| `cards.claim_attach` | a receipt, letter or photo, **sealed under the person's own Keep key**. A file showing a full card number is refused |
| `cards.claim_file` | **the read-back:** the administrator and its address, what happened, the amount, **the clause relied on (quoted)**, the attachments, what's still to follow, the deadline. Then **their yes in a later turn** (a question isn't a yes), then **one email** to the administrator's address from the terms. Test mode: captured, never sent. Live: the email allow-list, so a real insurer is refused until Tyler adds it. **A portal behind a login:** everything prepared, and the person logs in themselves |
| `cards.claim_status` | the state, deadlines, reminders, and the administrator's replies, **as untrusted text** (instruction-like text flagged) |
| `cards.claim_simulate_reply` | test mode only: the demo's insurer inbox |

**Not yet:**
- **Real replies by email:** they need an inbound-email route. Test mode uses `cards.claim_simulate_reply`.
- **Live filing:** attachments are listed in the email by name and fingerprint. Sending the files themselves comes with live filing.
- **Refusals:** the refusal-response drafter is EU 216's step 8.

## Results

**The beta set, read on 10 Oct 2026 from the sandbox server:**

| Card | Read | Facts quoted | Benefits with facts |
|---|---|---|---|
| Chase Sapphire Preferred | cleanly | 63 | car rental 9, claims 13, extended warranty 2, points 19, purchase protection 8, travel insurance 12 |
| Chase Sapphire Reserve | cleanly | 49 | car rental 8, claims 15, extended warranty 2, lounges 3, points 6, purchase protection 5, travel insurance 10 |
| Citi AAdvantage Executive World Elite Mastercard | cleanly | 40 | car rental 7, claims 7, extended warranty 2, lounges 3, points 6, purchase protection 8, travel insurance 7 |
| Capital One Venture X Rewards | cleanly | 48 | car rental 8, claims 13, lounges 3, points 5, purchase protection 8, travel insurance 11 |
| American Express Gold Card | cleanly | 22 | car rental 6, extended warranty 1, points 9, purchase protection 2, travel insurance 4 |
| American Express Platinum Card | cleanly | 16 | car rental 9, claims 2, lounges 2, points 3 |
| Revolut Metal (EEA) | cleanly | 17 | car rental 3, claims 3, travel insurance 11 |
| Tarjeta Platinum American Express (España) | cleanly | 42 | car rental 8, claims 6, lounges 1, points 4, purchase protection 7, travel insurance 16 |
| British Airways American Express Premium Plus Card | cleanly | 26 | claims 4, points 2, purchase protection 9, travel insurance 11 |
| Barclaycard Avios Plus Card | thin | 5 | fx fee 1, lounges 2, points 2 |
| Tarjeta Unlimited Santander World Elite | cleanly | 20 | car rental 4, claims 3, lounges 1, points 1, purchase protection 1, travel insurance 10 |
| Tarjeta de crédito Visa Platinum BBVA | not read: HTTP 403 | 0 | — |

**Which read cleanly (≥ 15 quoted facts):** Chase Sapphire Preferred, Chase Sapphire Reserve, Citi AAdvantage Executive, Capital One
Venture X, Amex Gold, Amex Platinum (US), Revolut Metal (EEA), American Express Platinum (Spain), BA American Express Premium Plus,
Santander Unlimited World Elite.

**Thin:**
- **Barclaycard Avios Plus:** its official documents are the credit agreement and the Avios rules. Neither is travel-insurance terms,
  and only 5 facts were quotable.
- **Amex Platinum (US):** 16 facts. Its benefit terms sit behind JavaScript pop-ups.

**Not read:** **BBVA**. bbva.es answers HTTP 403 to every request from the sandbox: the product pages and the PDFs of all three
candidates (Visa Platinum, Infinite Patrimonios, Iberia Visa). There's no way around it that respects the site. **Option:** a person
downloads BBVA's official insurance PDF in a browser and gives it to AgAPI to read. Its source is then recorded as "a person".

**Santander's pick: Tarjeta Unlimited Santander World Elite** (the Private Banking Unlimited card). It's the premium card whose official
travel-insurance terms ("Seguro de viaje", Inter Partner Assistance for Mastercard) gave the most: 20 facts, against 12 for the Iberia
Cards Santander certificate. **BBVA's pick: none could be read.** Visa Platinum is kept as the slot, shown unread.

**The rental companies' own terms:**

| Rental terms | Read | Facts |
|---|---|---|
| Example Rentals terms (Portugal) | yes | 15 |
| Europcar rental terms (Portugal) | yes | 11 |
| Hertz rental terms (Spain) | yes | 6 |
| Sixt rental terms (Portugal) | no: robots.txt disallows this path for automated readers | 0 |
| Sixt rental terms (Spain) | no: robots.txt disallows this path for automated readers | 0 |

- **Sixt:** its robots.txt disallows the terms pages for automated readers. Respected: not read.
- **Europcar:** read from its general rental terms and protection pages, which apply "in the country of rental". They aren't specific
  to Portugal, and the counter card shows the quotes as they are.

## Tests

`agapi_service/tests/test_cr74.py`:
- **the beta set:** only the beta set answers;
- **rental:** the vectors, the guard, the counter card through the API on the fixtures;
- **claims:**
  - the plan's deadlines, including a missing one;
  - start → attach → read-back → a question refused → "Yes, file it." → filed once → a reply flagged as instruction-like;
  - a claim the terms don't support is never filed.
