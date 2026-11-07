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

## Found while proving it, and fixed

1. **A turn run outside the web routes** (the voice pathway, the gate's loops) wrote nothing pending, so a read-back's "Yes." met "nothing is waiting". The turn itself now notes what's pending (`s2_memory.note_pending`, the same step the routes' fold uses).
2. **A pending item's card drew nothing on /s2.** A trip render with no proposal cards is now the trip's ONE card.
3. **The keep-or-switch question carries each choice's own figure.** Without the figures, her words gave the waiting payment's total ("about €29") for a €65.19 flight.

**Also:** `test_s259`'s fixture dates fell into the past on 7 Nov (failing the gate's T41). They are now relative to today.

## Live proof (7 Nov, project.kanoe.ai, the test organiser, phone; no card entered)

**"yes" with a payment open:**
- "Nothing is waiting for a yes — your payment €28.71 for Transavia France MAD → ORY is still open. Tap Pay to finish it."
- The trip card shows [Pay] · [See the whole trip].

**A new pick over that payment:**
- "Your earlier pick, American Airlines Madrid to Orly at 18:34 on 25 November (€65.19), is still waiting for payment. Do you want to keep it, or switch to Transavia France at 19:55 (€28.71)?"
- [Keep it] · [Switch].
- Keep it → "Kept — your payment … is still open" + [Pay].
- Switch (the earlier run) → the new flight chosen; the earlier payment closed.

**"yes" with nothing waiting** (a new chat, a Rome flight chosen and nothing read back): "Nothing is waiting for a yes right now — what would you like to do?". No search.

**Book it → Yes, book it → the Pay card** (Stripe TEST embedded), as in Sasha 352.

**The gate** (deploy 4269282c, on recorded replies): PASS; the voice loops' read-back "Yes." books by code.

**WhatsApp:** the same turn, and the same card as taps ([Pay] · [Keep it] · [Switch]), are held by the unit tests. The test organiser has no WhatsApp linked, so nothing was sent.
