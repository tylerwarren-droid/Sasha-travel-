# Fine print, steps 1–3: card terms as cited claims, cards in the Keep, answers only from quotes

*CR 74 · 10 Oct 2026 · branch `cr/agapi-api` · EU 216's build order (`docs/sasha/s2-money-and-cover.md` in the AD repo), steps 1–3.
S2 wiring: Sasha branch `cr/s2-fine-print` (`docs/sasha/s2-fine-print-wiring.md` there).*

## Step 1 · the claim store

**What's in it** (`agapi_service/fineprint/model.py`, on the registry's claim model):
- **`card_products`:** issuer · product · network · country, the seeds, the read status, and whether a person **accepted** the first read.
- **`card_claims`:**
  - each benefit field (EU 216 §1 table, `fineprint/schema.py`) has a value + `source_url` + the **verbatim quote** + `read_at`
    (plus `quote_sha256`, `claim_sha256`, `rcl_` ids);
  - claims are **never edited:** a re-read writes new claims and supersedes the old ones.
- **`card_sources`:** each document read, with its `body_sha256`.

**Freshness:**
- **Re-read** every **60 days**, and **immediately when a source's body changes** (`fineprint/jobs.py`: daily with
  `AGAPI_FINEPRINT_SCHEDULE=1`, or the signed admin action `card_read` / `cards_tick`).
- **A changed source:** the quotes that vanished are marked **drifted**. They're shown with "The issuer's terms changed on …; this was
  read … and is being re-read" until the re-read replaces them.
- **Stale:** past the re-read date + 30 days, a fact carries a warning and is never used without saying so.
- **A failed re-read keeps the last good claims.**

**`magellan.read_site` purpose `card_terms`** (`fineprint/reader.py`, additive to the enum):
- **What it reads:** the issuer's own pages and the documents they link to: the Guide to Benefits, the insurance certificate, rates
  and fees. It reads **HTML or PDF** (pypdf).
- **Gates:**
  - **robots.txt first, strict:** an HTML robots file is unreadable, which means not allowed;
  - AD's **never-fetch** list;
  - booking platforms are never read;
  - at most 14 fetches a card.
- **No affiliate links:** tracking and affiliate parameters are stripped from every URL kept, and none is output.
- **What becomes a fact:**
  - a quote is checked **word for word** against its document, or dropped;
  - **a number must appear in its own quote;**
  - instruction-like text is never a fact.
- **What it never decides:** whether someone is covered.

**The accept surface** (`fineprint/review.py`, `/fineprint/review`):
- A Kanoe person checks each card's **first** read: every fact with its quote and source, the documents read, and those not read (with
  why). The choices are Accept or Not usable.
- Until it's accepted, no answer uses the card. Later re-reads are automatic.
- **Access:** a one-time link (signed admin action `review_link`, 15 minutes, used once) opens a 12-hour session.

**The seeds** (`fineprint/data/seeds.json`):
- **The 10 cards of Sasha's old `card_benefits_db`.** It's used only to choose which cards; its uncited figures aren't used.
- **For each card:** the issuer's own terms documents, found by a desk search on issuer domains only, plus its product page.
- **The demo's "Example Bank":** a labelled test fixture. Its two cards, each with a PDF Guide to Benefits, are served by the sandbox.

## Step 2 · `card_product` in the Keep

- **The type** (in `backend/agapi/keep.py`, shared with Sasha): issuer · product · network · country (optional).
  - Tier: free.
  - Mask: "Chase Sapphire Reserve · Visa".
  - **Any run of digits is refused (`never_card`):** a card number, the last four, "••42", "XXXX".
- **`cards.intake`:** a **photo of the card or a Wallet screenshot** → the AI reader names the product. Then:
  - the reader is told never to output a digit;
  - its answer is checked anyway: a card number anywhere in it refuses the whole intake;
  - **the image is read once and dropped:** never stored, logged or hashed into evidence;
  - the product is matched to the claim store only on its whole name, never a near guess.
- **`cards.mine`:** "My cards". Each card has its terms status ("terms read 2026-10-10" · not read yet · awaiting a check).

## Step 3 · the Q&A, and which card

**`cards.ask`** answers "what does my X cover for Y?" **only from quotes:**
- **What the AI reader does:** it only **chooses** which of the card's claims answer the question, and says yes / no / partly.
- **What the person reads** (`fineprint/answer.py`) is built from the quotes themselves: *"Your {card}'s terms (read {date}) say:
  "{quote}". So: no, as the terms state it. Source: {url}."* The quotes are never edited, not even their full stops.
- **No claim chosen**, or a claim from another card: *"The terms I've read don't say."* + the **claims line quoted** from the same
  terms (or that they give none).
- **Without the AI reader:** the quotes matching the question's topic, with no verdict.
- **A card not read yet, or not yet accepted:** said, never guessed.

**`cards.which`** answers "which of my cards for this?". It ranks the person's cards from their claims alone:
- the **FX fee** (quoted %, and its cost on this purchase; none in the card's own currency);
- the **points** (quoted rate × amount; a rate stated per another currency is said);
- the **cover that applies** (quoted).

Cards are ordered by FX cost, then cover, then points. The framing is fixed: *"Information from your cards' own terms. You decide."*
No card is "recommended".

**Vectors:** `spec/ext/vectors/cards.json`: the ranking and the exact answer sentences.

## Operations (Kanoe extensions for EU to formalize; scope `cards.*`)

| Operation | Cost | What it answers |
|---|---|---|
| `cards.products` | read | the card products read: terms date, freshness, accepted |
| `cards.terms` | read | one product's benefits, every value with its quote, source and date, and warnings |
| `cards.intake` | search | photo / Wallet screenshot → the card product, saved to the Keep |
| `cards.mine` | read | "My cards" |
| `cards.ask` | search | the answer, only from quotes |
| `cards.which` | read | the ranked cards, every reason quoted |

## Results

**Read on 10 Oct 2026 from the sandbox server.** For the 10 real cards: 239 facts quoted word for word, 0 quotes off their page,
≈ $3.5 of AI reading.

| Card | Documents read (used) | Facts quoted | Benefits with facts | Not read |
|---|---|---|---|---|
| American Express Platinum Card | 14 (2) | 16 | car rental 9, claims 2, lounges 2, points 3 | — |
| American Express Gold Card | 12 (1) | 22 | car rental 6, points 9, purchase protection 2, travel insurance 5 | — |
| Chase Sapphire Reserve | 14 (2) | 44 | car rental 8, claims 9, extended warranty 2, lounges 3, points 4, purchase protection 8, travel insurance 10 | — |
| Chase Sapphire Preferred | 14 (3) | 57 | car rental 9, claims 10, extended warranty 2, points 19, purchase protection 7, travel insurance 10 | — |
| Capital One Venture X Rewards | 14 (2) | 36 | car rental 8, claims 10, lounges 2, points 1, purchase protection 7, travel insurance 8 | — |
| Citi AAdvantage Executive World Elite Mastercard | 6 (4) | 38 | car rental 8, claims 5, extended warranty 2, lounges 3, points 6, purchase protection 6, travel insurance 8 | — |
| Discover it Miles | 13 (2) | 4 | points 4 | HTTP 404 |
| Bank of America Travel Rewards | 7 (0) | 0 | — | HTTP 403 |
| Bilt Mastercard | 9 (2) | 5 | car rental 1, claims 4 | — |
| Wells Fargo Autograph Card | 13 (3) | 17 | car rental 7, claims 4, points 6 | HTTP 404; robots.txt couldn't be read (ConnectErro |
| Example Bank Travel Visa | 2 (1) | 26 | car rental 9, claims 5, fx fee 1, points 5, travel insurance 6 | — |
| Example Bank Everyday Mastercard | 2 (1) | 7 | claims 3, fx fee 1, points 1, purchase protection 2 | — |

**What it shows:**
- **The old database's figures are replaced, not extended.** Two of its seed URLs had moved: Chase's product pages answered 404 (EU
  216's "four months stale"). The cards were re-read from the issuers' own Guides to Benefits: for Chase, Capital One (Visa Infinite)
  and Citi, the PDFs on their own hosts.
- **Amex** publishes its card benefit terms behind "Terms apply" pop-ups drawn by JavaScript. Fewer facts were quotable there
  (16 · 22).
- **Bank of America's** rewards rules host answered 403, and nothing on its product page could be quoted. Its answers say "the terms
  I've read don't say".
- **Discover's** terms PDF moved (404). Only its earn rates were quoted.
- **The FX fee** sits mostly in the issuers' pricing tables, which aren't in these documents. For most real cards the FX fee is
  "the terms I've read don't say", which `cards.which` says plainly.
- **Claims deadlines differ by benefit** (e.g. Chase: rental 100 days, baggage 20, trip 90). Each claim's quote says which benefit it
  belongs to. **Step 5** (claims) scopes them per benefit.
- **The 10 real cards are waiting for a Kanoe person's check** on `/fineprint/review`, so no answer uses them yet. The two Example Bank
  cards are accepted (a test fixture).

## Tests

`agapi_service/tests/test_cr74.py` (24). With the rest: 203 green on SQLite and Postgres.
