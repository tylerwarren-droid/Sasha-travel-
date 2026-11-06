# Sasha 354 · a reply means what is pending NOW, from ONE record

FROZEN BETA LIST: SME demo. This ticket follows the NO PATCHES rule.

## What was seen (Sasha 352's proof, mailbox 1774)

1. A pick on a flight whose earlier choice was waiting for payment failed in the store (AlreadyRecorded). Sasha said "still waiting for payment" and drew no card.
2. "Yes", with nothing waiting for a yes (a payment already under way), made the model search flights again.

**Cause:** nothing said what a reply answers. The model guessed, and the store refused a second choice written over a payment.

## The one record

`s2_memory`'s `pending` (Sasha 349's one conversation record) is written by the turn that made it (`fold`):

| Kind | Made by |
|---|---|
| yes (trip) | a read-back waiting for the yes (hold_booking) |
| yes (venue) | the existing "hold" (hold_venue) |
| pick | a new pick waiting for "keep or switch?" |
| question | her latest question |

**The LATEST turn decides:** a question asked after a read-back is what a "yes" answers. The yes, once given, is no longer pending.

`agapi/pending.now(account)` is the one reader. It checks the record against what's live (a read-back still in its 15 minutes, the pick fresh), and reads a payment under way from the basket itself, never copied.

## Read before any model step (`app/agent/sasha.turn`)

**A bare yes:**
- a trip read-back → `book` with their words, by code;
- a venue read-back → `book_venue`, by code;
- her question → the conversation, as ever;
- a pick waiting → its question again, on its card;
- a payment open → "Nothing is waiting for a yes — your payment €X for … is still open. Tap Pay to finish it." on its card [Pay];
- nothing → "Nothing is waiting for a yes right now — what would you like to do?".

It is never a new search.

**"Keep the earlier one":** the pick is dropped, and the earlier payment stays (its card).

**"Switch to the new one":** `choose_offer {offer_id, switch}`. The earlier payment is closed the basket's own way (`basket_book._supersede`: expired at Stripe, its items cancelled, never paid twice), then the new one is chosen.

**A pick** (`choose_offer` → `_pick_against_payment`):
- the same flight already waiting → that payment, said;
- an earlier choice of that flight waiting → its card and ONE question: "Your earlier pick (…) is waiting for payment. Keep it, or switch to …?"

Nothing is written over a payment.

**Every pending item has ONE card,** from Sasha 352's table:
- pending_payment → [Pay];
- choice → [Keep it] [Switch];
- held → [Yes, book it].

S2 and S1 show the trip card; WhatsApp shows the same as taps.

## Tests

`backend/tests/test_s354_pending_now.py`: the record (the latest turn decides); the reading; the pick (card, question, switch, the same flight); the turn ("yes" with nothing pending is said by code, with no model and no search; with a payment its card; to a read-back, `book` by code; to her question, the conversation).
