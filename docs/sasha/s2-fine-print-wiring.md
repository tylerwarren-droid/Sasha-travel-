# S2's fine print: the wiring

*CR 74 · branch `cr/s2-fine-print` (from main `1bac4d1`), for the Sasha tab to merge. Not on main.*

> "Add my card" (a photo or a Wallet screenshot) → "Example Bank Travel Visa · Visa (no number kept)" →
> "Can I rent a car in Ireland on it?" → *"Your Example Bank Travel Visa's terms (read 2026-10-10) say: "Excluded countries: Ireland,
> Israel, Jamaica." So: no, as the terms state it. Source: …"* → "Which card for a €400 rental in the US?" → the ranked cards,
> each reason quoted, under "Information from your cards' own terms. You decide."

**Who does the work:** AgAPI (`cards.mine`, `cards.intake`, `cards.ask`, `cards.which`, plus `keep.put` type `card_product`, in
`cr/agapi-api`, deployed on agapi-sandbox). Sasha only asks and says.

**On /s2 only.** S1 (/next) never sees these tools: its tool list and its fingerprint are unchanged (tests below).

## What changes in the code

### 1 · `backend/agapi/s2_fine_print.py` (new)

/s2's four card tools:

| Tool | What it does |
|---|---|
| **`my_cards`** | the person's cards: products only (issuer, product, network), each with whether its official terms were read |
| **`add_card`** | from a photo or Wallet screenshot uploaded on /s2 (`card_image_ref`), or by the card's name. Only the product is kept, never a digit |
| **`card_cover`** | "what does my X cover for Y?" → AgAPI's answer, **built from the card's quoted terms**. She says its `say` text as given |
| **`which_card`** | "which of my cards for this?" → ranked by quoted FX fee, cover and points; the fixed framing line first; never "recommended" |

**Calls to AgAPI:**
- `SASHA_FINE_PRINT_VIA=sandbox` (the default) uses `SASHA_AGAPI_TEST_KEY`. That key is already set on Sasha's Railway (CR 73) and
  holds `cards.*`.
- `SASHA_FINE_PRINT_VIA=live` uses `SASHA_AGAPI_KEY`. The `cards.*` operations aren't on agapi-live yet: keep the sandbox for now.

**Card images:** kept in this server's memory for 10 minutes, read once, never on disk. AgAPI reads the image once and drops it.

**Ambiguity:** with two or more cards and no name given, `card_cover` returns `which_card` ("Which card?"). It never guesses.

### 2 · `backend/app/agent/sasha.py`

**Inside `if surface == "s2":`, after `run = VIA.runner(API.call)`:**
```python
from agapi import s2_fine_print as FP   # CR 74 · fine print: /s2's own four card tools, run here
tools = tools + [dict(t) for t in FP.TOOLS]
run = FP.wrap(run)
```

**A new route, `POST /api/agent/s2/card-image`:**
- Accepts `{media_type, content_base64}` and returns `{card_image_ref}`.
- Answers only with `x-sasha-surface: s2` and a signed-in account. /next gets 404.

### 3 · `backend/agapi/keep.py` (shared Keep logic)

**A new type, `card_product`:**
- Fields: issuer · product · network · country (optional).
- Tier: free.
- Mask: "Chase Sapphire Reserve · Visa".
- **Any run of digits is refused (`never_card`):** a card number, the last four, "••42", "XXXX". The refusal never repeats the digits.
- Additive: every other type is unchanged. It's the same file and the same change as AgAPI's copy in `cr/agapi-api`.

### 4 · Tests

**`backend/tests/test_s2_fine_print.py`** (new, 8 tests):
- the quoted answer is said as given;
- two cards without a name ask which, and never guess;
- a photo is read once and only by its own account; a name with digits is refused;
- `which_card` keeps the framing;
- it says "not switched on" without a key;
- S1 never sees the tools and S2 does;
- S1's fingerprint is unchanged, with zero fine-print calls;
- the image route is S2-only.

**`backend/tests/test_s2_221.py`:** S2's pinned tool set now also includes the four card tools. S1's checks are unchanged.

**Result:** the S2, agent, safety and Keep suites give **196 green**: main's 188 + 8.

## Merging alongside `cr/s2-subscriptions`

Both branches add tools and a `wrap` inside /s2's block. Keep both, in this order:
```python
run = VIA.runner(API.call)
run = SUBS.wrap(run)     # CR 72
run = FP.wrap(run)       # CR 74
```
(`cr/s2-subscriptions` was cut from `6899468`, before main gained `run = VIA.runner(API.call)`; keep main's line.)

## Switching it on

1. Merge `cr/s2-fine-print` through the normal gate. Nothing else is needed for the sandbox: the key is already set.
2. **Upload button:** /s2 needs a "card" picker in `frontend/app/s2/S2App.tsx`, like the statement one. It reads the image, sends it to
   `/api/agent/s2/card-image`, then sends "Add this card" with the `card_image_ref`. Until then, cards are added by name.
3. **Which cards can be answered:**
   - **the first reads, read 10 Oct from the issuers' own Guides to Benefits:** each is used only after a Kanoe person accepts it on
     AgAPI's accept surface (`/fineprint/review`, opened by a one-time link);
   - **the demo cards** ("Example Bank", a labelled test fixture, not a real bank) are accepted already.

## The 30-second demo (test mode)

| Say (on /s2) | She does | On screen |
|---|---|---|
| "Add my Example Bank Travel Visa." | `add_card` | "Added: Example Bank Travel Visa · Visa — no number kept." |
| "Can I rent a car in Ireland on it?" | `card_cover` | "Your Example Bank Travel Visa's terms (read 2026-10-10) say: "Excluded countries: Ireland, Israel, Jamaica." So: no, as the terms state it. Source: …" |
| "What if my bag is delayed?" | `card_cover` | the baggage-delay sentence quoted: more than 6 hours, up to EUR 300 per trip |
| "Add my Everyday Mastercard too. Which card for a $400 rental in Miami?" | `add_card`, `which_card` | "Information from your cards' own terms. You decide." Travel Visa: 0% FX, primary rental cover quoted · Everyday: 3% FX ≈ $12 |

**What not to claim:**
- **Coverage:** never "you're covered" without the quote. The answer is the terms' sentence.
- **Advice:** a card ranking is information about each card's own terms, not advice. No card is "recommended".
- **Reality of the demo bank:** Example Bank isn't a real bank. Its pages say so.
