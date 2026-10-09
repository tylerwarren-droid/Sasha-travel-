# AgAPI for partners · 3: the pricing page (draft)

*EU 211 · 9 Oct 2026. **Every number marked ⟨placeholder⟩ is Tyler's to set** (Part 4 "Only Tyler decides" 1). The
structure follows the contract's cost classes (`operations.json` `cost_class`), so the bill can be computed from
`usage_record`s that already exist.*

## The page

### Pay for what acts, not for looking

| What you call | Cost class | Units | Example operations |
|---|---|---|---|
| Account, status and proof | **free / read** | **0** | `acts.status`, `approvals.status`, `evidence.get`, `evidence.verify`, `activity.list`, `messages.replies`, `calendar.add_event`, `users.*`, `webhooks.*`, `usage.get` |
| Search | **search** | **1** | `travel.find_flights`, `travel.find_stays`, `venues.find_venues` |
| A message to a person | **message** | **1** | `approvals.request`, `messages.send_email`, `messages.send_whatsapp` |
| Preparing an act | **act_prepare** | **2** | `trip.hold` (re-checks every item at the provider and builds the read-back) |
| An act | **act** | **5** | `trip.complete`, `trip.cancel` |

**Never charged:**
- a **replay** (the same idempotency key);
- any error of ours or the provider's being down;
- a refused request.

**Charged:** a successful call, and `upstream_refused` on an act (the provider answered "no").

**Test mode:** metered and shown, **never billed**.

### Plans

| | **Test** | **Partner** |
|---|---|---|
| Who | anyone we've given a test key | partners going live |
| Price | **free** | **⟨€0.05⟩ per unit**, billed monthly |
| Included | **⟨10,000⟩ units / month** | **⟨20,000⟩ units / month** in a **⟨€500⟩ / month** minimum |
| Rate limit | **⟨60⟩ requests / min** | **⟨600⟩ requests / min** |
| Mode | test only (captured messages, fixtures, Stripe test) | test + live |
| Support | email, 2 working days | a named contact, 1 working day |
| Webhooks | 2 endpoints | 2 endpoints |
| Budget cap | the included units, a hard stop (402 `budget_exhausted`) | your monthly cap; an email at 80% |

### What a typical flow costs (at the ⟨€0.05⟩ placeholder)

| Flow | Calls | Units | ⟨€⟩ |
|---|---|---|---|
| **A booked flight:** find → hold → approval link → complete → status + proof | 1 + 2 + 1 + 5 + 0 | **9** | ⟨0.45⟩ |
| **A booking the user didn't approve:** find → hold → link, then it expired | 1 + 2 + 1 | **4** | ⟨0.20⟩ |
| **An email sent on the user's behalf:** send_email (read-back) → approval → send | 1 + 1 | **2** | ⟨0.10⟩ |
| **A cancellation:** hold (cancel read-back) → link → cancel | 2 + 1 + 5 | **8** | ⟨0.40⟩ |
| **Add to calendar, status checks, proof checks** | any | **0** | 0 |

**Not in the price:**
- the **booking's own price** (the fare, the room), which the user pays to the provider through the payment link;
- **provider fees passed through at cost**, shown on the read-back before the yes.

## Notes for Tyler (not on the page)

- **Why per unit, and why acts cost 5×:** the expensive, valuable thing is the guaranteed act (a re-check, the
  approval, idempotency, the evidence). Searches stay cheap so partners don't ration them.
- **The minimum** pays for the named contact and live-mode review. **The test tier** must stay free, or nobody gets
  to step 4 of the journey.
- **The unit values are the contract's placeholders** (Part 4 M2). Changing a class's units is a pricing change, not
  a contract change; the cost class itself is frozen per operation.
- **Open:** the live-mode payment model (who's merchant of record) is separate from this page.
