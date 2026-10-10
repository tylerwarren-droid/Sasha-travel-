# S2's subscription radar: the wiring

*CR 72 · branch `cr/s2-subscriptions` (from main `6899468`), for the Sasha tab to merge. Not on main.*

> "Sasha, what am I subscribed to?" → a short list (service, amount, how often, last charge, likely unused, with its reason) →
> "cancel Calm" → she reads it back → "yes" → "cancel requested", until the merchant confirms.

The work is done by AgAPI (`subscriptions.find`, `subscriptions.cancel_plan`, `subscriptions.cancel`, in `cr/agapi-api`, deployed on
agapi-sandbox and agapi-live). Sasha only asks and says.

**On /s2 only.** S1 (/next) never sees these tools: its tool list and its fingerprint are unchanged (tests below).

## What changes in the code

### 1 · `backend/agapi/s2_subscriptions.py` (new)

The radar's three tools for /s2:
- **`find_subscriptions`**
- **`plan_cancel_subscription`**
- **`cancel_subscription`**

**Calls to AgAPI:**
- `SASHA_SUBSCRIPTIONS_VIA=sandbox` (the default) uses `SASHA_AGAPI_TEST_KEY`.
- `SASHA_SUBSCRIPTIONS_VIA=live` uses `SASHA_AGAPI_KEY`.

**The yes:**
- **Test mode:** the person's OWN words, in a later turn than the read-back, go to AgAPI, whose rules decide whether it's a yes.
  "What's the refund?" is not one.
- **Live:** AgAPI's approval link goes to their phone and their tap is the yes.

**Statements:** kept in this server's memory for 30 minutes, read once, never on disk.

### 2 · `backend/app/agent/sasha.py`

**In `turn()`, before /s2's block:**
```python
run = API.call        # CR 72 · how a tool runs: agapi.v0.call, as always — /s2's block below is the ONLY place that changes it
```

**Inside `if surface == "s2":`, after S2's tool filter:**
```python
from agapi import s2_subscriptions as SUBS   # CR 72 · the subscription radar: /s2's own three tools, run here
tools = tools + [dict(t) for t in SUBS.TOOLS]
run = SUBS.wrap(run)
```

**In the tool loop:** `r = await API.call(ctx, u.name, args)` becomes `r = await run(ctx, u.name, args)`.

**A new route, `POST /api/agent/s2/statement`:**
- Accepts `{media_type, content_base64}` and returns `{statement_ref}`.
- Answers only with `x-sasha-surface: s2` and a signed-in account. /next gets 404.

### 3 · Tests

- **`backend/tests/test_s2_subscriptions.py`** (new, 7 tests):
  - the list from the sample;
  - cancel needs their own yes in a later turn, and a question is refused by AgAPI's rule;
  - live, the yes is their tap and the sample is refused;
  - an uploaded statement is read once, and only by its own account;
  - S1 never sees the radar and S2 does;
  - S1's fingerprint is unchanged, with zero radar calls;
  - the statement route is S2-only.
- **`backend/tests/test_s2_221.py`:** S2's pinned tool set now also includes the three radar tools. S1's checks are unchanged.

## Merging alongside `cr/s2-via-agapi`

Both branches add one line before /s2's block (`run = API.call`), and both change `run` inside it. Keep one `run = API.call` and
both additions, in this order:
```python
run = VIA.runner(API.call)
run = SUBS.wrap(run)
```
The radar's tools never go through `via_agapi`: they are AgAPI's already.

## Switching it on

1. Merge `cr/s2-subscriptions` through the normal gate. Until a key is set, the tools answer "not switched on yet".
2. Tyler pastes `SASHA_AGAPI_TEST_KEY` on Sasha's Railway: a sandbox test key for the `sasha` product. Mint it with the CR tab's
   signed admin; it lands in Keychain.
3. **Upload button:** /s2's page still needs one (a paperclip in `frontend/app/s2/S2App.tsx`). It reads the file, sends it to
   `/api/agent/s2/statement`, and then sends the chat line "Here's my statement" with the `statement_ref`. Until then the demo uses
   the sample.
4. **Live** (`SASHA_SUBSCRIPTIONS_VIA=live` + `SASHA_AGAPI_KEY`) needs two things:
   - **Routes:** a merchant's email isn't on AgAPI live's allow-list, so live cancels go by the cancel-page route to the person's
     own phone, and they finish it there.
   - **Privacy:** reading a PDF or a photo sends it to the AI reader (Anthropic) for this one read. Say so in the privacy notice
     before switching live on.

## The 30-second demo (test mode, the sample statement)

| Say (on /s2) | She does | On screen |
|---|---|---|
| "Sasha, what am I subscribed to? Use my sample statement." | `find_subscriptions` | "Ten subscriptions, about **€146 a month**. Three look unused: **Calm** started as a free trial in July and became paid; **YouTube Premium**, and you also pay for Spotify; **Disney+**, and you also pay for Netflix." |
| "Cancel Calm." | `plan_cancel_subscription` → `cancel_subscription` (read-back) | "I'll email Calm's cancellation address and ask them to cancel. It stays 'cancel requested' until they confirm. Shall I?" |
| "Yes, cancel it." | `cancel_subscription` with her own words → AgAPI | "Done: cancellation requested from Calm. I'll show it as cancelled once they confirm." |

**What not to claim:**
- **Calm isn't cancelled yet:** it's "requested". In test mode nothing is sent to Calm; the email is captured.
- **It isn't logging in:** Sasha never logs into anyone's account.
- **The reasons are the statement's:** a trial that became paid, a second service of the same kind. They aren't a guess about the
  person's habits.
