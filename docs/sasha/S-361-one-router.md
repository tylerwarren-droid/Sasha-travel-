# Sasha 361 — ONE product router decides which product every WhatsApp message is for

**Found** (EU 282 N7, mailbox 1848): on 9 Nov at 14:04:36Z, "do 1-3 on Halfords" from an AD user with an open case was answered by Sasha ("Who's going?"). The old router read word lists (`_INVESTIGATION`, `_DD`, `_CASE`, `_CLAIMS`, `for_sasha`) plus the current space, and neither matched AD.

## The router — `products/tools.route`

It sits beside the registry the Menu reads (Tyler, 9 Nov). It works over the number's **roles**:
- **Sasha's** role is always there: a linked guest is hers.
- **AD's** role is AgAPI's inbound `conversation_role` (CR 180a, on every inbound). It is passed through untouched by `agapi/venue_submit` → the webhook → the turn.

The order:
1. An explicit keyword or Menu tap wins (a tap reaches the router as its tool's keyword) and is recorded as their choice.
2. Otherwise, the product they last **chose**. This is the router's own record, written only by `route`.
3. Otherwise, for a number with both roles, ONE question in the registry's words: "Is this for 🔍 Due diligence or ✈️ Travel?", with two taps. The tap routes the words they had sent.

A Sasha-only number is unaffected. A message routed to AD goes to AD's door (`diligence.hand_over`) and never reaches Sasha's brain or her group tools.

## Deleted as sources

- `products/router.py`: the word lists, the 15-minute `ad_at` window, `route_ask`, and AD's case-name reading (`venue_submit.ad_cases`).
- AD's entry in `product_turn`'s keyword loop.
- `current_space` and the pending question as AD's source.
- 349's "a reply answers the tool that spoke last", for AD.

**The trade-off, said:** a reply after Travel speaks goes to the product they last chose, until they say "sasha" or tap ✈️ Travel.

## Proven (9 Nov, production's code 79c40c6a, Railway 267ca415)

The real signed webhook, the sandbox number, fictional numbers. AgAPI's inbound was stood in with CR 180a's shape (agapi-live is never called from here). The outbound was recorded, not sent.

| Case | What happened |
|---|---|
| 1 · an AD user who chose AD ("diligence"), then 6 hours of silence: "do 1-3 on Halfords" | → AD; Sasha's brain not called |
| 2 · a Sasha-only number: "do 1-3 on Halfords" | → Sasha's brain; nothing to AD |
| 3 · a number with both, no keyword, no prior choice | → "Is this for 🔍 Due diligence or ✈️ Travel?" with two buttons; nothing to either |
| 4 · tap 🔍 Due diligence, then "and 4 as well" | → "do 1-3 on Halfords" to AD, then "and 4 as well" to AD; Sasha's brain never called |

The live log has been clean since the deploy.

**Noted, not changed:** after "diligence" alone, the Menu attached is the top-level tools list (AD's own replies carry AD's menu from AgAPI).

## Tests

- `tests/test_s361_one_router.py`: the rule; the three webhook cases; one source (`router.py` gone, no word lists / window / spoke-last, the record written only by the router).
- The gate's T90 runs it. `test_s315` / `test_s318` (the deleted by-meaning router) were removed.
- Suite: 3391 tests; the only failures are the 2 baseline ones.
