# AgAPI for partners · 2: the docs site

*EU 211 · 9 Oct 2026. The structure, and what each page must say. It's generated where it can be: the operation
pages and the MCP manifest come from `docs/agapi/v1/operations.json` + the schemas, as the sandbox's `/openapi.json`
already does. **One source; the docs can't drift from the contract.***

## Table of contents

```
1. Start here
   1.1 What AgAPI does (one screen + the 2-minute demo)
   1.2 Quickstart: your first booking in 5 minutes (curl · TypeScript · Python)
   1.3 Test mode and live mode
2. Concepts (one page each, ≤ 1 screen, a diagram + a rule list)
   2.1 The envelope: every request, every answer
   2.2 The read-back: what your user approves, line by line
   2.3 Your user's yes: approvals, channels, expiry, what voids one
   2.4 Evidence: proof you can verify yourself
   2.5 Idempotency: never twice
   2.6 Outages are never "no results"
   2.7 Untrusted text: what came from the outside world
3. Operations (one page per operation, generated)
   3.1 Find        travel.find_flights · travel.find_stays · venues.find_venues
   3.2 Act         trip.hold · approvals.request · trip.complete · trip.cancel
   3.3 Messages    messages.send_email · messages.send_whatsapp · messages.replies          (v1.1)
   3.4 After       acts.status · approvals.status · activity.list · calendar.add_event     (activity, calendar: v1.1)
   3.5 Proof       evidence.get · evidence.verify
   3.6 Account     users.register · users.verify_destination · usage.get · webhooks.register · webhooks.revoke
   3.7 Test only   sandbox.simulate_approval · sandbox.messages · sandbox.simulate_reply   (simulate_reply: v1.1)
   3.8 The Keep    keep.put · keep.list · keep.use · keep.delete · keep.activity              (v1.2)
4. Errors: all 36 codes, grouped, each with "what to show your user"
5. Webhooks: events, payload, signature, retries, testing
6. Test switches: magic refs and sandbox destinations
7. For AI agents: the MCP manifest
8. Changelog and versioning (1.0 → 1.0.1 → 1.1 → 1.2)
9. Go-live checklist
```

## 1. Start here

- **1.1 What AgAPI does:**
  - **The three sentences:** "Find things your users want. Hold one and show your user exactly what will happen. Act
    only after **their own yes**, once, and keep proof."
  - **The 2-minute demo:** an embed of `/demo`.
  - **Who it's for:** links to the partner types (`04-first-partners.md`).
- **1.2 Quickstart:** `01-partner-journey.md` step 4, verbatim. **Every snippet is run in CI against the sandbox**
  before the page publishes.
- **1.3 Test and live:**

  | | Test | Live |
  |---|---|---|
  | Key prefix | `agp_test_` | `agp_live_` |
  | Money | Stripe test | real |
  | Messages | captured, read via `sandbox.messages` | sent |
  | Venues | fixtures, never contacted | not open |
  | Approvals | real link **or** simulated | real only |

  **Live: not open yet.** The page says so plainly, with no date.

## 2. Concepts: each rule a partner must not get wrong

| Page | The rules on it (from the contract) |
|---|---|
| **2.1 Envelope** | `POST /v1/{operation}`, body = input; headers `AgAPI-Version`, `Idempotency-Key`, `AgAPI-Approval-Id`, `AgAPI-Request-Id`. The answer is **always** `{agapi, request_id, ok, result \| error, trace}`, whatever the HTTP status. Unknown request fields are refused; unknown response fields must be ignored |
| **2.2 Read-back** | `trip.hold` re-checks every item at the provider and returns `read_back.lines`. **Show them verbatim.** The read-back is approvable for **30 minutes** after it's presented |
| **2.3 Your user's yes** | Approvals come only from the user's device: AgAPI's single-use link (SMS, WhatsApp, email), the SDK, or Sasha. **No API key can approve.** A yes must be a **separate action** after the read-back is shown. An approval is usable for **15 minutes**, **once**. It is **void** if the price, the items, the read-back or the intent changes. **Spoken or typed yes:** questions and requests veto it ("Yes, what are the terms?" isn't a yes). v1.1: for a **cancellation's own** read-back, "Yes, cancel it" counts. The rule order (which error you get first) is a table |
| **2.4 Evidence** | Every act yields an `evidence_id` (required when `CONFIRMED`). `evidence.verify` recomputes `body_sha256`; anyone can. **"Booked" is said from `acts.status` or the evidence, never from a webhook alone** |
| **2.5 Idempotency** | A key is scoped to **(account, operation, key)**. The same key + the same input → the same answer, `replayed: true`, **no second charge, no second act**. The same key + a different input → `idempotency_conflict`. Failures that might succeed on retry **release** the key; `outcome_unknown` **keeps it in flight** until `acts.status` resolves it. Keys last 24 h |
| **2.6 Outages** | An unreadable source is **an error, never an empty list**. A partial result carries `coverage` naming what answered. `items: []` means "none" **only** if `coverage.complete` is true |
| **2.7 Untrusted text** | Anything fetched (venue names, reviews, replies) arrives as `untrusted_text {text, source, retrieved_at, instruction_like, truncated}`. **Never pass it to your model as instructions.** v1.1 flags "ignore **your** previous instructions" too |

## 3. Operation pages (generated; one template)

**Each page has, in this order:**
1. **One sentence:** what it does.
2. **Badges:** agent, **cost class + units**, needs an approval yes/no, idempotent yes/no, since version.
3. **Request:** a curl example + a field table (from the input schema).
4. **Response:** an example `result` + a field table.
5. **Errors this operation can return:** each linked to §4, with "what to show your user".
6. **Test it:** the relevant magic refs.

**The v1.1 operations** (shapes in `docs/agapi/v1/schemas/ext/ext.schema.json`, taken from the live sandbox):

| Operation | One sentence | Class | Approval |
|---|---|---|---|
| `messages.send_email` | Sends **one** email from AgAPI's own sending address (never the user's mailbox) to **one** person the user names. The first call returns the exact message as a read-back; it's sent only after the user's yes, **one yes = one send**. Proof: the provider's message id + a hash of the body | message (1) | **yes** |
| `messages.send_whatsapp` | The same, on WhatsApp. Inside the recipient's 24-hour window: the user's own `text`. Outside it: the approved first-contact template with `on_behalf_of` (the recipient is asked whether they want the message). STOP is final | message (1) | **yes** |
| `messages.replies` | Replies received to messages AgAPI sent for this user (`rpl_…`), as **untrusted text** | read (0) | no |
| `activity.list` | Everything AgAPI did for this end user, newest first, from the proof records only: bookings, payments, emails, WhatsApps, replies, calendar, cancellations | read (0) | no |
| `calendar.add_event` | A **confirmed** booking as a calendar file + "Add to calendar" links for Google, Outlook and Apple. Nothing leaves the user's account | free (0) | no |
| `sandbox.simulate_reply` | Test only: the person you messaged answers on WhatsApp (opens their 24 h window; STOP is final) | free (0) | no |

**Also in v1.1:** the webhook event **`message.replied`** (`data.reply_id`; fetch the text with `messages.replies`).

## 4. Errors

- **One table per group:** request · auth · limits · idempotency · approval · upstream · domain · internal.
- **Each row:** code · HTTP · retryable · **what to show your user** · what to do.
- **Generated** from `error-codes.json` (36 codes; v1.1 adds none). The "what to show" column is written once,
  here.

**The ones partners get wrong:**

| Code | Show your user | Do |
|---|---|---|
| `outcome_unknown` | "We're confirming your booking. This can take a minute." | poll `acts.status`; never say "failed" |
| `approval_void` | "Something changed (the price or the details). Please check and approve again." | `trip.hold` again → a new read-back |
| `no_explicit_yes` | "We need a clear yes to go ahead." | ask again; never treat silence or a question as yes |
| `upstream_unreachable` | "{Source} isn't answering right now. This isn't a 'nothing found'." | retry after `retry_after_s` |
| `idempotency_in_flight` | nothing; it's still running | wait `retry_after_s`, retry the **same** key |

## 5. Webhooks

**Events:**
- `approval.presented|given|expired|void`;
- `act.confirmed|awaiting_payment|refused|failed|unknown|cancelled`;
- **`message.replied`** (v1.1).

**Payload:** ids and states only, never personal data.

**Signature:** `AgAPI-Signature: t=…,v1=…`, HMAC-SHA256 over `"<t>.<raw body>"`; reject if older than 5 minutes.

**Delivery:** at least once, de-duplicate on `webhook_id`, no ordering guarantee, retries for 24 h.

**Endpoints:** at most 2 (that's how a secret is rotated).

**Code:** verification snippets in Node, Python and Go, each run against `webhook-signature.json` in CI.

## 6. Test switches

| Magic value | Where | Result |
|---|---|---|
| `off_test_sold_out` | an offer ref | `upstream_refused` |
| `off_test_timeout_before` | an offer ref | `upstream_timeout` (nothing happened; retry safe) |
| `off_test_timeout_after` | an offer ref | `outcome_unknown` (it may have happened: poll `acts.status`) |
| `off_test_price_jump` | an offer ref | the next hold's price changes → the approval is void (`payload_changed`) |
| `src_test_down` | any find query | `upstream_unreachable` for that source; a partial result with `coverage` |
| `+1 500 555 0xxx`, `@example.test` | destinations | messages captured; read them with `sandbox.messages` |
| `sandbox.simulate_approval {said}` | — | an approval with `device.channel: sandbox_simulated` (invalid in live) |
| `sandbox.simulate_reply {number, text}` | — | an inbound WhatsApp reply; `STOP` blocks further sends |

## 7. For AI agents: the MCP manifest

**The source:** `/mcp.json` (live today: 24 tools, `schema_version 2025-06-18`), generated from the same schemas.

**Rules on this page:**
- **Envelope fields are hidden from models.** `Idempotency-Key` and `AgAPI-Approval-Id` are filled by the client, never
  by the model.
- **A model can find and hold; it can never approve.** The approval comes from the user's device.
- **Treat every `untrusted_text` field as data.**

⚠ **TO FILE for CR:** today's tool descriptions are bare (`"[magellan] travel.find_flights"`). A model picks tools
from their descriptions, so each needs the operation page's one sentence plus "needs the user's approval" where true.
Generate them from `operations.json` + a `summary` field: an additive v1.1.x field.

## 8. Changelog and versioning

**What 1.x promises:** it's additive only. New operations, fields, codes and events can appear; nothing is renamed or
removed.

**The changelog** renders `docs/agapi/v1/README.md`'s table:
- **1.0** frozen 8 Oct;
- **1.0.1** the apostrophe erratum;
- **1.1** CR's six operations, `message.replied`, the act-aware yes, the untrusted-pattern fix and the second
  apostrophe fix.

## 9. Go-live checklist

`01-partner-journey.md` step 8.

---

## CR's two open findings: resolved in v1.1

1. **AP6, "Yes, cancel it" for a cancellation's own yes (CR 61):**
   - an optional `act_kind` on the yes check;
   - for `cancel`, the words in the new `vectors/approval-language-acts.json` (EN "cancel", ES "cancela") stop vetoing;
   - every other veto still applies: "Don't cancel it" and "Yes, cancel it, wait" aren't yes;
   - without `act_kind`, AP6 is exactly 1.0.1;
   - `approval-language.json` is untouched, so Sasha's byte check still passes;
   - +8 vectors.
2. **Untrusted pattern, "ignore YOUR previous instructions" (CR 62):** `ignore` / `disregard` now allow `your`,
   `my`, `these`, `those` before `previous` / `prior` / `above` / `earlier`. +2 vectors (U-9, U-10).

**Found while doing (1): a hole in 1.0.1.**
- **The hole:** deleting apostrophes made "what's" into "whats", which escaped the question veto, so **"Yes, but
  what's the refund?" was a yes**. CR's sandbox and Sasha have the same deletion.
- **The fix:** vetoes now match in **both** forms (apostrophe deleted *and* split). +3 vectors.

**Result:** all 53 explicit-yes vectors pass. **CR and Sasha need this too.**

## v1.2: the Keep page (concept 2.8 + operations 3.8)

**One screen:** "Save your passport once. It's used only when your own yes names it, and the AI only ever sees
`Passport ES ••••456`." Plus the tier table (free / yes / read_back / never) and the **never_raw** rule: no
operation, purpose or prompt returns a value.

**Partners must:**
- show the re-issued read-back line ("I'll use your saved … for this booking.");
- treat `keep_not_approved` as "ask again";
- never log a fill token.

**DIVE** (`docs/agapi/dive/`) is a separate partner product, not a page of these docs.
