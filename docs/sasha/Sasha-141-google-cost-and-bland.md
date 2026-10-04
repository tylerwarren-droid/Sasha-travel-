# Sasha 141: the Google bill and the Bland balance

*4 Oct 2026.*

## 1. What is consuming the Google credit

**Source:** Cloud Monitoring `serviceruntime.googleapis.com/api/request_count`, project `applied-diligence-site-project`,
last 19 days. Script: `s141_counts.py` in the session scratchpad.
- There is no billing export to BigQuery, so gcloud cannot give euros per SKU.
- The euros below are request counts × Google's list prices for Places API (New): Enterprise Place Details $20 per 1,000,
  Enterprise Text Search $35 per 1,000, 1,000 free a month per SKU.
- The invoice is the authority.

| API method | Requests, 19 days | Rough cost |
|---|---|---|
| **Places · GetPlace (Place Details, Enterprise: phone, website, hours)** | **8,255** | **≈ $145** after the free 1,000 |
| Places · SearchText (Enterprise) | 304 | inside the free 1,000 (≈ $11 at list) |
| Cloud KMS Decrypt / Encrypt | 271 / 22 | cents (+ $0.06/month per key version) |
| Routes · ComputeRoutes | 19 | cents |
| Gmail, Calendar | ~300 | free |

**The money is GetPlace, and it isn't spread over 19 days.**

| Day | GetPlace calls |
|---|---|
| 1 Oct | 1 |
| 2 Oct | 19 |
| 3 Oct | 2,998 |
| 4 Oct (so far) | 5,243 |

- **Hourly shape:** a flat ~110 calls an hour, all night, every night, with ~330 an hour on top during the daytime
  rehearsals.
- **What this means:** the €6.49/day figure is 19 days averaged over two expensive ones. At today's rate (~$100/day) the
  credit would not have lasted to 25 Oct.

## 2. The cause: a loop, not the demo

1. A phone booking's venue name is never stored (Sasha 64). Its receipt re-reads the Google listing: one Enterprise Place
   Details call.
2. The proactive watchers run every 60 s. Each tick read the upcoming bookings with their names, at least twice:
   - `tick`, plus `no_reply_offers` (switched on in Sasha 130);
   - invitations' watcher too.
   That meant one receipt, and so one Google call, for every upcoming phone booking on every read.
3. The founder's account has 11 active phone bookings from the rehearsals. Together that is ≈ 2 calls a minute.

## 3. Cuts

**Implemented (safe, no capability removed)**
1. **The watchers scan without names.** `_upcoming(account, names=False)` is used by:
   - the tick;
   - the no-reply offers;
   - the invitations watcher, which reads status only.
2. **Names are still re-read where they're needed:**
   - for a message actually sent: the status re-read at the send, and the morning brief's items;
   - for a leave-now route that has no address;
   - everywhere a guest asks (receipts, cancel list, mailbox).
3. **Test:** `tests/test_places_cost_s141.py`. An hour of ticks over 4 phone bookings reads 0 receipts; a guest asking
   still gets the real name.
- **Expected effect:** the ~110/hour background goes to ~0. What remains is real use: a search ≈ 1 Text Search, and a
  pick ≈ 1 Details call.

**Proposed, not done**
- **Field masks: no saving.** Phone, website and hours are what the cards and the ladder need, and they put Details and
  Search in the Enterprise SKU. Dropping them would remove a capability.
- **Caching listings: not allowed.** Google's terms allow storing place IDs only, and we already store only those.
- **Prewarm: affordable.** ≈ 14 searches and ≈ 40 Details calls, about $1 per run.
- **Budget alert (founder's action):** Google Cloud console → Billing → Budgets & alerts, at €30/month on the billing
  account, so a loop like this is caught on day one, not day 19.

**To verify after deploy:** re-run `s141_daily.py` hourly. Night-time GetPlace should read ≈ 0.

## 4. Bland

- **The balance, read just now:** `billing.current_balance = -0.087` (≈ −$0.09). Auto-refill is not set
  (`refill_to = None`), and there is no plan.
- **Effect:** with a negative balance, calls will be refused. The Vietnam/Madrid demo call on Wednesday needs credit
  before then.

**To top up (the founder, before Wednesday)**
1. Sign in at app.bland.ai with the account that owns the Railway `BLAND_API_KEY`.
2. Open Billing (account / settings menu) → add credits. **$20** covers the demo with a wide margin: a 2–3 minute call is
   well under $1.
3. Optional: switch on auto-refill (e.g. refill to $20 when it falls below $5), so a rehearsal can't strand it again.
4. Tell this tab; it re-reads the balance and places one call to the test line to prove it.

*(The menu wording is Bland's usual dashboard, not seen from here: only the API was read.)*
