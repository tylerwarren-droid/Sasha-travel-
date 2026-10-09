# S2's front door: project.kanoe.ai/s2

*Sasha 221. S2 is Sasha as a personal concierge on a phone. Its public name is just "Sasha". S1 (/next) is unchanged.*

## What /s2 is

**Pages and routes**
- **Route:** `/s2`. It is built phone-first (390×844) and works on a desktop.
- **Installable:** it's a PWA, via `app/s2/manifest.webmanifest`. On an iPhone: Share → Add to Home Screen.
- **Sign-in:** the same 6-digit email code as everywhere else (`/sign-in?next=/s2`).

**Screens**
- **Home:** the greeting ("Hey there — what can I do for you?"), a big mic and a text box.
- **Conversation:** cards in line with her words:
  - venue photo cards, with Choose;
  - the read-back ("Ready to book", "Ready to send · on your yes");
  - Booked;
  - Add to your calendar (Google / Outlook / Apple);
  - the email card (Sent / Kept here · not sent);
  - Pay here.
- **Activity tab:** what she did today, each row with what it was and its reference.

**Voice and look**
- Voice is Deepgram: the mic in, her voice out. There is no avatar or video call on /s2.

**How S2 mode is chosen**
- Only by the `/s2` page. Its proxy (`/api/s2-agent`) adds the header `x-sasha-surface: s2`.
- `/next` never sends it, so everything else stays S1.
- With that header, the backend gives her:
  - S2's own opening lines (`backend/app/agent/s2.py`, `S2_WHO`);
  - S2's tool set (`S2_TOOLS`): places and their bookings, email, the calendar, WhatsApp, Activity, payment, and trips.

## What it shares with S1, and what is its own

| Shared, unchanged | S2's own |
|---|---|
| The agent: `/api/agent/turn`, the same model and tools code | `app/s2/*` (page, layout, manifest), `app/api/s2-agent/route.ts` |
| "How she talks" and every rule after it in the system text | `S2_WHO`, her opening lines |
| Yes-binding, read-back, guard, idempotency, Activity record | `S2_TOOLS`, the tool list she is given |
| `VoiceButton`, `PayHere`, `untag` (imported, not edited) | The S2 demo setting (below) |
| Payments, the webhook settle, the calendar links, Sasha's email address | Two S2-only behaviours (below) |

**The two S2-only behaviours**
- **A repeat search re-shows the cards.** If the same search runs again within 20 minutes (a reload, a rehearsal), it re-shows the SAME stored cards. On S1, the repeat returns no cards ("they're already on screen"). That's fine in one page's life, but a fresh page then shows none. S1 is left as it was.
- **The demo setting reaches the stand-in without a card id.** It applies when she names a card without passing its id.

**Isolation proof (Sasha 221)**
- **Zero diff** to `frontend/app/next`, `frontend/app/components`, `frontend/lib` and `frontend/app/api/sasha-agent`.
- **Same S1 output:** the S1 fingerprint (a fixed S1 conversation's tool calls and output, scripted model) was captured at 10471df and is byte-identical after every 221 commit.
- **Full gate green:** Places replay only, 0 live.

## The S2 demo setting (founder only, /s2 only)

**Who has it**
- On the founder's account, a restaurant or spa booked on /s2 goes to **our test venue**. So a demo reaches "Booked", with a reference, and nothing real is contacted.
- On `/next` the founder's account is exactly as before: real restaurants and spas.
- `SASHA_S2_DEMO_ACCOUNTS` (Railway) can list a scratch fixture account for a rehearsal. It is empty after Sasha 221.

**What the screen shows**
- Nothing on screen says "test" or "stand-in". The card shows the real place's name and photo; the booking goes to our test venue.
- **Say so if asked.** In demo mode, "Booked" means our test venue took it, not the restaurant. Don't let a VC believe the real place has a table.

**Email**
- An email still goes out for real from Sasha's own address on the founder's account (the allow-list). Use an address you control for "Marta".

## The 2-minute VC demo on /s2

**Before you start**
- Open **project.kanoe.ai/s2** on the iPhone (or the home-screen icon), already signed in. Volume up.
- Google Places must have quota left (see `s2-phone-demo.md`, "Before you start").

| # | Say or tap | What appears | Point out |
|---|---|---|---|
| 0 | Open | "Hey there — what can I do for you?" and the mic | "A concierge, not a travel app." |
| 1 | *"Book me dinner tomorrow near Sol for two at nine, then email the plan to Marta at ‹your address› and put it in my calendar."* | Five photo cards near Sol; she names two or three | "Only what's on screen. Opening hours, never a promised table." |
| 2 | Tap **Choose** | One read-back: the route, the day, the time, the name. "Shall I…?" | "Nothing has happened. Only my yes sends it." |
| 3 | *"Yes, go ahead."* (if she reads it back once more: *"Yes, book it."*) | **Booked** with a reference, then **Add to your calendar**, then the email to Marta on its card | "One tap for the calendar. The email waits for my yes too." |
| 4 | *"Yes, send it."* | The email card turns to **Sent** (Sasha's own address) | "She emails from her own address; replies come back to her." |
| 5 | *"Also a weekend in Lisbon from 20 November, two of us, from Madrid."* then *"Book it."* | The trip read-back: flights and hotel, €… all in | "The hotel price is labelled an estimate." |
| 6 | *"Yes, go ahead."* | **Pay here**: Apple Pay / Google Pay on this phone | "The pay step happens here, on the same phone." *(Don't pay in a demo.)* |
| 7 | *"What have you done for me today?"*, then the **Activity** tab | Her list from her records; Activity rows with references | "Every act, with its proof. She reads from the record." |

**If it misbehaves**
- **No cards:** the Places quota.
- **"Kept here · not sent" on the email:** the account isn't on the email allow-list.
- **The Pay card opens Stripe's page instead of paying in place:** embedded pay is waiting on the two Stripe values (Sasha 221 B).
