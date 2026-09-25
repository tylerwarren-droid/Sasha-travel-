# The Sasha ↔ booking-helper contract

**For:** the team building Sasha — the web page and the server on Railway.
**Version:** protocol 1, booking-helper build `sasha-helper/0.1.0`, 25 September 2026.
**Self-contained:** everything needed to build the Sasha side is in this file. Nothing here refers to code
you cannot see; where behaviour matters, a reference implementation is given inline, and the test vectors in
§12 were produced and verified by the booking helper's own code.

---

## 0. ⚠ Read this first: the helper is INERT, by design, today

Three switches are off. Each produces a **specific, repeatable refusal**. None of them is a bug in your code,
and none can be fixed from Sasha's side.

| switch | state | what your page will see | cleared by |
|---|---|---|---|
| **1. no signing key is pinned** in the helper | pinned value is the literal `"UNSET"` | every `RUN` returns a `REPORT` with `rule: "no_signing_key_pinned"`, `phase: "refused"`, `tab_opened: false`, and `user_words` *"I couldn't check this booking came from me, so I didn't open anything. Nothing was sent."* — **before anything else is checked**, however correct your task is | the founder creates the key (§3.1) and the helper is rebuilt with its public half pinned |
| **2. live submission is off** in the helper build | `LIVE_SUBMIT_ENABLED = false` | (once a key is pinned) every task with `mode: "live"` returns `rule: "live_submit_disabled_in_this_build"` — *"This version of the helper can prepare a booking but can't send one yet. Nothing was sent."* `mode: "dry_run"` tasks work end to end and stop before the submit | a founder decision and a new helper build |
| **3. Sasha's page is currently framed** | the Demo tab at `https://project.kanoe.ai/demo` shows Sasha inside an `<iframe>` of `https://project.kanoe.ai/vietnam` | the port opens and immediately receives `{"type":"REFUSED","why":"a connection from a frame inside the page is refused — only Sasha's top-level page"}`, then disconnects | **decided (option B): Sasha opens in her own tab when booking.** Open `https://project.kanoe.ai/vietnam` (or wherever Sasha lives on that origin) as a top-level tab and connect from there |

**Also:** the helper is not in the Chrome Web Store yet. Until it is, it is loaded unpacked, and its
**extension ID** is whatever Chrome assigns that installation (§5.1). And the only origin allowed to connect
is **`https://project.kanoe.ai`** (§5.1).

**So the order of work that actually runs today:** build the page and the signer against this contract, test
the signer against the vectors in §12, and test the page's connection from a **top-level** tab on
`https://project.kanoe.ai`. Expect `no_signing_key_pinned` on every `RUN` until switch 1 is cleared. Do not
spend a day debugging a channel that is refusing by design.

---

## 1. What each side does

```
 Sasha server (Railway)                Sasha page (browser, top frame)          booking helper (user's Chrome)
 ───────────────────────               ────────────────────────────────          ──────────────────────────────
 records the INTENT first
 mints + SIGNS a booking task  ──────▶ holds it, never alters it  ── port ──▶  verifies signature, device, origin,
 (holds the private key)                                                        approval, expiry, refusal half
                                                                                opens the venue's page in a
                                                                                background tab, fills, (submits),
                                                                                reads the page after
 VERIFIES the device-signed    ◀────── relays it, never alters it ◀── port ──  signs a REPORT with its device key
 report, records the outcome,
 tells the page what to say
```

**The one line that must hold:** the request to the restaurant is made **from the user's own Chrome, never
from any server** of ours. Every rule below serves that line or protects the user from a result that isn't
what it looks like.

---

## 2. Primitives (both the signer and the page use these)

### 2.1 Canonical JSON — the exact bytes that are signed

A signature is over **canonical JSON encoded as UTF-8**. A serialiser that differs by one byte produces a task
that *looks* valid and is refused (`task_signature_invalid`). The rules:

1. `null` → `null`; `true` → `true`; `false` → `false`.
2. **Numbers:** finite only (NaN/Infinity are an error). Output exactly as JavaScript's `JSON.stringify(n)`.
   ⚠ The payload contains **only integers** (`v: 1`); keep it that way — non-integer formatting differs across
   languages.
3. **Strings:** exactly as JavaScript's `JSON.stringify(s)`: wrapped in `"`; `"` → `\"`; `\` → `\\`;
   U+0008 `\b`, U+000C `\f`, U+000A `\n`, U+000D `\r`, U+0009 `\t`; every other code point below U+0020 as
   `\u00XX` (**lower-case hex**); lone surrogates as `\uDXXX` (lower-case hex); **everything else literally**,
   including non-ASCII (`é` stays `é`, emitted as its UTF-8 bytes) and `/` (not escaped).
4. **Arrays:** `[` + elements joined by `,` + `]`. **Order preserved.** No spaces.
5. **Objects:** keys **sorted by UTF-16 code-unit order** (JavaScript `Array.prototype.sort()` on the keys;
   every key in this protocol is ASCII, so plain byte order gives the same result); `{` + `"key":value`
   pairs joined by `,` + `}`. No spaces.
6. ⚠ A field whose value is **undefined/absent-but-declared is an error**, not an omission. A key that is
   present must have a value; use `null` for "none".
7. Only plain objects, arrays, strings, numbers, booleans and null. A date is a **string** (ISO 8601).

**Reference implementation** (JavaScript, exactly what the helper runs):

```js
function canonicalJson(value) {
  if (value === null) return "null";
  const t = typeof value;
  if (t === "boolean") return value ? "true" : "false";
  if (t === "number") { if (!Number.isFinite(value)) throw new Error("non-finite number"); return JSON.stringify(value); }
  if (t === "string") return JSON.stringify(value);
  if (Array.isArray(value)) return `[${value.map(canonicalJson).join(",")}]`;
  if (t === "object") {
    const proto = Object.getPrototypeOf(value);
    if (proto !== Object.prototype && proto !== null) throw new Error("not a plain object");
    const keys = Object.keys(value).sort();
    for (const k of keys) if (value[k] === undefined) throw new Error(`field "${k}" is undefined`);
    return `{${keys.map((k) => `${JSON.stringify(k)}:${canonicalJson(value[k])}`).join(",")}}`;
  }
  throw new Error(`unsupported type ${t}`);
}
```

**Worked example.** Input (as a JavaScript object literal): `{ b: [3, 1, { d: null, c: true }], a: "é \"q\" \n\u0001/", Z: 0 }`
Canonical output — note `Z` sorts before `a` (upper case first), array order kept, `\u0001` lower-case, `/` literal:

```
{"Z":0,"a":"é \"q\" \n\u0001/","b":[3,1,{"c":true,"d":null}]}
```

### 2.2 Hashes, signatures, encodings

- **SHA-256** is always given as **lower-case hex**.
- **Ed25519** (RFC 8032, pure — no pre-hash, no context). A signature is the raw 64 bytes, **standard base64
  with padding** (`+`, `/`, `=`) — not URL-safe.
- **Public keys** are **SPKI DER, standard base64** — for Ed25519 always 44 bytes: the fixed prefix
  `302a300506032b6570032100` followed by the 32-byte raw public key.
- **Instants** are ISO 8601 in UTC with milliseconds, e.g. `2026-09-25T12:00:00.000Z`.

---

## 3. The signer (Sasha's server, on Railway)

### 3.1 The key

- **Environment variable:** `SASHA_BOOKING_TASK_SIGNING_KEY`, on the Railway service
  (`sasha-travel-production`). **The founder sets it himself.** No session, script or person handles the value
  in chat or a shared channel.
- **Format:** **base64 of the raw 32-byte Ed25519 seed** (the private key's seed, not a PEM, not PKCS#8).
  Refuse at startup, loudly, if it does not decode to exactly 32 bytes — a truncated key signs tasks nothing
  will ever verify.
- **The public half** is the only thing that leaves the server: its SPKI DER in standard base64 (§2.2). It is
  handed to whoever builds the helper, who pins it (`SIGNING_PUBLIC_KEY_SPKI_BASE64`). Until then the helper
  refuses everything (§0, switch 1).
- ⚠ **Plan for rotation now.** The helper ships through the Chrome Web Store, and an update takes days of
  review. With one pinned key, a rotation means days in which every installation refuses every task. Ask for
  **two** keys to be pinned (current + next) before the first store release.

### 3.2 A booking task — every field

The signer produces `{ payload, signature }`. `signature = base64(Ed25519.sign(seed, UTF-8(canonicalJson(payload))))`.
The payload's **digest** is `sha256hex(UTF-8(canonicalJson(payload)))` — record it: reports quote it (§6).

**`payload`** — every field required unless marked:

| field | type | meaning |
|---|---|---|
| `v` | `1` | protocol version |
| `kind` | `"sasha_booking_task"` | exactly this string |
| `mode` | `"dry_run"` \| `"live"` | `dry_run` fills and captures, then stops before sending. `live` sends — and is refused by today's build (§0, switch 2) |
| `task` | object, below | the act |
| `device_id` | 64 lower-case hex | the **one paired installation** this task may run on (§4). The helper refuses a task for another device |
| `spec_standing` | `{ established: boolean, basis: string\|null, source: string\|null }` | whether the venue's **refusal half** is established, on what, and where it was observed (§3.4). Signed, so the helper checks it too |
| `read_back` | `{ lines: string[], sha256: hex }` | the exact words read to the user; `sha256 = sha256hex(lines.join("\n"))` |
| `approval` | object, below | the user's yes, bound to those words and this payload |
| `issued_at` | instant | when signed |
| `expires_at` | instant | ⚠ must equal `task.expires_at`; at most **15 minutes** after `issued_at`; must be in the future |

**`payload.task`:**

| field | type | meaning |
|---|---|---|
| `intent_id` | string (a UUID) | the intent **recorded on your server before this task was signed**. One task per intent; the helper runs an intent **once, ever** — a retry is a **new intent** |
| `origin` | string | the venue's origin, e.g. `https://www.restaurante-psi.com` — exact, `https`, no path |
| `url` | string | the booking page to open; **must be on `origin`** (compared as origins, never prefixes) |
| `steps` | array | exactly `["navigate","await_form","fill_fields","submit","read_page_after","report"]` — a fixed vocabulary; `submit` and `read_page_after` are required, an unknown step is refused |
| `fields` | array of `{ name, value, selector }` | what to write, **already in the venue page's own formats** (§3.6). `selector` is the CSS selector the field is hashed under (`[name="rtb-date"]`) |
| `required` | string[] | field **names** the form requires; the helper stops if any is empty on the page |
| `envelope` | array of `{ name, value }` | hidden constants the form must already serve (checked, never injected) — at Psi: `[{"name":"action","value":"booking_request"}]` |
| `spec` | object, §3.4 | how to read the page after: acceptance and refusal |
| `outcome_ceiling` | `"requested"` \| `"confirmed"` | the best outcome this form can produce — **`"requested"` at Psi** (§8) |
| `filled_values_sha256` | hex | the payload hash, §3.3 |
| `issued_at`, `expires_at` | instants | same as the payload's |

**`payload.approval`:**

| field | type | meaning |
|---|---|---|
| `by` | string | your user identifier |
| `how` | `"button"` \| `"voice"` | how they said yes |
| `at` | instant | when |
| `said` | string \| null | ⚠ **required and non-empty when `how` is `"voice"`** — the transcribed words; there is no screen to point at afterwards |
| `read_back_sha256` | hex | = `read_back.sha256` |
| `filled_values_sha256` | hex | = `task.filled_values_sha256` |

### 3.3 The payload hash

`filled_values_sha256 = sha256hex(UTF-8(lines))` where
`lines = task.fields.map(f => f.selector + "=" + f.value).sort().join("\n")` — JavaScript default `sort()`
(UTF-16 code-unit order; for the ASCII selectors in use, byte order). The helper **re-reads the values from the
page after filling** and recomputes this; if the page changed a value (a mask, a script), it stops
(`payload_differs_from_approved`).

### 3.4 The spec, the refusal half, and the standing

```ts
spec = {
  accepted: { text_pattern: string, reference_pattern: string | null, selector: string | null, example: string },
  refused:  Array<{ text_pattern: string, meaning: string, selector: string | null }>
}
```

Patterns are **JavaScript regular-expression sources**, evaluated case-insensitively (`new RegExp(p, "i")`).
A `selector` is `null` (whole page), `"#id"`, or **`".class"`** (a single class token; every element carrying
it, as a whole token, is read). The helper checks **refusals first** (a page that refuses and happens to
contain the accepted words is a refusal), then acceptance, then **neither** — which is never a weaker yes.

**Psi's spec, verbatim** (refusals matched by the plugin's error container, so a refusal in Portuguese reads as
a refusal):

```json
{
  "accepted": {
    "text_pattern": "your\\s+booking\\s+request\\s+is\\s+waiting\\s+to\\s+be\\s+confirmed",
    "example": "Thanks, your booking request is waiting to be confirmed. Updates will be sent to the email address you provided.",
    "reference_pattern": null,
    "selector": null
  },
  "refused": [
    {
      "text_pattern": "Please\\s+enter\\s+the\\s+date\\s+you\\s+would\\s+like\\s+to\\s+book",
      "meaning": "no date was given (case date_missing)",
      "selector": ".rtb-error"
    },
    {
      "text_pattern": "The\\s+date\\s+you\\s+entered\\s+is\\s+not\\s+valid",
      "meaning": "the date was not one the calendar offers (case date_invalid)",
      "selector": ".rtb-error"
    },
    {
      "text_pattern": "bookings\\s+must\\s+be\\s+made\\s+more\\s+than\\s+\\d+\\s+days?\\s+in\\s+advance",
      "meaning": "inside the venue's booking notice, or in the past (cases inside_24h_notice, date_in_the_past)",
      "selector": ".rtb-error"
    },
    {
      "text_pattern": "no\\s+bookings\\s+are\\s+being\\s+accepted\\s+on\\s+that\\s+date",
      "meaning": "the venue takes no bookings that day (case closed_day_sunday)",
      "selector": ".rtb-error"
    },
    {
      "text_pattern": "no\\s+bookings\\s+are\\s+being\\s+accepted\\s+at\\s+that\\s+time",
      "meaning": "the venue takes no bookings at that time (case closed_time_5pm)",
      "selector": ".rtb-error"
    },
    {
      "text_pattern": "Please\\s+enter\\s+the\\s+time\\s+you\\s+would\\s+like\\s+to\\s+book",
      "meaning": "no time was given (case time_missing)",
      "selector": ".rtb-error"
    },
    {
      "text_pattern": "The\\s+time\\s+you\\s+entered\\s+is\\s+not\\s+valid",
      "meaning": "the time was not one the form offers (case time_invalid)",
      "selector": ".rtb-error"
    },
    {
      "text_pattern": "Please\\s+enter\\s+a\\s+name\\s+for\\s+this\\s+booking",
      "meaning": "no name was given (case name_missing)",
      "selector": ".rtb-error"
    },
    {
      "text_pattern": "Please\\s+let\\s+us\\s+know\\s+how\\s+many\\s+people\\s+will\\s+be\\s+in\\s+your\\s+party",
      "meaning": "no valid party size (cases party_missing, party_zero, party_not_a_number)",
      "selector": ".rtb-error"
    },
    {
      "text_pattern": "Please\\s+enter\\s+an\\s+email\\s+address\\s+so\\s+we\\s+can\\s+confirm\\s+your\\s+booking",
      "meaning": "no email was given (case email_missing)",
      "selector": ".rtb-error"
    },
    {
      "text_pattern": "\\S[\\s\\S]*",
      "meaning": "the plugin rendered a validation error in its error container (.rtb-error) — the wording may be translated, so this is matched by WHERE it renders, not by what it says",
      "selector": ".rtb-error"
    }
  ]
}
```

**Psi's standing:** `{"established": true, "basis": "reference_install", "source": "…"}` — the exact `source`
string is in the vector payload in §12. It records that the refusal wording was observed on **our own install
of the same plugin release**, not at the restaurant. ⚠ That string mentions a file name on our side (`…S-08-reference-install.json`).
It is **opaque signed data**: copy it exactly, and do not try to resolve it. Nothing in this contract depends
on opening it.

### 3.5 ⛔ What the signer MUST refuse before signing

The helper enforces most of these again — but two exist **only at the signer**, and Sasha's signer must
implement them itself: **the refusal-half guard for live tasks** (also re-checked on the device) and **the
email check** (signer only). Refuse, by name, in this order:

1. **The refusal-half guard (`mode: "live"` only).** Refuse unless **all** hold:
   - `spec_standing.established === true`;
   - `spec_standing.basis` is `"observed_at_venue"` or `"reference_install"` (**documentation is not a
     basis** — a plugin's published wording once failed to match the real page);
   - `spec_standing.source` is non-empty;
   - `spec.refused` has **at least one** entry, **none** matching `/PLACEHOLDER|NOT\s+OBSERVED|NOT\s+a\s+reading/i`
     in `text_pattern` or `meaning`, each `text_pattern` compiling, each `selector` null / `#id` / single `.class`.
   Why: a refusal the spec can't recognise reads as "unclear", the user retries, and a retry of a request that
   actually landed is a double booking.
2. **`device_id`** is 64 lower-case hex of a device this account has **paired** (§4).
3. **The email check (`mode: "live"` only).** The field carrying the user's address (Psi: `rtb-email`) must be
   present in `task.fields`, and its value must be able to receive the confirmation. ⚠ **Psi's plugin release
   accepts an invalid address and creates the booking anyway** — its confirmation arrives later **by email**,
   so without this check the user would never hear back. Reference implementation:
   ```js
   function emailCanReceiveConfirmation(value) {
     const v = (value ?? "").trim();
     if (!v) return { ok: false, why: "it is empty" };
     if (v !== value) return { ok: false, why: "leading or trailing spaces" };
     if (v.length > 254) return { ok: false, why: "longer than 254 characters" };
     const at = v.lastIndexOf("@");
     if (at < 1 || at !== v.indexOf("@")) return { ok: false, why: "not exactly one @ with something before it" };
     const local = v.slice(0, at), domain = v.slice(at + 1).toLowerCase();
     if (local.length > 64 || !/^[A-Za-z0-9!#$%&'*+/=?^_`{|}~-]+(\.[A-Za-z0-9!#$%&'*+/=?^_`{|}~-]+)*$/.test(local)) return { ok: false, why: "invalid mailbox name" };
     const labels = domain.split(".");
     if (labels.length < 2 || labels.some((l) => !/^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$/.test(l))) return { ok: false, why: "not a domain name" };
     const tld = labels[labels.length - 1];
     if (!/^[a-z]{2,63}$/.test(tld)) return { ok: false, why: "no valid top-level domain" };
     if (["test","invalid","example","localhost","local"].includes(tld) || ["example.com","example.net","example.org"].some((d) => domain === d || domain.endsWith("." + d)))
       return { ok: false, why: "a domain reserved never to deliver mail" };
     return { ok: true };
   }
   ```
   It makes **no network request**, so a well-formed address on a real-looking domain passes and may still
   bounce. It catches what the plugin lets through; it never guesses beyond that. Dry runs are not held to it.
4. **The one line** — refuse if: `url` does not parse; is not `https`; its origin ≠ `task.origin`; `task.origin`
   is **ours** (`https://applieddiligence.com`, `https://www.applieddiligence.com`, **`https://project.kanoe.ai`**);
   `steps` holds anything outside the fixed six; `submit` or `read_page_after` is missing.
5. **The approval** — refuse if `sha256hex(read_back.lines.join("\n"))` ≠ `read_back.sha256` or ≠
   `approval.read_back_sha256`; if the recomputed payload hash (§3.3) ≠ `task.filled_values_sha256` or ≠
   `approval.filled_values_sha256`; if `how` is `"voice"` with empty `said`.
6. **The stop before an intent** — refuse if any name in `required` has no non-empty value in `fields`.
7. **Time** — refuse if `expires_at` is not after now, or more than 15 minutes after `issued_at`.

And, not a refusal but an ordering rule: **record the intent before signing.** An outcome that cannot be tied
to an intent recorded *before* the act is an act nobody approved.

### 3.6 Psi, the one venue that is specified

| | value |
|---|---|
| origin / url | `https://www.restaurante-psi.com` / `https://www.restaurante-psi.com/reservas/` |
| envelope | `action = booking_request` (served; never injected) |
| `rtb-date` | page format **`mmmm d, yyyy`** → `October 2, 2026` (not ISO) |
| `rtb-time` | page format **`h:i A`** → `8:00 PM` (not `20:00`); 30-minute steps |
| `rtb-party` | a select, `1`–`100` |
| `rtb-name`, `rtb-email`, `rtb-phone` | text; the confirmation goes to `rtb-email` |
| `rtb-message` | optional; send nothing rather than an empty value |
| required | `rtb-date`, `rtb-time`, `rtb-party`, `rtb-name`, `rtb-email`, `rtb-phone` |
| schedule the venue serves | Monday–Saturday, 12:30–15:00 and 19:30–22:00; **24 hours' notice**; no Sunday |
| outcome ceiling | **`requested`** |

The read-back is five lines, exactly this template (the helper hashes the lines; any change voids the yes):

```
{venue}.
{date} at {time}, for {party}.
Under the name {name}.
They will have your email, {email}, and your telephone, {phone}.
I will open their booking page on this machine and send it from here. Shall I?
```

---

## 4. Pairing — one browser, one account

Once per browser, while the user is signed in to Sasha:

1. Your server issues a **random challenge of at least 32 characters** and remembers it for this user.
2. The page sends `{"type":"PAIR","challenge":"…"}` over the port (§5).
3. The helper answers `{"type":"PAIR","ok":true,"device_id","device_public_spki","origin","signature"}`, where
   `signature = base64(Ed25519.sign(deviceKey, UTF-8(canonicalJson({ kind: "sasha_pairing", v: 1, challenge, device_id, origin }))))`
   and `origin` is **the origin Chrome stamped on the port** — not one the page supplied.
4. Your server verifies: challenge is the one it issued; `origin === "https://project.kanoe.ai"`; the key is a
   44-byte Ed25519 SPKI; `device_id === sha256hex(SPKI DER bytes)`; the signature verifies. Then it stores
   `{ device_id, device_public_spki }` **against that account**.

The device key is generated inside the helper, non-extractable; nothing can read its private half out.

---

## 5. The page

### 5.1 Opening the connection

- Only a page on **`https://project.kanoe.ai`**, in the **top frame of a real tab**, can connect. Another site
  gets no `chrome.runtime` for the helper at all; a frame on the same origin is refused (§0, switch 3).
- `const port = chrome.runtime.connect(EXTENSION_ID)`. `EXTENSION_ID` is the helper's ID: the Web Store ID once
  listed; for an unpacked development build, the ID Chrome shows on `chrome://extensions` (it changes per
  installation unless the build pins a manifest `key`). If `chrome.runtime` is undefined, or the port
  disconnects at once with `chrome.runtime.lastError`, the helper is **not installed** (or not allowed for
  this page) — say so to the user; do not retry in a loop.
- One port per operation is fine; the helper handles each message independently.

### 5.2 What crosses — page → helper

| message | when |
|---|---|
| `{"type":"HELLO","protocol":1}` | first — find out whether the helper is there and which device it is |
| `{"type":"PAIR","challenge":"…"}` | once per browser (§4) |
| `{"type":"RUN","payload":{…},"signature":"…"}` | a signed task, **exactly as the signer returned it** |
| `{"type":"PENDING"}` | after any reconnect — collect reports you did not acknowledge |
| `{"type":"ACK","intent_id":"…"}` | after your server has verified and stored a report |

### 5.3 What crosses — helper → page

| message | meaning |
|---|---|
| `{"type":"HELLO","agent":"sasha-helper/0.1.0","protocol":1,"device_id":"…"}` | installed; this is its device |
| `{"type":"PAIR","ok":true,…}` / `{"type":"PAIR","ok":false,"why":"…"}` | §4 |
| `{"type":"PROGRESS","phase":"…"}` | zero or more, in order: `verifying` → `awaiting_permission` → `filling` → `submitting` → `reading`. A run that stops early stops sending them |
| `{"type":"REPORT","report":{…},"task_digest":"…","device_id":"…","device_signature":"…"}` | the result (§6) — **always one per `RUN`**, including refusals |
| `{"type":"PENDING_DONE"}` | after the reports owed on `PENDING` |
| `{"type":"ACKED","intent_id":"…"}` | the helper dropped that report from its store |
| `{"type":"REFUSED","why":"…"}` then disconnect | the gate refused this connection (wrong origin, a frame, not a tab) |
| `{"type":"ERROR","why":"…"}` | the helper failed handling a message — treat as "our error", do not retry the same task |

`awaiting_permission` matters for the UI: the **first booking at each venue** opens a small helper window naming
the restaurant's site, then Chrome's own permission prompt. The user must click; a voice yes cannot cover this
step. Declining returns `rule: "venue_permission_declined"`.

### 5.4 Verifying a report is genuine

The page **relays**; your **server verifies**. A script running on Sasha's page can see and alter anything the
page holds — so the page's view of a report is never trusted. The server checks:

1. `device_id` equals the device this account paired;
2. `task_digest` equals the digest recorded when the task was signed (§3.2);
3. `device_signature` verifies — Ed25519, the paired device public key, over
   `UTF-8(canonicalJson({ report, task_digest, device_id }))`.

⚠ **`task_digest` is `null`** when the helper refused **before it could verify the task** — every refusal from
`no_signing_key_pinned` through `task_signature_invalid` and the time and device checks, which is **every
report you will see today** (§0). For such a report: verify the device signature over the body as given (with
`"task_digest":null`), require `sent === false` and `tab_opened === false`, show `user_words`, and record no
outcome. The helper does not keep these for `PENDING`.

Only then record the outcome (§7) and send `ACK`. A report that fails any check is discarded and the task is
**not** treated as having run or not run — the user is told to check their email before trying again.

### 5.5 ⛔ What the page must NOT do

- **Hold the key**, or anything that can sign a task. Only the server signs.
- **Build, edit or re-sign a task.** A task altered in the page is `task_signature_invalid`.
- **Interpret the outcome** from the report it relays. It renders what the server returns after §5.4.
- **Retry.** Never send the same task twice (the helper refuses: `intent_already_run`). A second attempt is a
  **new intent**, a **new read-back**, a **new yes** and a **new task** — and never after `submitted_unread`
  until the user has checked their email, because the first may have landed.
- **Run from a frame**, or ask the helper to open anything other than the task's own URL.
- **Treat a missing report as "nothing happened".** Use `PENDING` on reconnect.

---

## 6. The report

```ts
report = {
  agent: "sasha-helper/0.1.0",
  intent_id: string | null,
  ok: boolean,
  phase: "refused" | "stopped" | "captured_not_sent" | "submitted_and_read",
  rule: string,            // why it ended — the names in §11
  why: string,             // a technical sentence, for your logs
  user_words: string | null,  // what to tell the user when nothing (or not enough) happened — §8
  tab_opened: boolean,
  sent: boolean,           // ⚠ true only once the submit was pressed
  // (the signed envelope around this object also carries task_digest: hex | null — §5.4)
  capture?:  { method, action, enctype, filled_values_sha256_device, captured_at, … },
             // dry run: includes `entries` (exactly what would have been sent);
             // live: the SHAPE and hash only — never the field values
  reading?:  { observed_by: "the user's device", intent_id, matched: "accepted" | "refused" | "neither",
               quoted: string, reference: string | null, http_status: null, bytes: number,
               page_sha256: string | null, read_at: instant, agent: string },
  payment?:  { signs: string[], amount_seen: string | null }
}
```

⚠ **`reading` is the user's device's observation, reported to you** — not yours. You did not see the page and
cannot re-read it. Record it as that ("read on your device"), never as your own observation.

---

## 7. From report to outcome (server)

- **`sent: false`** (refused, stopped, dry run, payment stop): **nothing was asked of the restaurant. Record no
  outcome.** Show `user_words`. (Recording "unreachable" here would claim you tried and failed; you did not
  try.)
- **`sent: true`, `phase: "submitted_and_read"`:** map `reading.matched`:
  - `accepted` → **REQUESTED** at Psi (the ceiling), with what the page said;
  - `refused` → **DECLINED**, with what the page said (`reading.quoted`, in the venue's own words and
    language);
  - `neither` → **UNREACHABLE** — nothing is established; the venue's words do **not** go on the record.
- **`sent: true`, anything else:** **FAILED** — sent from the user's machine, the page after not read.

---

## 8. What the user is told

Use these words; they are the ones the helper and its outcome rules already carry.

**While it runs.** ⚠ No wording is built for the progress phases; the phases themselves are
`verifying`, `awaiting_permission`, `filling`, `submitting`, `reading`. For `awaiting_permission`, the user must
act (the helper's window says: *"To send your booking, Sasha needs to open **this site** in the background and
fill in its booking form — from your computer, not ours."* / *"Chrome will ask you once for this site."*).

**REQUESTED** (the only success Psi can produce):
> *"The request is in, sent from your machine. The ceiling on this form is REQUESTED: confirmation comes
> later, from the venue. Watch for their reply."*

and, as the one-line status: *"Asked Restaurante Psi via web_form; no confirmation yet. This is not a booking."*
Psi's page itself says: *"Thanks, your booking request is waiting to be confirmed. Updates will be sent to the
email address you provided."*

**DECLINED:**
> *"The form would not take it. Their page said so on your machine — choose an alternative rather than
> repeating the ask."*

with the venue's own words (`reading.quoted`) as *"Restaurante Psi declined: "…". That is the venue's answer."*

**UNREACHABLE** (sent, and the page after matched neither):
> *"Your machine read the page after and it matched neither what acceptance looks like nor what refusal looks
> like. Nothing is established. Read it yourself before any retry — and a retry is a NEW intent."*

and to the user (`user_words` when `rule` is `submitted_unread`): *"I sent it from your computer but couldn't
read their reply. Please check your email before we try again — trying again could book twice."*
⚠ Do **not** use the generic sentence "We could not reach … nothing was asked" here — on this path something
**was** sent.

**FAILED:** *"It was sent from the user's machine and the page after could not be read. Check for the venue's
email before any retry — a retry is a NEW intent, and a repeat could book twice."*

**Payment:** *"They want a payment to hold this table. I've filled in the details and stopped before paying — a
payment always needs its own yes from you. Nothing was paid."* A payment is never covered by the booking's yes.

**Anything else that stops it:** show the report's `user_words` as given. Every one says whether anything was
sent.

**⛔ CONFIRMED is not reachable through this surface.** Psi's form submits a *request*; its page gives no
reference; confirmation arrives later, by email, from the restaurant. The task's `outcome_ceiling` is
`"requested"`, and an accepted page is clamped to REQUESTED. Never show "booked" or "confirmed" from this path.

---

## 9. Timing and single use

- A task lives **at most 15 minutes**. An expired task is `task_expired` — read back again, get a new yes,
  mint a new task.
- Each `intent_id` runs **once per device, ever**. A second `RUN` of the same task returns
  `intent_already_run` and opens nothing.
- A report is kept by the helper until you `ACK` it and re-sent on `PENDING`.

---

## 10. Dry run

`mode: "dry_run"` goes through every check, opens the venue's page in a background tab, fills it, confirms the
page holds exactly the approved values, and **stops before the submit**. Its report has
`phase: "captured_not_sent"`, `sent: false`, and `capture.entries` — exactly what would have been sent. This is
the mode to build and test against (once switch 1 is cleared).

---

## 11. Refusal and stop names (for your logs)

**At the helper, before anything opens:** `no_signing_key_pinned`, `task_signature_invalid`,
`browser_cannot_verify`, `task_expired`, `task_lifetime_too_long`, `task_without_a_device`,
`task_for_another_device`, `task_malformed`, `url_unparseable`, `not_https`, `url_outside_origin`,
`originates_on_our_server`, `unknown_step`, `no_submit_on_the_device`, `no_reading_on_the_device`,
`approval_not_bound`, `approval_void_words`, `approval_void_payload`, `approval_voice_without_words`,
`live_without_established_refusal`, `live_refusal_basis_not_accepted`, `live_refusal_without_source`,
`live_on_a_placeholder_refusal`, `live_refusal_pattern_invalid`, `live_refusal_selector_unsupported`,
`live_submit_disabled_in_this_build`, `intent_already_run`, `venue_permission_declined`,
`venue_permission_unanswered`.

**On the venue's page:** `page_did_not_load`, `redirected_off_origin`, `challenge` (a CAPTCHA — never worked
around), `form_not_found`, `envelope_missing`, `envelope_differs`, `field_not_found`, `option_not_served`,
`required_field_empty`, `payload_differs_from_approved`, `payload_moved_before_submit`, `no_submit_control`,
`payment_needs_its_own_yes`.

**Endings:** `captured_not_sent` (dry run), `read_accepted`, `read_refused`, `submitted_unread`,
`our_error_before_send`, `our_error`.

**Your signer's own refusals** (names suggested, to match): `live_without_established_refusal` (and the other
`live_*` above), `no_paired_device`, `no_confirmation_email`, `email_cannot_receive_confirmation`,
`originates_on_our_server` (and the other one-line names), `approval_void`, `approval_void_payload`,
`required_field_empty`, `task_expired`, `task_lifetime_too_long`.

---

## 12. Test vectors

Produced by the helper's own code and **verified by it**: the task below passes the helper's verifier (with the
test key standing in for the pinned one, the test device, at `2026-09-25T12:01:00.000Z`); the report passes the
server-side report check; the pairing passes the pairing check.

⚠ **These keys are the public RFC 8032 test keys.** Never use them for anything real.

- **Signer test key** — RFC 8032 §7.1 TEST 1 seed:
  `9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60` (hex) → public SPKI (base64):
  `MCowBQYDK2VwAyEA11qYAYKxCrfVS/7TyWQHOg7hcvPapiMlrwIaaPcHURo=`
- **Device test key** — RFC 8032 §7.1 TEST 2 seed:
  `4ccd089b28ff96da9db6c346ec114e0f5b8a319f35aba624da8cf6ed4fb8a6fb` → SPKI: `MCowBQYDK2VwAyEAPUAXw+hDiVqStwqnTRt+vJyYLM8uxJaMwM1V8Sr0Zgw=`
  → `device_id` = `deb2ded39dc26fce0e6085b6fc34bf6b5941913bbfe2ea614113cff9e004c170`

**Payload hash.** The lines (§3.3), shown as a JSON string:
`"[name=\"rtb-date\"]=October 2, 2026\n[name=\"rtb-email\"]=ana.guest@example.org\n[name=\"rtb-name\"]=Ana Guest\n[name=\"rtb-party\"]=2\n[name=\"rtb-phone\"]=+351 000 000 000\n[name=\"rtb-time\"]=8:00 PM"` → `filled_values_sha256` = `71d1874c6858ad0b33f053a9026555f29e76951007761d9ed4f9188c76ae5d8e`
**Read-back hash** = `ded1027b041a46a66eae74e38d9266bb366b297c9d3d46f88597c1e6a823cdb8`

**The payload** (pretty-printed here for reading — the signature is over the canonical form below, not this):

```json
{
  "v": 1,
  "kind": "sasha_booking_task",
  "mode": "dry_run",
  "task": {
    "intent_id": "00000000-0000-4000-8000-000000000001",
    "origin": "https://www.restaurante-psi.com",
    "url": "https://www.restaurante-psi.com/reservas/",
    "steps": [
      "navigate",
      "await_form",
      "fill_fields",
      "submit",
      "read_page_after",
      "report"
    ],
    "fields": [
      {
        "name": "rtb-date",
        "value": "October 2, 2026",
        "selector": "[name=\"rtb-date\"]"
      },
      {
        "name": "rtb-time",
        "value": "8:00 PM",
        "selector": "[name=\"rtb-time\"]"
      },
      {
        "name": "rtb-party",
        "value": "2",
        "selector": "[name=\"rtb-party\"]"
      },
      {
        "name": "rtb-name",
        "value": "Ana Guest",
        "selector": "[name=\"rtb-name\"]"
      },
      {
        "name": "rtb-email",
        "value": "ana.guest@example.org",
        "selector": "[name=\"rtb-email\"]"
      },
      {
        "name": "rtb-phone",
        "value": "+351 000 000 000",
        "selector": "[name=\"rtb-phone\"]"
      }
    ],
    "required": [
      "rtb-date",
      "rtb-time",
      "rtb-party",
      "rtb-name",
      "rtb-email",
      "rtb-phone"
    ],
    "envelope": [
      {
        "name": "action",
        "value": "booking_request"
      }
    ],
    "spec": {
      "accepted": {
        "text_pattern": "your\\s+booking\\s+request\\s+is\\s+waiting\\s+to\\s+be\\s+confirmed",
        "example": "Thanks, your booking request is waiting to be confirmed. Updates will be sent to the email address you provided.",
        "reference_pattern": null,
        "selector": null
      },
      "refused": [
        {
          "text_pattern": "Please\\s+enter\\s+the\\s+date\\s+you\\s+would\\s+like\\s+to\\s+book",
          "meaning": "no date was given (case date_missing)",
          "selector": ".rtb-error"
        },
        {
          "text_pattern": "The\\s+date\\s+you\\s+entered\\s+is\\s+not\\s+valid",
          "meaning": "the date was not one the calendar offers (case date_invalid)",
          "selector": ".rtb-error"
        },
        {
          "text_pattern": "bookings\\s+must\\s+be\\s+made\\s+more\\s+than\\s+\\d+\\s+days?\\s+in\\s+advance",
          "meaning": "inside the venue's booking notice, or in the past (cases inside_24h_notice, date_in_the_past)",
          "selector": ".rtb-error"
        },
        {
          "text_pattern": "no\\s+bookings\\s+are\\s+being\\s+accepted\\s+on\\s+that\\s+date",
          "meaning": "the venue takes no bookings that day (case closed_day_sunday)",
          "selector": ".rtb-error"
        },
        {
          "text_pattern": "no\\s+bookings\\s+are\\s+being\\s+accepted\\s+at\\s+that\\s+time",
          "meaning": "the venue takes no bookings at that time (case closed_time_5pm)",
          "selector": ".rtb-error"
        },
        {
          "text_pattern": "Please\\s+enter\\s+the\\s+time\\s+you\\s+would\\s+like\\s+to\\s+book",
          "meaning": "no time was given (case time_missing)",
          "selector": ".rtb-error"
        },
        {
          "text_pattern": "The\\s+time\\s+you\\s+entered\\s+is\\s+not\\s+valid",
          "meaning": "the time was not one the form offers (case time_invalid)",
          "selector": ".rtb-error"
        },
        {
          "text_pattern": "Please\\s+enter\\s+a\\s+name\\s+for\\s+this\\s+booking",
          "meaning": "no name was given (case name_missing)",
          "selector": ".rtb-error"
        },
        {
          "text_pattern": "Please\\s+let\\s+us\\s+know\\s+how\\s+many\\s+people\\s+will\\s+be\\s+in\\s+your\\s+party",
          "meaning": "no valid party size (cases party_missing, party_zero, party_not_a_number)",
          "selector": ".rtb-error"
        },
        {
          "text_pattern": "Please\\s+enter\\s+an\\s+email\\s+address\\s+so\\s+we\\s+can\\s+confirm\\s+your\\s+booking",
          "meaning": "no email was given (case email_missing)",
          "selector": ".rtb-error"
        },
        {
          "text_pattern": "\\S[\\s\\S]*",
          "meaning": "the plugin rendered a validation error in its error container (.rtb-error) — the wording may be translated, so this is matched by WHERE it renders, not by what it says",
          "selector": ".rtb-error"
        }
      ]
    },
    "outcome_ceiling": "requested",
    "filled_values_sha256": "71d1874c6858ad0b33f053a9026555f29e76951007761d9ed4f9188c76ae5d8e",
    "issued_at": "2026-09-25T12:00:00.000Z",
    "expires_at": "2026-09-25T12:10:00.000Z"
  },
  "device_id": "deb2ded39dc26fce0e6085b6fc34bf6b5941913bbfe2ea614113cff9e004c170",
  "spec_standing": {
    "established": true,
    "basis": "reference_install",
    "source": "our own WordPress Playground install (WP 6.6, PHP 7.4) of Five Star Restaurant Reservations 1.4.6 and 1.5.3 — the releases whose form matches Psi's served form exactly — 25 September 2026, 14 refusal cases; docs/sasha/S-08-reference-install.json. NOT observed at Psi."
  },
  "read_back": {
    "lines": [
      "Restaurante Psi, Lisbon.",
      "October 2, 2026 at 8:00 PM, for 2.",
      "Under the name Ana Guest.",
      "They will have your email, ana.guest@example.org, and your telephone, +351 000 000 000.",
      "I will open their booking page on this machine and send it from here. Shall I?"
    ],
    "sha256": "ded1027b041a46a66eae74e38d9266bb366b297c9d3d46f88597c1e6a823cdb8"
  },
  "approval": {
    "by": "user-123",
    "how": "voice",
    "at": "2026-09-25T11:59:30.000Z",
    "said": "yes, book it",
    "read_back_sha256": "ded1027b041a46a66eae74e38d9266bb366b297c9d3d46f88597c1e6a823cdb8",
    "filled_values_sha256": "71d1874c6858ad0b33f053a9026555f29e76951007761d9ed4f9188c76ae5d8e"
  },
  "issued_at": "2026-09-25T12:00:00.000Z",
  "expires_at": "2026-09-25T12:10:00.000Z"
}
```

**Canonical form — 4568 bytes, UTF-8, one line:**

```
{"approval":{"at":"2026-09-25T11:59:30.000Z","by":"user-123","filled_values_sha256":"71d1874c6858ad0b33f053a9026555f29e76951007761d9ed4f9188c76ae5d8e","how":"voice","read_back_sha256":"ded1027b041a46a66eae74e38d9266bb366b297c9d3d46f88597c1e6a823cdb8","said":"yes, book it"},"device_id":"deb2ded39dc26fce0e6085b6fc34bf6b5941913bbfe2ea614113cff9e004c170","expires_at":"2026-09-25T12:10:00.000Z","issued_at":"2026-09-25T12:00:00.000Z","kind":"sasha_booking_task","mode":"dry_run","read_back":{"lines":["Restaurante Psi, Lisbon.","October 2, 2026 at 8:00 PM, for 2.","Under the name Ana Guest.","They will have your email, ana.guest@example.org, and your telephone, +351 000 000 000.","I will open their booking page on this machine and send it from here. Shall I?"],"sha256":"ded1027b041a46a66eae74e38d9266bb366b297c9d3d46f88597c1e6a823cdb8"},"spec_standing":{"basis":"reference_install","established":true,"source":"our own WordPress Playground install (WP 6.6, PHP 7.4) of Five Star Restaurant Reservations 1.4.6 and 1.5.3 — the releases whose form matches Psi's served form exactly — 25 September 2026, 14 refusal cases; docs/sasha/S-08-reference-install.json. NOT observed at Psi."},"task":{"envelope":[{"name":"action","value":"booking_request"}],"expires_at":"2026-09-25T12:10:00.000Z","fields":[{"name":"rtb-date","selector":"[name=\"rtb-date\"]","value":"October 2, 2026"},{"name":"rtb-time","selector":"[name=\"rtb-time\"]","value":"8:00 PM"},{"name":"rtb-party","selector":"[name=\"rtb-party\"]","value":"2"},{"name":"rtb-name","selector":"[name=\"rtb-name\"]","value":"Ana Guest"},{"name":"rtb-email","selector":"[name=\"rtb-email\"]","value":"ana.guest@example.org"},{"name":"rtb-phone","selector":"[name=\"rtb-phone\"]","value":"+351 000 000 000"}],"filled_values_sha256":"71d1874c6858ad0b33f053a9026555f29e76951007761d9ed4f9188c76ae5d8e","intent_id":"00000000-0000-4000-8000-000000000001","issued_at":"2026-09-25T12:00:00.000Z","origin":"https://www.restaurante-psi.com","outcome_ceiling":"requested","required":["rtb-date","rtb-time","rtb-party","rtb-name","rtb-email","rtb-phone"],"spec":{"accepted":{"example":"Thanks, your booking request is waiting to be confirmed. Updates will be sent to the email address you provided.","reference_pattern":null,"selector":null,"text_pattern":"your\\s+booking\\s+request\\s+is\\s+waiting\\s+to\\s+be\\s+confirmed"},"refused":[{"meaning":"no date was given (case date_missing)","selector":".rtb-error","text_pattern":"Please\\s+enter\\s+the\\s+date\\s+you\\s+would\\s+like\\s+to\\s+book"},{"meaning":"the date was not one the calendar offers (case date_invalid)","selector":".rtb-error","text_pattern":"The\\s+date\\s+you\\s+entered\\s+is\\s+not\\s+valid"},{"meaning":"inside the venue's booking notice, or in the past (cases inside_24h_notice, date_in_the_past)","selector":".rtb-error","text_pattern":"bookings\\s+must\\s+be\\s+made\\s+more\\s+than\\s+\\d+\\s+days?\\s+in\\s+advance"},{"meaning":"the venue takes no bookings that day (case closed_day_sunday)","selector":".rtb-error","text_pattern":"no\\s+bookings\\s+are\\s+being\\s+accepted\\s+on\\s+that\\s+date"},{"meaning":"the venue takes no bookings at that time (case closed_time_5pm)","selector":".rtb-error","text_pattern":"no\\s+bookings\\s+are\\s+being\\s+accepted\\s+at\\s+that\\s+time"},{"meaning":"no time was given (case time_missing)","selector":".rtb-error","text_pattern":"Please\\s+enter\\s+the\\s+time\\s+you\\s+would\\s+like\\s+to\\s+book"},{"meaning":"the time was not one the form offers (case time_invalid)","selector":".rtb-error","text_pattern":"The\\s+time\\s+you\\s+entered\\s+is\\s+not\\s+valid"},{"meaning":"no name was given (case name_missing)","selector":".rtb-error","text_pattern":"Please\\s+enter\\s+a\\s+name\\s+for\\s+this\\s+booking"},{"meaning":"no valid party size (cases party_missing, party_zero, party_not_a_number)","selector":".rtb-error","text_pattern":"Please\\s+let\\s+us\\s+know\\s+how\\s+many\\s+people\\s+will\\s+be\\s+in\\s+your\\s+party"},{"meaning":"no email was given (case email_missing)","selector":".rtb-error","text_pattern":"Please\\s+enter\\s+an\\s+email\\s+address\\s+so\\s+we\\s+can\\s+confirm\\s+your\\s+booking"},{"meaning":"the plugin rendered a validation error in its error container (.rtb-error) — the wording may be translated, so this is matched by WHERE it renders, not by what it says","selector":".rtb-error","text_pattern":"\\S[\\s\\S]*"}]},"steps":["navigate","await_form","fill_fields","submit","read_page_after","report"],"url":"https://www.restaurante-psi.com/reservas/"},"v":1}
```

- `digest` = `sha256hex(canonical)` = `88a6bbef26b21c3f77a2e8ca10851240976a3cc05ce96d45f5dd6dda810016cd`
- `signature` (signer test key) = `gdIKducUz3vTenXlGgqc6mYjJvFM8IFyUV7Jsn+XLOLXYLR4Sk2XbawP1iKZA7YGB7aF0q+vRWbDeTdK/o7KBQ==`

⚠ This example is a **dry run** with a test address on `example.org`. As a **live** task it would be refused by
the email check (§3.5, step 3) — `example.org` is reserved never to deliver mail — and by today's helper build
(§0).

**A report** (dry run), the signed body as canonical JSON:

```
{"device_id":"deb2ded39dc26fce0e6085b6fc34bf6b5941913bbfe2ea614113cff9e004c170","report":{"agent":"sasha-helper/0.1.0","capture":{"action":"https://www.restaurante-psi.com/reservas/","captured_at":"2026-09-25T12:00:05.000Z","enctype":"application/x-www-form-urlencoded","entries":[["action","booking_request"],["rtb-date","October 2, 2026"]],"filled_values_sha256_device":"71d1874c6858ad0b33f053a9026555f29e76951007761d9ed4f9188c76ae5d8e","method":"POST","submitter":"Faça a Reserva"},"intent_id":"00000000-0000-4000-8000-000000000001","ok":true,"phase":"captured_not_sent","rule":"captured_not_sent","sent":false,"tab_opened":true,"user_words":"I've filled in their form on your computer and stopped just before sending, as planned. Nothing was sent.","why":"dry run: filled, checked against the approved payload, captured, and stopped before the submit"},"task_digest":"88a6bbef26b21c3f77a2e8ca10851240976a3cc05ce96d45f5dd6dda810016cd"}
```

- `device_signature` (device test key) = `asYlq0qIo7T1R9YO5TommiWjgnNKtrR8uLsLfILrU+vCWEZpsr+emmCHQ+HFMMh6lZ8aBwfheeq4F/ePT8j7Cg==`

**A pairing**, canonical statement:

```
{"challenge":"cccccccccccccccccccccccccccccccccccccccc","device_id":"deb2ded39dc26fce0e6085b6fc34bf6b5941913bbfe2ea614113cff9e004c170","kind":"sasha_pairing","origin":"https://project.kanoe.ai","v":1}
```

- `signature` (device test key) = `KNVP0quH+TmHQ818uSSUu0YKd8dsczOThdbUPsD4vwP/2rzBrzN3KW6MJz52WyBJxhSOgcSMucusbeYasUDuDg==`

If your serialiser reproduces the canonical strings byte for byte and your signer reproduces the signatures,
you are compatible. Ed25519 is deterministic: the same key and bytes always give the same signature.
