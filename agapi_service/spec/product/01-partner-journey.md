# AgAPI for partners · 1: the journey, from first look to live

*EU 211 · 9 Oct 2026 · design, docs only. Built on the contract **v1.1** (`docs/agapi/v1/`) and CR's live sandbox
`https://agapi-sandbox-production.up.railway.app`, which serves `/docs`, `/demo`, `/openapi.json` and `/mcp.json`.
Everything here works **in test mode today**. Live mode isn't open.*

**The promise, in one line:** *"Your app finds and books things for your users. AgAPI makes sure your user said yes
to exactly that, that it happens once, and that you can prove it."*

## The journey in 8 steps

| # | Step | What the partner does | What we give them | Time |
|---|---|---|---|---|
| 1 | **Discover** | lands on the docs home or the 2-minute `/demo` | the demo: find → hold → the read-back on a phone → "Yes" → booked + proof | 2 min |
| 2 | **Request access** | fills one form: company, use case, expected volume, a technical contact | a reply from a person within 2 working days (the private phase: **keys are issued by hand**, Part 4 K6) | 2 days |
| 3 | **Get a test key** | receives `agp_test_…` **shown once** on a one-time page (never by email) | the key + a sandbox account with a monthly test budget | — |
| 4 | **First call in 5 minutes** | runs the quickstart: register an end user → find flights → hold → simulate the yes → complete → read the proof | copy-paste curl, TypeScript and Python (below) | **5 min** |
| 5 | **The real approval on their user's phone** | swaps `sandbox.simulate_approval` for `approvals.request` with `channel: link_sms` to a sandbox number; reads the captured message with `sandbox.messages` | the key-less approval page (exact read-back lines → one "Yes, go ahead" button) | 15 min |
| 6 | **Webhooks** | `webhooks.register {url}`, verifies the HMAC header with the snippet, handles `act.confirmed` | the `whsec_` secret (once), a signature vector to test against | 30 min |
| 7 | **Build it in** | their UI, their copy; test the failure cases with the **test switches** (sold out, timeout, price jump, source down) | the error catalogue: each code with what to show the user | days |
| 8 | **Go live** | completes the checklist (below); we review and issue `agp_live_…` | live keys, live budget, a named contact | when live opens |

---

## Step 4: the 5-minute quickstart

**What the partner needs:** a test key in `AGAPI_KEY`. Every call is `POST /v1/{operation}` with the operation's input
as the JSON body. The answer is always the same envelope: `{ agapi, request_id, ok, result | error, trace }`.

### curl

```bash
BASE=https://agapi-sandbox-production.up.railway.app
H=(-H "Authorization: Bearer $AGAPI_KEY" -H "Content-Type: application/json" -H "AgAPI-Version: 1.1")
key() { uuidgen | tr -d '-'; }   # a NEW Idempotency-Key per action, per run (32 chars). Reuse one only to retry the same request

# 1. Register your end user (once per user). Sandbox numbers are +1 500 555 0xxx; messages are captured, never sent.
curl -s "${H[@]}" -H "Idempotency-Key: $(key)" $BASE/v1/users.register \
  -d '{"external_ref":"marta-123","destinations":[{"channel":"sms","value":"+15005550101"}]}'
#   → result.end_user_id = usr_…

# 2. Find flights.
curl -s "${H[@]}" $BASE/v1/travel.find_flights \
  -d '{"origin":{"query":"Madrid","iata":"MAD"},"destination":{"query":"Lisbon","iata":"LIS"},"date":"2026-11-20","passengers":1}'
#   → result.offers[0].offer_ref

# 3. Hold it. AgAPI re-checks the price and returns the READ-BACK: the exact lines your user will approve.
curl -s "${H[@]}" -H "Idempotency-Key: $(key)" $BASE/v1/trip.hold \
  -d '{"end_user":"usr_…","items":[{"kind":"flight","ref":"off_…"}],
       "travellers":[{"given_name":"Marta","family_name":"Ruiz","born_on":"1990-04-02","title":"ms"}]}'
#   → result.hold_id, result.read_back.read_back_id, result.read_back.lines

# 4. Test mode: simulate your user's yes, said in a separate turn.
curl -s "${H[@]}" -H "Idempotency-Key: $(key)" $BASE/v1/sandbox.simulate_approval -d '{"read_back_id":"rb_…","said":"Yes, book it."}'
#   → result.approval_id = apv_…

# 5. Complete: the one call that acts. It needs the approval and an idempotency key.
curl -s "${H[@]}" -H "Idempotency-Key: $(key)" -H "AgAPI-Approval-Id: apv_…" \
  $BASE/v1/trip.complete -d '{"hold_id":"hold_…","payment":{"method":"payment_link"}}'
#   → result.outcome.kind = CONFIRMED | AWAITING_PAYMENT …, evidence_id

# 6. The proof: fetch the evidence, then verify it (anyone can recompute its hash).
curl -s "${H[@]}" $BASE/v1/evidence.get -d '{"evidence_id":"evd_…"}' > evidence.json
curl -s "${H[@]}" $BASE/v1/evidence.verify -d "{\"evidence\": $(jq .result evidence.json)}"
#   → result.valid = true
```

### TypeScript (Node 18+, no SDK needed)

```ts
const BASE = "https://agapi-sandbox-production.up.railway.app";

async function agapi<T = any>(op: string, input: object, h: Record<string, string> = {}): Promise<T> {
  const res = await fetch(`${BASE}/v1/${op}`, {
    method: "POST",
    headers: { Authorization: `Bearer ${process.env.AGAPI_KEY}`, "Content-Type": "application/json", "AgAPI-Version": "1.1", ...h },
    body: JSON.stringify(input),
  });
  const env = await res.json();            // always an envelope, even on errors
  if (!env.ok) throw Object.assign(new Error(env.error.message), env.error);   // code, retryable, details
  return env.result as T;
}

const key = () => crypto.randomUUID().replace(/-/g, "");   // 32 chars ⇒ a valid Idempotency-Key

const user  = await agapi("users.register", { external_ref: "marta-123", destinations: [{ channel: "sms", value: "+15005550101" }] }, { "Idempotency-Key": key() });
const found = await agapi("travel.find_flights", { origin: { query: "Madrid", iata: "MAD" }, destination: { query: "Lisbon", iata: "LIS" }, date: "2026-11-20", passengers: 1 });
const hold  = await agapi("trip.hold", { end_user: user.end_user_id, items: [{ kind: "flight", ref: found.offers[0].offer_ref }],
                travellers: [{ given_name: "Marta", family_name: "Ruiz", born_on: "1990-04-02", title: "ms" }] }, { "Idempotency-Key": key() });
console.log(hold.read_back.lines.join("\n"));            // show THESE lines to your user, verbatim
const yes   = await agapi("sandbox.simulate_approval", { read_back_id: hold.read_back.read_back_id, said: "Yes, book it." }, { "Idempotency-Key": key() });
const done  = await agapi("trip.complete", { hold_id: hold.hold_id, payment: { method: "payment_link" } },
                { "Idempotency-Key": key(), "AgAPI-Approval-Id": yes.approval_id });
console.log(done.outcome.kind, done.evidence_id);
const ev    = await agapi("evidence.get", { evidence_id: done.evidence_id });
console.log((await agapi("evidence.verify", { evidence: ev })).valid);   // true
```

### Python (3.9+, `requests`)

```python
import os, uuid, requests
BASE = "https://agapi-sandbox-production.up.railway.app"

def agapi(op, body, **headers):
    h = {"Authorization": f"Bearer {os.environ['AGAPI_KEY']}", "AgAPI-Version": "1.1", **headers}
    env = requests.post(f"{BASE}/v1/{op}", json=body, headers=h, timeout=30).json()
    if not env["ok"]:
        raise RuntimeError(f"{env['error']['code']}: {env['error']['message']}")   # check env['error']['retryable']
    return env["result"]

key = lambda: uuid.uuid4().hex   # 32 chars

user  = agapi("users.register", {"external_ref": "marta-123", "destinations": [{"channel": "sms", "value": "+15005550101"}]}, **{"Idempotency-Key": key()})
found = agapi("travel.find_flights", {"origin": {"query": "Madrid", "iata": "MAD"}, "destination": {"query": "Lisbon", "iata": "LIS"}, "date": "2026-11-20", "passengers": 1})
hold  = agapi("trip.hold", {"end_user": user["end_user_id"], "items": [{"kind": "flight", "ref": found["offers"][0]["offer_ref"]}],
                            "travellers": [{"given_name": "Marta", "family_name": "Ruiz", "born_on": "1990-04-02", "title": "ms"}]}, **{"Idempotency-Key": key()})
print("\n".join(hold["read_back"]["lines"]))
yes   = agapi("sandbox.simulate_approval", {"read_back_id": hold["read_back"]["read_back_id"], "said": "Yes, book it."}, **{"Idempotency-Key": key()})
done  = agapi("trip.complete", {"hold_id": hold["hold_id"], "payment": {"method": "payment_link"}},
              **{"Idempotency-Key": key(), "AgAPI-Approval-Id": yes["approval_id"]})
print(done["outcome"]["kind"], done["evidence_id"])
ev = agapi("evidence.get", {"evidence_id": done["evidence_id"]})
print(agapi("evidence.verify", {"evidence": ev})["valid"])   # True
```

**Errata (EU 213, found by CR 64's CI, which runs these snippets byte for byte):**
- **(a)** `sandbox.simulate_approval` is idempotent in `operations.json`, so it needs an `Idempotency-Key`. All three snippets now send one.
- **(b)** The curl snippet used fixed keys, so a second run hit `idempotency_conflict` at `trip.hold`. Every key is now generated per run (`key()`).

⚠ **Before publishing, verify each snippet** against the sandbox with a test key. Field names come from the v1.1
schemas, but no key was used to run them (EU uses no accounts). TO FILE for CR: run all three in CI against the
sandbox.

## Step 5: the real approval, instead of the simulation

```bash
curl -s "${H[@]}" -H "Idempotency-Key: $(key)" $BASE/v1/approvals.request \
  -d '{"read_back_id":"rb_…","channel":"link_sms"}'
curl -s "${H[@]}" $BASE/v1/sandbox.messages -d '{"end_user_id":"usr_…"}'     # the captured SMS with the link
# open the link: the exact read-back lines → [Yes, go ahead]
curl -s "${H[@]}" $BASE/v1/approvals.status -d '{"read_back_id":"rb_…"}'  # → approval.approval_id once tapped
```

**What the partner learns here:**
- A link preview can't approve. Only the button does.
- An approval is **one use** and expires after **15 minutes**.
- Any change to the basket voids it.

## Step 6: webhooks

```bash
curl -s "${H[@]}" -H "Idempotency-Key: $(key)" $BASE/v1/webhooks.register \
  -d '{"url":"https://partner.example/agapi/hooks"}'     # → secret whsec_… (shown once)
```

**Verifying** (Part 4 W3):
- `AgAPI-Signature: t=<unix>,v1=<hex HMAC-SHA256(secret, "<t>.<raw body>")>`;
- compute over the **raw** body, compare in constant time, reject if `t` is older than 5 minutes;
- de-duplicate on `webhook_id`.

**The vectors** are in `docs/agapi/v1/vectors/webhook-signature.json`.

## Step 8: the go-live checklist

| # | The partner shows us | How we check |
|---|---|---|
| 1 | **The read-back lines are shown to the user verbatim** before any yes | a screen recording of their flow |
| 2 | **The yes is the user's own**: a tap on AgAPI's link or the SDK, never a button the partner presses for them | `approval.method` and `device.channel` on their last 50 test approvals |
| 3 | **Idempotency keys on every act**, regenerated per user action, reused on retry | the usage log: no `idempotency_key_required`, replays present after forced timeouts |
| 4 | **Errors handled by code**, not by message text; `outcome_unknown` → poll `acts.status`, never "failed" | the test-switch run: sold out, timeout before, timeout after, price jump, source down |
| 5 | **"Booked" is said only from `acts.status` = CONFIRMED or the evidence**, never from a webhook alone | their UI copy + code review |
| 6 | **Webhook signatures verified** and stale ones rejected | a replayed delivery with an old `t` is refused at their endpoint |
| 7 | **Untrusted text** (`untrusted_text`, `instruction_like`) is shown quoted, never fed to their model as instructions | their prompt and render code |
| 8 | **End users' destinations verified** (the code page or `users.verify_destination`) | `end_user.verified` on their users |
| 9 | **A named on-call contact** + their support page names AgAPI's role | the form |
| 10 | **Budget and rate limits** set for live | the account settings |

Live mode needs, on our side, the items listed in Part 4 §5 (opened by Tyler).
