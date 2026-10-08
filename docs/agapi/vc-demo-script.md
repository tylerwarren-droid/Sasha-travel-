# The AgAPI demo: a 2-minute script for Tyler

**Where:** https://agapi-sandbox-production.up.railway.app/demo, on a laptop, in full screen.
- The buttons are on the left; the traveller's phone is on the right.
- Everything is **test mode**: no real flight is booked, no money moves, no venue is contacted.

**Before you start:** press **↺ Reset** once. The card should say *"Ready. One traveller, one phone, nothing booked."*

The button to press next is always the **dark** one, and each step takes about 10 seconds.

| # | Click | You say (about one breath each) | What they see |
|---|---|---|---|
| — | **↺ Reset** | "Any app or agent can book through us. Here's what happens when it does." | "Ready." |
| 1 | **Find** | "The partner's agent asks for flights. These prices come straight from the airline." | three flights, a green check |
| 2 | **Hold** | "Before anything happens, we write down *exactly* what will be done: these words, this price. That text gets a fingerprint." | the read-back lines, "any change voids the yes" |
| 3 | **Ask for approval** | "Now the person themselves, on *their own phone*, gets the request. Opening it shows it; it can't approve anything by itself." | an SMS bubble, then the approval page on the phone |
| 4 | **"Yes — what are my cancellation terms?"** | "This is where other agents go wrong. A 'yes' that's really a question is **not** a yes. Refused." | **red**: "a question is never a yes" |
| 5 | **"Yes, book it."** | "A clear yes, in a separate turn, from the person. It's valid for 15 minutes, for this booking only." | **green** bubble, two green checks |
| 6 | **Pay (test)** | "Payment happens on their phone. We only book *after* they've paid, and until then we say 'not booked yet'." | the phone shows **Paid** |
| 7 | **Confirmed + proof** | "Booked, in the airline's own words. And here's the receipt for the whole chain, the yes, the payment, the airline, which anyone can verify. Change one letter and it fails." | the reference, two green checks |
| 8 | **Cancel** | "Cancelling is an action too, so it needs its **own** yes. The booking's yes can't be reused." | refunded, two green checks |
| 9 | **Source down** | "And when a supplier is down, we say so. Never 'no results', because that's how agents make things up." | a red "Places: unreachable", then a green "reported as an outage" |

**Close with:**

> "Find, hold, ask the person, act once, and prove it. That's AgAPI, and it's live in our sandbox for partners today."

**If something looks stuck:**
- Press **↺ Reset** and start again from Find; it takes one second.
- The phone fills itself in after Pay. If it hasn't shown *Paid* yet, wait two seconds before pressing **Confirmed + proof**.
- Pressing Confirmed too early just says "Not confirmed yet": that's the honest answer, not an error.

**What not to say:**
- "It's live with airlines." It's **test mode**, with recorded Duffel test fares and a simulated Stripe test payment.
- "No agent ever acts without a yes." Say "**our** API never acts without the person's yes."
