"""CR 66 · AgAPI's PUBLIC DOCS on the sandbox, following EU 211's docs/agapi/product/02-docs-site.md table of contents. Generated where it
can be — the operation pages from spec/v1/operations.json (1.2, the Keep included) + the schemas, the errors from error-codes.json, the
changelog from spec/v1/README.md, the quickstart and the go-live checklist from EU's partner journey (vendored, byte for byte) — so
the docs can't drift from the contract. The earlier one-page docs stay at /docs/reference."""
from __future__ import annotations

import html
import json
import re
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from . import config, gen
from .registry import operations, resolved

router = APIRouter()
SPEC = config.ROOT / "agapi_service" / "spec"
H = html.escape


# ── a small, safe markdown renderer (escape first; then **bold**, `code`, [links](…), lists, tables, fences) ─────────────

def _inline(s: str) -> str:
    s = H(s, quote=False)
    s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
    s = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", s)
    s = re.sub(r"(?<![\w*])\*([^*\n]+)\*(?![\w*])", r"<i>\1</i>", s)
    s = re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+|/[^)\s]*)\)", r'<a href="\2">\1</a>', s)
    return s


def md(text: str) -> str:
    out: List[str] = []
    lines = text.split("\n")
    i = 0
    while i < len(lines):
        l = lines[i]
        if l.startswith("```"):
            lang, code = l[3:].strip(), []
            i += 1
            while i < len(lines) and not lines[i].startswith("```"):
                code.append(lines[i])
                i += 1
            out.append(f'<pre data-lang="{H(lang)}"><code>{H(chr(10).join(code))}</code></pre>')
        elif l.startswith("|") and i + 1 < len(lines) and re.match(r"^\|[\s|:-]+\|$", lines[i + 1]):
            head = [c.strip() for c in l.strip("|").split("|")]
            rows = []
            i += 2
            while i < len(lines) and lines[i].startswith("|"):
                rows.append([c.strip() for c in lines[i].strip("|").split("|")])
                i += 1
            i -= 1
            out.append("<table><tr>" + "".join(f"<th>{_inline(c)}</th>" for c in head) + "</tr>" +
                       "".join("<tr>" + "".join(f"<td>{_inline(c)}</td>" for c in r) + "</tr>" for r in rows) + "</table>")
        elif m := re.match(r"^(#{1,4}) (.*)", l):
            n = len(m.group(1)) + 1
            out.append(f"<h{n}>{_inline(m.group(2))}</h{n}>")
        elif re.match(r"^\s*[-*] ", l):
            items = []
            while i < len(lines) and re.match(r"^\s*[-*] ", lines[i]):
                items.append(re.sub(r"^\s*[-*] ", "", lines[i]))
                i += 1
            i -= 1
            out.append("<ul>" + "".join(f"<li>{_inline(x)}</li>" for x in items) + "</ul>")
        elif l.strip().startswith(("⚠",)) or l.strip():
            para = [l]
            while i + 1 < len(lines) and lines[i + 1].strip() and not re.match(r"^(#|```|\||\s*[-*] )", lines[i + 1]):
                i += 1
                para.append(lines[i])
            out.append(f"<p>{_inline(' '.join(p.strip() for p in para))}</p>")
        i += 1
    return "\n".join(out)


def _section(md_text: str, start: str, end: Optional[str]) -> str:
    a = md_text.index(start)
    b = md_text.index(end, a + 1) if end else len(md_text)
    return md_text[a:b]


def journey() -> str:
    return (SPEC / "product" / "01-partner-journey.md").read_text(encoding="utf-8")


# ── what to show your user, for every code (written once, here — EU 211 §4) ───────────────────────────────────────────

SHOW: Dict[str, Tuple[str, str]] = {
    "invalid_request": ("nothing — it's a bug on your side", "fix the request: the body is the operation's input object, JSON"),
    "invalid_input": ("“Please check the details.” (and point at details.path)", "correct the field named by details.path / details.rule"),
    "unknown_operation": ("nothing", "check the operation name and AgAPI-Version"),
    "version_unsupported": ("nothing", "send an AgAPI-Version this server lists (details.supported)"),
    "not_found": ("“We couldn't find that booking.”", "check the id belongs to this account"),
    "unauthenticated": ("nothing — it's your configuration", "send Authorization: Bearer agp_test_… / agp_live_…"),
    "forbidden": ("nothing", "use a key whose scopes include the operation"),
    "mode_not_available": ("nothing", "test-only operations need a test key; live isn't open yet"),
    "rate_limited": ("“One moment…” (retry silently)", "wait retry_after_s, then retry the same request"),
    "budget_exhausted": ("“This service is paused right now.”", "raise the key's budget, or wait for the next period"),
    "idempotency_key_required": ("nothing", "send an Idempotency-Key (16–128 chars), a new one per action"),
    "idempotency_in_flight": ("nothing — it's still running", "wait retry_after_s and retry with the SAME key"),
    "idempotency_conflict": ("nothing — it's a bug on your side", "a key was reused for a different request: generate a new key per action"),
    "already_completed": ("“That's already booked.”", "read acts.status for the act"),
    "approval_required": ("the read-back lines, verbatim, and “Do you want to go ahead?”", "show details.read_back.lines; get the user's yes (approvals.request or your SDK)"),
    "approval_not_found": ("“Please approve again.”", "request a fresh approval"),
    "approval_same_turn": ("“Please confirm in a separate step.”", "the yes must come after the read-back was shown, in a later action"),
    "approval_expired": ("“That took a little long — please check and approve again.”", "hold again → a new read-back and approval"),
    "approval_void": ("“Something changed (the price or the details). Please check and approve again.”", "trip.hold again → a new read-back; never reuse the old yes"),
    "approval_consumed": ("“That's already been done.”", "one yes authorises one act; check acts.status"),
    "approval_untrusted_origin": ("“Please approve on your own phone.”", "approvals come only from the user's device (link, SDK, Sasha) — never from your server"),
    "no_explicit_yes": ("“We need a clear yes to go ahead.”", "ask again; never treat a question or silence as a yes"),
    "upstream_unreachable": ("“{Source} isn't answering right now. This isn't a ‘nothing found’.”", "retry after retry_after_s"),
    "upstream_timeout": ("“{Source} is slow right now — nothing has been booked. Try again in a moment.”", "retry: nothing took effect"),
    "upstream_rate_limited": ("“{Source} is busy — trying again shortly.”", "retry after retry_after_s"),
    "upstream_failed": ("“{Source} had a problem. This isn't a ‘nothing found’.”", "retry after retry_after_s"),
    "upstream_refused": ("the provider's answer, plainly (“That fare has sold out.”)", "offer the user another option; don't retry the same request"),
    "outcome_unknown": ("“We're confirming your booking. This can take a minute.”", "poll acts.status; never say “failed”; keep the same idempotency key"),
    "internal": ("“Something went wrong on our side. Nothing was changed.”", "retry later; it's safe — nothing happened"),
    "hold_expired": ("“The price could change — let's check it again.”", "trip.hold again"),
    "travellers_missing": ("“We need each traveller's full name, title and date of birth.”", "collect them, then trip.hold with travellers"),
    "not_cancellable": ("“This booking can't be cancelled now.”", "show the provider's terms; offer support"),
    "destination_code_invalid": ("“That code isn't right — {n} tries left.”", "let them re-enter (details.attempts_remaining)"),
    "destination_code_expired": ("“That code expired — we've sent a new one.”", "users.register again for a new code"),
    "webhook_url_refused": ("nothing — your configuration", "use a public https URL"),
    "webhook_limit_reached": ("nothing — your configuration", "revoke an endpoint first (that's how a secret is rotated)"),
}

GROUPS = [("Find", ["travel.find_flights", "travel.find_stays", "venues.find_venues"]),
          ("Act", ["trip.hold", "approvals.request", "trip.complete", "trip.cancel"]),
          ("Messages", ["messages.send_email", "messages.send_whatsapp", "messages.replies"]),
          ("After", ["acts.status", "approvals.status", "activity.list", "calendar.add_event"]),
          ("Proof", ["evidence.get", "evidence.verify"]),
          ("Account", ["users.register", "users.verify_destination", "usage.get", "webhooks.register", "webhooks.revoke"]),
          ("Test only", ["sandbox.simulate_approval", "sandbox.messages", "sandbox.simulate_reply"]),
          ("The Keep", ["keep.put", "keep.list", "keep.use", "keep.delete", "keep.activity"])]

TEST_IT = {"travel.find_flights": "`src_test_down` in a query → upstream_unreachable for that source (never “no results”).",
           "travel.find_stays": "`src_test_down` in a query → upstream_unreachable, a partial result with coverage.",
           "venues.find_venues": "`src_test_down` in `where.query` → upstream_unreachable.",
           "trip.hold": "`off_test_price_jump` → the next hold's price changes, so an earlier approval is void (payload_changed).",
           "trip.complete": "`off_test_sold_out` → upstream_refused · `off_test_timeout_before` → upstream_timeout · `off_test_timeout_after` → outcome_unknown (poll acts.status).",
           "approvals.request": "Destinations `+1 500 555 0xxx` / `@example.test`: the link is captured — read it with sandbox.messages.",
           "messages.send_whatsapp": "Reply as the recipient with sandbox.simulate_reply (YES, NO, STOP…).",
           "messages.send_email": "Captured, never sent: read it with sandbox.messages.",
           "keep.use": "Any purpose other than fill / show (raw, value, reveal…) → invalid_input, rule never_raw."}

NAV = [("Start here", [("/docs", "What AgAPI does"), ("/docs/quickstart", "Quickstart"), ("/docs/test-and-live", "Test and live")]),
       ("Concepts", [("/docs/concepts/envelope", "The envelope"), ("/docs/concepts/read-back", "The read-back"), ("/docs/concepts/approvals", "Your user's yes"),
                     ("/docs/concepts/evidence", "Evidence"), ("/docs/concepts/idempotency", "Idempotency"), ("/docs/concepts/outages", "Outages"),
                     ("/docs/concepts/untrusted", "Untrusted text"), ("/docs/concepts/keep", "The Keep")]),
       ("Reference", [("/docs/operations", "Operations"), ("/docs/errors", "Errors"), ("/docs/webhooks", "Webhooks"), ("/docs/test-switches", "Test switches"),
                      ("/docs/mcp", "For AI agents (MCP)"), ("/docs/changelog", "Changelog"), ("/docs/go-live", "Go-live checklist"),
                      ("/docs/reference", "One-page reference")])]

CSS = """:root{--bg:#fbfaf7;--fg:#1c1a16;--mut:#6b665c;--line:#e4e0d6;--card:#fff;--acc:#1f5f8b;--code:#f3f1ec}
@media (prefers-color-scheme:dark){:root{--bg:#121110;--fg:#f1eee7;--mut:#a39e93;--line:#2c2a26;--card:#1b1a17;--acc:#7cc4e4;--code:#22201c}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:16px/1.6 -apple-system,system-ui,sans-serif}
.wrap{display:grid;grid-template-columns:15rem minmax(0,1fr);gap:2rem;max-width:72rem;margin:0 auto;padding:1rem}
nav{position:sticky;top:1rem;align-self:start;font-size:.93rem}nav b{display:block;margin:1rem 0 .3rem;color:var(--mut);font-size:.78rem;letter-spacing:.06em;text-transform:uppercase}
nav a{display:block;padding:.15rem 0;color:var(--fg);text-decoration:none}nav a.on{color:var(--acc);font-weight:600}a{color:var(--acc)}
main{min-width:0}h1{font-size:1.7rem;margin:.4rem 0 .6rem}h2{margin-top:1.8rem}code{background:var(--code);padding:.08rem .3rem;border-radius:5px;font-size:.9em}
pre{background:var(--code);padding:.9rem 1rem;border-radius:10px;overflow:auto;font-size:.86rem;line-height:1.45}pre code{background:none;padding:0}
table{border-collapse:collapse;width:100%;margin:.6rem 0;font-size:.93rem;display:block;overflow-x:auto}th,td{border-bottom:1px solid var(--line);padding:.45rem .55rem;text-align:left;vertical-align:top}
.badges span{display:inline-block;border:1px solid var(--line);border-radius:99px;padding:.1rem .6rem;margin:0 .3rem .3rem 0;font-size:.82rem}
.top{display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid var(--line);padding:.8rem 1rem}.top a{text-decoration:none;color:var(--fg);font-weight:700}
.tag{font-size:.75rem;border:1px solid var(--line);border-radius:99px;padding:.1rem .6rem;color:var(--mut)}
@media (max-width:860px){.wrap{grid-template-columns:1fr}nav{position:static}}"""


def page(path: str, title: str, body: str) -> HTMLResponse:
    nav = "".join(f"<b>{H(g)}</b>" + "".join(f'<a href="{u}"{" class=on" if u == path else ""}>{H(t)}</a>' for u, t in items) for g, items in NAV)
    return HTMLResponse(f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{H(title)} · AgAPI docs</title><style>{CSS}</style></head><body><div class="top"><a href="/docs">AgAPI</a>
<span class="tag">v{H(config.SPEC_DRAFT)} · sandbox · test mode</span></div><div class="wrap"><nav>{nav}</nav><main>{body}</main></div></body></html>""",
                        headers={"Cache-Control": "no-cache"})


# ── 1 · Start here ──────────────────────────────────────────────────────────────────────────────────────────────────────

@router.get("/docs", response_class=HTMLResponse)
async def start():
    return page("/docs", "What AgAPI does", f"""<h1>What AgAPI does</h1>
<p><b>Find things your users want. Hold one and show your user exactly what will happen. Act only after <i>their own</i> yes, once, and keep proof.</b></p>
<p>One API for flights, stays, restaurants, messages and a personal vault (the Keep), with the rules that make an AI agent safe to let act:
a read-back the user approves word for word, a yes that only the user's own device can give, every act exactly once, an outage never
dressed up as “no results”, and verifiable evidence for everything.</p>
<h2>The 2-minute demo</h2><p><a href="/demo">Open the live demo console</a> — a booking from search to proof, with the user's phone beside it.</p>
<iframe src="/demo" title="The AgAPI demo" style="width:100%;height:560px;border:1px solid var(--line);border-radius:12px"></iframe>
<h2>Next</h2><ul><li><a href="/docs/quickstart">Your first booking in 5 minutes</a> (curl · TypeScript · Python)</li>
<li><a href="/docs/concepts/approvals">Your user's yes</a> — the one rule you must not get wrong</li><li><a href="/docs/operations">All {len(operations())} operations</a></li></ul>
<p>Machine-readable: <a href="/openapi.json">/openapi.json</a> · <a href="/mcp.json">/mcp.json</a> · <a href="/collection.http">/collection.http</a></p>""")


@router.get("/docs/quickstart", response_class=HTMLResponse)
async def quickstart():
    sec = _section(journey(), "## Step 4", "## Step 5")
    return page("/docs/quickstart", "Quickstart", "<h1>Quickstart: your first booking in 5 minutes</h1>"
                "<p><b>Every snippet below runs in the sandbox's CI, as published, before this page ships.</b></p>" + md(sec.split("\n", 1)[1]))


@router.get("/docs/test-and-live", response_class=HTMLResponse)
async def test_and_live():
    return page("/docs/test-and-live", "Test and live", md("""# Test mode and live mode

| | Test | Live |
|---|---|---|
| Key prefix | `agp_test_` | `agp_live_` |
| Money | Stripe test | real |
| Messages | captured, read via `sandbox.messages` | sent |
| Venues | fixtures, never contacted | not open |
| Approvals | real link **or** simulated | real only |

**Live is not open yet.** Everything on this sandbox is test mode: no money moves, no message leaves, no venue is contacted."""))


# ── 2 · Concepts ────────────────────────────────────────────────────────────────────────────────────────────────────────

CONCEPTS = {
 "envelope": ("The envelope: every request, every answer", """Every call is `POST /v1/{operation}` with the operation's input as the JSON body.

- **Headers:** `Authorization: Bearer agp_…` · `AgAPI-Version` · `Idempotency-Key` (acts) · `AgAPI-Approval-Id` (acts that need the user's yes) · `AgAPI-Request-Id` (optional).
- **The answer is always** `{agapi, request_id, ok, result | error, trace}`, whatever the HTTP status.
- **Unknown request fields are refused** (`invalid_input`); **unknown response fields must be ignored** — 1.x only ever adds.

```json
{"agapi": "1.2", "request_id": "req_…", "ok": false,
 "error": {"code": "approval_required", "message": "…", "retryable": false, "details": {"read_back_id": "rb_…", "read_back": {"lines": ["…"]}}},
 "trace": {"operation": "trip.complete", "agent": "austen", "ms": 12, "upstream": [], "cost_units": 0}}
```"""),
 "read-back": ("The read-back: what your user approves, line by line", """`trip.hold` re-checks every item with its provider and returns `read_back.lines`.

- **Show them verbatim.** Don't summarise, translate or restyle the words.
- The read-back is approvable for **30 minutes** after it's presented (15 when the act is irreversible).
- Its `read_back_sha256` covers the lines AND the payload: change either, and a yes given to it is **void**."""),
 "approvals": ("Your user's yes", """Approvals come **only from the user's device**: AgAPI's single-use link (SMS, WhatsApp, email), the SDK, or Sasha. **There is no approve operation: no API key can approve.**

- The yes is a **separate action** after the read-back is shown (never the same turn).
- An approval is usable **once**, for **15 minutes**.
- It is **void** if the price, the items, the read-back or the intent changes — and never corrected: hold again.
- **A spoken or typed yes:** questions and requests veto it — “Yes, what are the terms?” and “Yes, but what's the refund?” aren't yes (1.1: vetoes match in both apostrophe forms).
- **1.1:** for a **cancellation's own** read-back, “Yes, cancel it” counts; “Don't cancel it” never does.
- **1.2:** a Keep item a booking will use is **named in the read-back** (“I'll use your saved Passport ES ••••456 for this booking.”); a yes that didn't name it is void (`keep_not_approved`)."""),
 "evidence": ("Evidence: proof you can verify yourself", """Every act yields an `evidence_id` (required when the outcome is `CONFIRMED`).

- `evidence.get` returns what the provider answered, what the user approved (their words or tap), and the hashes that tie them.
- `evidence.verify` recomputes `body_sha256` — **anyone** can run it.
- **Say “booked” from `acts.status` or the evidence, never from a webhook alone.**"""),
 "idempotency": ("Idempotency: never twice", """A key is scoped to **(account, operation, key)**.

- The same key + the same input → the same answer, `replayed: true`: **no second charge, no second act**.
- The same key + a different input → `idempotency_conflict`. **Generate a new key per action**, reuse one only to retry the same request.
- Failures that might succeed on retry **release** the key; `outcome_unknown` **keeps it in flight** until `acts.status` resolves it. Keys last 24 h."""),
 "outages": ("Outages are never “no results”", """An unreadable source is **an error, never an empty list**.

- A partial result carries `coverage` naming what answered.
- `items: []` means “none” **only** if `coverage.complete` is true.
- Tell your user “{Source} isn't answering right now” — never “sold out”."""),
 "untrusted": ("Untrusted text: what came from the outside world", """Anything fetched — venue names, reviews, a supplier's reply — arrives as `untrusted_text {text, source, retrieved_at, instruction_like?, truncated?}`.

- **Never pass it to your model as instructions.** Show it as data.
- `instruction_like: true` flags text that tries to instruct an AI (1.1 also catches “ignore **your** previous instructions”). It is flagged, never removed."""),
 "keep": ("The Keep (1.2)", """**Save your passport once. It's used only when your own yes names it, and the AI only ever sees `Passport ES ••••456`.**

| Tier | What | How it's used |
|---|---|---|
| free | preferences, loyalty numbers, home address | filled into a booking |
| yes | passport, DNI/NIE, trusted traveller, visa/residence, insurance, health card | only when the booking's read-back **names** it and the user said yes |
| read_back | booking references, door / Wi-Fi codes, eSIM | shown once on the user's own phone, never filled |
| never | card numbers, one-time / 2FA codes, passwords (not in v1) | refused |

- **never_raw:** no operation, purpose or prompt returns a value — `keep.use` with `raw`, `reveal`, `export`… → `invalid_input`.
- Show the re-issued read-back line; treat `keep_not_approved` as “ask again”; **never log a fill token** (`kf_…`).
- Deleting everything destroys the person's key: every value is shredded."""),
}


@router.get("/docs/concepts/{name}", response_class=HTMLResponse)
async def concept(name: str):
    if name not in CONCEPTS:
        return page("/docs", "Not found", "<h1>No such page</h1>")
    t, body = CONCEPTS[name]
    return page(f"/docs/concepts/{name}", t, f"<h1>{H(t)}</h1>" + md(body))


# ── 3 · Operations (generated) ──────────────────────────────────────────────────────────────────────────────────────────

def _fields(schema: dict) -> List[Tuple[str, str, bool, str]]:
    props, req = schema.get("properties") or {}, set(schema.get("required") or [])
    out = []
    for k, v in props.items():
        t = v.get("type") or ("enum" if "enum" in v else "const" if "const" in v else "object" if "properties" in v else "oneOf" if "oneOf" in v else "")
        if isinstance(t, list):
            t = " | ".join(t)
        note = v.get("description") or ""
        if "enum" in v:
            note = ("one of: " + ", ".join(map(str, v["enum"])) + (" — " + note if note else ""))
        if "pattern" in v:
            note = (note + " · " if note else "") + f"pattern {v['pattern']}"
        out.append((k, str(t), k in req, note))
    return out


def _example(schema: dict, depth: int = 0) -> Any:
    if depth > 4:
        return "…"
    if "const" in schema:
        return schema["const"]
    if "enum" in schema:
        return schema["enum"][0]
    if "oneOf" in schema:
        return _example(schema["oneOf"][0], depth + 1)
    t = schema.get("type")
    if isinstance(t, list):
        t = t[0]
    if t == "object" or "properties" in schema:
        props, req = schema.get("properties") or {}, schema.get("required") or list((schema.get("properties") or {}))[:3]
        return {k: _example(props[k], depth + 1) for k in req if k in props}
    if t == "array":
        return [_example(schema.get("items") or {}, depth + 1)]
    if t == "integer":
        return schema.get("minimum", 1)
    if t == "boolean":
        return True
    if t == "string":
        p = schema.get("pattern") or ""
        m = re.match(r"^\^([a-z]+)_", p)
        if m:
            return f"{m.group(1)}_…"
        if schema.get("format") == "date-time" or p == "Z$":
            return "2026-11-20T21:00:00Z"
        return "…"
    return None


def _table(rows: List[Tuple[str, str, bool, str]]) -> str:
    if not rows:
        return "<p>No fields.</p>"
    return "<table><tr><th>Field</th><th>Type</th><th>Required</th><th>Notes</th></tr>" + "".join(
        f"<tr><td><code>{H(k)}</code></td><td>{H(t)}</td><td>{'yes' if r else ''}</td><td>{H(n)}</td></tr>" for k, t, r, n in rows) + "</table>"


@router.get("/docs/operations", response_class=HTMLResponse)
async def ops_index():
    ops = operations()
    body = "<h1>Operations</h1><p>Every call is <code>POST /v1/{operation}</code>. Generated from <code>operations.json</code> "
    body += f"{H(config.SPEC_DRAFT)} and its schemas — the same source as <a href='/openapi.json'>/openapi.json</a>.</p>"
    seen = set()
    for g, names in GROUPS:
        body += f"<h2>{H(g)}</h2><table><tr><th>Operation</th><th>What it does</th><th>Approval</th></tr>"
        for n in names:
            if n in ops:
                seen.add(n)
                body += f"<tr><td><a href='/docs/operations/{H(n)}'><code>{H(n)}</code></a></td><td>{H(gen.DESCRIPTIONS.get(n, '').split('. ')[0])}.</td><td>{'yes' if ops[n]['requires_approval'] else ''}</td></tr>"
        body += "</table>"
    rest = [n for n in ops if n not in seen]
    if rest:
        body += "<h2>More</h2><ul>" + "".join(f"<li><a href='/docs/operations/{H(n)}'><code>{H(n)}</code></a></li>" for n in rest) + "</ul>"
    return page("/docs/operations", "Operations", body)


@router.get("/docs/operations/{name}", response_class=HTMLResponse)
async def op_page(name: str):
    ops = operations()
    if name not in ops:
        return page("/docs/operations", "Not found", "<h1>No such operation</h1>")
    o = ops[name]
    inp, out = resolved(o["input"]), resolved(o["output"])
    units = config.COST_UNITS.get(o["cost_class"], 0)
    badges = [f"agent: {o['agent']}", f"cost: {o['cost_class']} ({units} unit{'s' if units != 1 else ''})",
              "needs the user's approval" if o["requires_approval"] else "no approval", "idempotent — send an Idempotency-Key" if o["idempotent"] else "not idempotent",
              f"since {o.get('since', '1.0')}"] + (["test only"] if o.get("test_only") or name.startswith("sandbox.") else [])
    ex_in = _example(inp)
    curl = (f'curl -s {config.PUBLIC_URL}/v1/{name} \\\n  -H "Authorization: Bearer $AGAPI_KEY" -H "Content-Type: application/json" -H "AgAPI-Version: {config.SPEC_DRAFT}"'
            + (' \\\n  -H "Idempotency-Key: $(uuidgen | tr -d -)"' if o["idempotent"] else "") + (' \\\n  -H "AgAPI-Approval-Id: apv_…"' if o["requires_approval"] else "")
            + f" \\\n  -d '{json.dumps(ex_in, ensure_ascii=False)}'")
    errs = "".join(f"<tr><td><a href='/docs/errors#{H(c)}'><code>{H(c)}</code></a></td><td>{H(SHOW.get(c, ('', ''))[0])}</td></tr>" for c in o.get("errors") or [])
    test = TEST_IT.get(name)
    body = (f"<h1><code>{H(name)}</code></h1><p><b>{H(gen.DESCRIPTIONS.get(name, ''))}</b></p><div class='badges'>" + "".join(f"<span>{H(b)}</span>" for b in badges) + "</div>"
            f"<h2>Request</h2><pre><code>{H(curl)}</code></pre>{_table(_fields(inp))}"
            f"<h2>Response <code>result</code></h2><pre><code>{H(json.dumps(_example(out), indent=2, ensure_ascii=False))}</code></pre>{_table(_fields(out))}"
            f"<h2>Errors this operation can return</h2><table><tr><th>Code</th><th>What to show your user</th></tr>{errs}</table>"
            + (f"<h2>Test it</h2>{md(test)}" if test else ""))
    return page("/docs/operations", name, body)


# ── 4 · Errors ──────────────────────────────────────────────────────────────────────────────────────────────────────────

@router.get("/docs/errors", response_class=HTMLResponse)
async def errors_page():
    codes = json.loads((SPEC / "v1" / "error-codes.json").read_text())["codes"]
    body = f"<h1>Errors</h1><p>All {len(codes)} codes, grouped, each with <b>what to show your user</b>. Generated from <code>error-codes.json</code>.</p>"
    for cat in ("request", "auth", "limits", "idempotency", "approval", "upstream", "outcome", "domain", "internal"):
        rows = [c for c in codes if c["category"] == cat]
        if not rows:
            continue
        body += f"<h2>{H(cat.capitalize())}</h2><table><tr><th>Code</th><th>HTTP</th><th>Retry</th><th>What to show your user</th><th>What to do</th></tr>"
        for c in rows:
            show, do = SHOW.get(c["code"], ("", ""))
            body += (f"<tr id='{H(c['code'])}'><td><code>{H(c['code'])}</code><br><span style='color:var(--mut)'>{H(c['meaning'])}</span></td>"
                     f"<td>{c['http']}</td><td>{'yes' if c['retryable'] else ''}</td><td>{H(show)}</td><td>{H(do)}</td></tr>")
        body += "</table>"
    return page("/docs/errors", "Errors", body)


# ── 5 · Webhooks (the verification snippets are run against EU's webhook-signature.json vectors in CI) ─────────────────

WEBHOOK_SNIPPETS = {
 "python": '''import hashlib, hmac, time

def verify(secret: str, header: str, raw_body: str, now: int | None = None, tolerance: int = 300) -> bool:
    parts = dict(p.split("=", 1) for p in header.split(","))
    t, sig = int(parts["t"]), parts["v1"]
    if abs((now or int(time.time())) - t) > tolerance:
        return False                       # older than 5 minutes: a replay
    want = hmac.new(secret.encode(), f"{t}.{raw_body}".encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(want, sig)''',
 "node": '''import { createHmac, timingSafeEqual } from "node:crypto";

export function verify(secret, header, rawBody, now = Math.floor(Date.now() / 1000), tolerance = 300) {
  const parts = Object.fromEntries(header.split(",").map(p => p.split("=", 2)));
  const t = Number(parts.t);
  if (Math.abs(now - t) > tolerance) return false;          // older than 5 minutes: a replay
  const want = createHmac("sha256", secret).update(`${t}.${rawBody}`).digest("hex");
  return want.length === parts.v1.length && timingSafeEqual(Buffer.from(want), Buffer.from(parts.v1));
}''',
 "go": '''func Verify(secret, header, rawBody string, now int64) bool {
	var t int64; var sig string
	for _, p := range strings.Split(header, ",") {
		kv := strings.SplitN(p, "=", 2)
		if kv[0] == "t" { t, _ = strconv.ParseInt(kv[1], 10, 64) } else if kv[0] == "v1" { sig = kv[1] }
	}
	if now-t > 300 || t-now > 300 { return false }            // older than 5 minutes: a replay
	m := hmac.New(sha256.New, []byte(secret)); m.Write([]byte(fmt.Sprintf("%d.%s", t, rawBody)))
	return hmac.Equal([]byte(hex.EncodeToString(m.Sum(nil))), []byte(sig))
}'''}


@router.get("/docs/webhooks", response_class=HTMLResponse)
async def webhooks_page():
    ev = json.loads((SPEC / "v1" / "schemas" / "product" / "product.schema.json").read_text())["$defs"]["webhook_event"]["properties"]["event"]["enum"]
    snip = "".join(f"<h3>{H(k.capitalize())}</h3><pre><code>{H(v)}</code></pre>" for k, v in WEBHOOK_SNIPPETS.items())
    return page("/docs/webhooks", "Webhooks", md("""# Webhooks

Register up to **2** https endpoints with `webhooks.register` (that's how a secret is rotated). The signing secret (`whsec_…`) is in that response only.

- **Payload:** ids and states only — never personal data, never upstream text. Fetch details with your key.
- **Signature:** `AgAPI-Signature: t=…,v1=…` — HMAC-SHA256 over `"<t>.<raw body>"` with your secret. **Reject if older than 5 minutes.**
- **Delivery:** at least once; de-duplicate on `webhook_id`; no ordering guarantee; retries for 24 h.
- **1.1:** `message.replied` carries `data.reply_id` and the `intent_id` of the send that opened the conversation — fetch the text with `messages.replies`.""") +
                "<h2>Events</h2><ul>" + "".join(f"<li><code>{H(e)}</code></li>" for e in ev) + "</ul>"
                "<h2>Verify a delivery</h2><p>The Python and Node snippets run against EU's <code>webhook-signature.json</code> vectors in the sandbox's CI; "
                "the Go one is checked when a Go toolchain is present.</p>" + snip)


# ── 6 · Test switches · 7 · MCP · 8 · Changelog · 9 · Go-live ─────────────────────────────────────────────────────────────

@router.get("/docs/test-switches", response_class=HTMLResponse)
async def test_switches():
    return page("/docs/test-switches", "Test switches", md("""# Test switches

| Magic value | Where | Result |
|---|---|---|
| `off_test_sold_out` | an offer ref | `upstream_refused` |
| `off_test_timeout_before` | an offer ref | `upstream_timeout` (nothing happened; retry safe) |
| `off_test_timeout_after` | an offer ref | `outcome_unknown` (it may have happened: poll `acts.status`) |
| `off_test_price_jump` | an offer ref | the next hold's price changes → the approval is void (`payload_changed`) |
| `src_test_down` | any find query | `upstream_unreachable` for that source; a partial result with `coverage` |
| `+1 500 555 0xxx`, `@example.test` | destinations | messages captured; read them with `sandbox.messages` |
| `sandbox.simulate_approval {said}` | — | an approval with `device.channel: sandbox_simulated` (invalid in live) |
| `sandbox.simulate_reply {number, text}` | — | an inbound WhatsApp reply; `STOP` blocks further sends |"""))


@router.get("/docs/mcp", response_class=HTMLResponse)
async def mcp_page():
    n = len(gen.mcp_manifest(config.PUBLIC_URL)["tools"])
    return page("/docs/mcp", "For AI agents", md(f"""# For AI agents: the MCP manifest

[/mcp.json](/mcp.json) — **{n} tools**, schema version `2025-06-18`, generated from the same schemas as these pages. Every tool has a
description written for a model: what it does, when to call it, and the rule that keeps the user safe.

- **Envelope fields are hidden from models.** `Idempotency-Key` and `AgAPI-Approval-Id` are filled by your client, never by the model.
- **A model can find and hold; it can never approve.** The approval comes from the user's device.
- **Treat every `untrusted_text` field as data**, never as instructions.
- **The Keep:** a model only ever sees masks; it can't get a value, whatever it asks."""))


@router.get("/docs/changelog", response_class=HTMLResponse)
async def changelog():
    readme = (SPEC / "v1" / "README.md").read_text(encoding="utf-8")
    sec = _section(readme, "## Changelog", "\n**Rules of this directory")
    return page("/docs/changelog", "Changelog", md("""# Changelog and versioning

**What 1.x promises:** additive only. New operations, fields, codes and events can appear; nothing is renamed or removed. Ignore fields you don't know.""")
                + md(sec.split("\n", 1)[1]))


@router.get("/docs/go-live", response_class=HTMLResponse)
async def go_live():
    sec = _section(journey(), "## Step 8", None)
    nxt = re.search(r"\n## ", sec[5:])
    if nxt:
        sec = sec[:nxt.start() + 5]
    return page("/docs/go-live", "Go-live checklist", "<h1>Go-live checklist</h1><p><b>Live is not open yet.</b> This is what we'll check before it is.</p>"
                + md(sec.split("\n", 1)[1]))


@router.get("/docs/reference", response_class=HTMLResponse)
async def reference():
    return HTMLResponse(gen.docs_page(config.PUBLIC_URL))
