# The fine-print demos on /s2 (two × 30 seconds)

*CR 75 · branch `cr/s2-fine-print`. Test mode: AgAPI sandbox. Every line below is what the live run said on 10 Oct 2026.*

**Before the demo:**
- The demo's bank ("Example Bank") and rental company ("Example Rentals") are AgAPI sandbox fixtures. **Neither is real, and their pages
  say so.**
- The demo photos are in `docs/sasha/demo-fixtures/accident/`. Each says "DEMO PHOTO — not a real accident". Put them on the demo phone.
- Sign in on /s2 with the demo account. Add the cards once: say **"Add my Example Bank Travel Visa"** and **"Add my Example Bank
  Everyday Mastercard"**. "My cards" then shows both, "terms read 2026-10-10".

## Demo A · "Which card for the rental in Lisbon?"

| Say (on /s2) | She does | On screen |
|---|---|---|
| "Which card for the rental in Lisbon? It's Example Rentals, a week." | `rental_cover` (PT, Example Rentals, 7 days) | **The counter card**, "Pay with your Example Bank Travel Visa" |

**What she says:** *"Decline Collision Damage Waiver (CDW): your Example Bank Travel Visa's terms say it covers damage and theft as
primary cover when you decline it, and this country isn't among the excluded countries they list."*

**The card**, each line with a **source** link (the sentence, its page, the date read):

| Section | Lines |
|---|---|
| **Decline** | the CDW, as above |
| **Keep** | "Keep the third-party liability the rental includes. Limit: EUR 6,450,000." · "Your card doesn't cover liability." |
| **Optional** | "Optional: Zero Excess Cover (EUR 18 per day) removes the excess of EUR 1,200." · "Your card's own limit for rental damage: EUR 50,000 per rental." |
| **Bring** | the card · "International Driving Permit: not required." · the licence rule · "Deposit: EUR 1,500." |
| **If something happens** | "Report an accident to Example Rentals within 48 hours." · "Notify the card's claims administrator within 60 days." · "Card claims line: +34 900 000 000." |

**At the bottom:** *"From your card's terms and the rental company's own terms for this country, each line quoted. You decide what to buy
at the counter."*

**Variation:** "and in Ireland?" → that card's terms exclude Ireland, so there's **no** decline line.

## Demo B · "I've had an accident at a roundabout in Lisbon"

| Say / tap | She does | On screen / she says |
|---|---|---|
| "I've had an accident at a roundabout in Lisbon. It's the Example Rentals car." | `accident` starts | **Accident · Safety** (red): *"Is anyone hurt?"* with **No / Yes / Not sure**. Nothing else until it's answered |
| tap **No** | `accident` "no" | *"The official rules for Portugal aren't read at source yet, so I won't quote them. Stay at the scene, keep everyone safe, and exchange details with the other driver."* |
| tap **Done** | photos | the 9 guided shots; tap **Take** on four and pick the demo photos; each turns ✓ (sealed + fingerprinted) |
| tap **Done with photos** ("it was 14:00 at Rotunda do Marquês, plate AA-00-ZZ") | the statement | *"Here's the statement with the facts filled in. The circumstances boxes and the sketch are yours to fill with the other driver. Don't sign anything you disagree with — and I never sign."* The form is the **Declaração Amigável de Acidente Automóvel**. "Yours to fill: circumstances boxes (1–17), the sketch, the signature." |
| tap **Done** | the clocks | "Report it to the rental company within 48 hours · by 12 Oct 14:00" · "Notify your card's claims administrator within 60 days · by 9 Dec" · "Portugal's own deadline: its official rules aren't read at source yet — not shown." Each has a source link |
| tap **Notify the rental company** | `accident_notify` | **The read-back:** to accidents@example-rentals.example (the address in its terms); date, time, place, vehicle, injuries; boxes, sketch and signature left to the drivers; 4 photos with their fingerprints; their 48-hour deadline, quoted. She asks |
| "Yes, send it." | sent (sandbox: captured) | *"Sent to Example Rentals. Next: your card's insurer — I'll read that claim back too, and it goes on your yes."* |
| tap **File the card claim** → "Yes, file it." | `file_claim` | **The claim read-back:** Example Assistance, the clause quoted ("This benefit is primary coverage and covers damage to and theft of the rental vehicle."), the 4 photos and the statement attached, what's still to follow, the 60-day deadline quoted. Then **filed** |
| "What's the status of my claim?" | `claim_status` | "Claim · filed": the deadlines and **Still needed:** the card statement line, the rental agreement, the damage report, the repair invoice, each with where to get it |

**To show the safety gate:** answer **"Not sure"** instead of No. She says *"Call 112 now."* with a red **Call 112** button. Nothing else
is offered until **"Help is on the way"**.

**To show the hand-off:** say "the other driver says it was my fault". She says *"This needs a lawyer or your insurer's legal team. I can
find one for you, and I'll keep doing only the paperwork."*

## What not to claim

- **Covered:** never "you're covered" or "you don't need insurance". She says what each card's terms say, quoted.
- **The rules shown:** Portugal's are **not shown** (ASF's site can't be read by our reader). Spain's, France's, Germany's and Italy's
  are read at source and appear after a Kanoe check.
- **Filing:** in test mode nothing reaches anyone. The emails are captured.
- **Fault and signatures:** Sasha never fills a fault box, never signs, and never argues fault.
