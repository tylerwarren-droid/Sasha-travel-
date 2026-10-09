# Run the DIVE demo yourself

*CR 66. Test mode: nothing in this demo sends a real message. Every supplier is ours, and in test mode their answers
are played from the test drawer.*

## Before you start

1. Open **https://agapi-dive-demo-production.up.railway.app/start**.
   - The first time, it asks for the console token. It's in Keychain Access: search for "DIVE console token".
   - The page remembers you for 12 hours.
2. Click **Reset demo**. The page says "✓ Reset. The console is empty and ready for step 1."
   - Do this before every run. It empties the console (suppliers, packages, bookings, keys, activity). The operator
     stays "Blue Kyma Diving (demo)".
3. Use two screens:
   - **Left screen:** the console. Every link on the start page opens in a new tab.
   - **Right screen:** the customer's booking page, then their phone.

Each step below is also on the start page, with its **Open** button. You never need to hunt through pages.

## The ten steps (5 minutes)

| # | Time | Open | Do | Say |
|---|---|---|---|---|
| 1 | 0:00 | (nothing) | Just talk. | "Most of the world's travel isn't on an API. A dive shop, a boat, a taverna take bookings on WhatsApp and paper. An operator who packages them has no API to sell through. AgAPI gives them one." |
| 2 | 0:30 | [Find suppliers](https://agapi-dive-demo-production.up.railway.app/console#find) | Click **Find suppliers on my site**. Five businesses appear, each quoting the sentence it came from. **Confirm** four. **Not ours** on Rival Boats. On each one: **Use …**, then **Send verification**. | "Blue Kyma's suppliers have no APIs. AgAPI reads his website, lists the businesses he works with, and he confirms them. Nothing is sent to anyone he didn't confirm." |
| 3 | 0:55 | [Test drawer](https://agapi-dive-demo-production.up.railway.app/console#drawer) | Click **Supplier: YES** for Aegean Boats and for Kyma Gear. (On rehearsal day this is Jon's phone instead.) | "In test mode we can play the supplier. The boat just agreed to receive bookings, on WhatsApp." |
| 4 | 1:15 | [His docs](https://agapi-dive-demo-production.up.railway.app/o/blue-kyma/docs) | First, in the console: **Packages → Create "Discover Mykonos" → Publish**. Then open his docs: titled "Blue Kyma Diving API". | "One click, and he has an API: his packages, his name, his keys. A travel app or an OTA can sell his dives tomorrow." |
| 5 | 1:45 | [The booking page](https://agapi-dive-demo-production.up.railway.app/o/blue-kyma/book) | Right screen: a **Tuesday**, 09:00, **4** divers, a name and a phone number, then **See the read-back**. | "The customer sees every leg, who provides it, and how it'll be confirmed." |
| 6 | 2:10 | [The customer's phone](https://agapi-dive-demo-production.up.railway.app/start/phone) | Opens the newest link the customer's phone received. Tap **Yes, book it**. | "And says yes once." |
| 7 | 2:30 | [Test drawer](https://agapi-dive-demo-production.up.railway.app/console#drawer) | **Supplier: YES** on Kyma Gear, **ΝΑΙ** on Aegean Boats. Then the **Bookings** tab: every leg turns ✓, then **✓ Confirmed**. | "Three suppliers, three channels: a web form, an email, a WhatsApp. Each answer is the supplier's own. One booking, confirmed by businesses that have never seen an API." |
| 8 | 3:30 | [Proof](https://agapi-dive-demo-production.up.railway.app/start/proof) | Opens the newest booking's proof. Click **Verify**: "✓ The record matches." | "Every leg has proof: what we sent, what they answered, when. If there's ever a dispute, the operator has the record." |
| 9 | 4:00 | [Test drawer](https://agapi-dive-demo-production.up.railway.app/console#drawer) | Click **Prepare the Thursday booking**. Back in the drawer: **Supplier: NO, full** on the boat. Bookings shows **✕ Couldn't confirm** and one button: **Offer another time**. | "When a supplier says no, the customer hears it straight, nothing is charged, nothing half-booked, and the operator gets one button to offer another time. If WhatsApp were down, AgAPI would say 'couldn't reach them', never 'sold out'." |
| 10 | 4:40 | [Activity](https://agapi-dive-demo-production.up.railway.app/console#activity) | Just talk. Every step is listed, each with its proof. | "AgAPI gives an API to businesses that don't have one. DIVE is the operator's own API on top of it." |

## If something looks wrong

| You see | What it means | Do |
|---|---|---|
| Step 6 says "Nothing on the customer's phone yet" | The customer hasn't reached the read-back. | Finish step 5 (**See the read-back**), then open step 6 again. |
| Step 8 says "No booking has proof yet" | Not every supplier has answered. | Finish step 7: both answers in the drawer. |
| The phone page says "This link isn't active" | It was already used, or it is more than 15 minutes old. | Do step 5 again for a fresh link. |
| A leg says "answer by …" and waits | It's quiet hours for the suppliers (22:00 to 08:00, Mykonos time). The request goes out at 08:00. | Rehearse in Mykonos daytime. |
| Anything else odd | — | **Reset demo** on the start page and start again from step 2. It takes a second. |

## What not to claim

- **Real suppliers or partners.** There are none. Say "test mode, our own phone and form".
- **Payments.** The total is shown, never charged.
- **Instant confirmation by WhatsApp or email.** It's "within 2 hours", said honestly.
- **Coverage beyond the demo.**

## Also useful

- AgAPI's public docs (what a partner reads): https://agapi-sandbox-production.up.railway.app/docs
- Blue Kyma's website (ours, fake): https://agapi-dive-demo-production.up.railway.app/fake/blue-kyma
- Real WhatsApp to Jon's phone and a real gear email are **off** until rehearsal day. See
  [switch-on-list.md](switch-on-list.md).
