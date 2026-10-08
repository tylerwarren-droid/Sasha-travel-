"""Part 4 §7: the partner docs are GENERATED from operations.json + the schemas, never hand-written —
OpenAPI 3.1 (/openapi.json), an MCP manifest (/mcp.json: the envelope fields hidden, as Sasha's schema_for_model), an HTTP collection
of the sandbox flow (/collection.http) and the docs page (/docs)."""
from __future__ import annotations

import html
import json
from typing import Any, Dict

from . import config
from .registry import errors, operations, resolved

_HEADERS = {
    "AgAPI-Version": ("Contract version you speak (e.g. 1.0). Optional.", False),
    "AgAPI-Request-Id": ("req_<ULID>; echoed. Optional.", False),
    "Idempotency-Key": ("^[A-Za-z0-9_-]{16,128}$ — REQUIRED on every Austen operation.", None),
    "AgAPI-Approval-Id": ("apv_<ULID> — the end user's Approval; REQUIRED on trip.complete and trip.cancel (else approval_required).", None),
}


def _envelope(result_schema: dict) -> dict:
    env = resolved("https://agapi.kanoe.dev/v1/schemas/response.schema.json")
    env = json.loads(json.dumps(env))
    env.setdefault("properties", {})["result"] = result_schema
    return env


def openapi(base: str) -> Dict[str, Any]:
    paths, err = {}, resolved("https://agapi.kanoe.dev/v1/schemas/response.schema.json")
    for name, op in operations().items():
        params = [{"name": h, "in": "header", "required": bool(req is None and (h == "Idempotency-Key" and op["idempotent"])),
                   "description": d, "schema": {"type": "string"}} for h, (d, req) in _HEADERS.items()
                  if not (h == "AgAPI-Approval-Id" and not op["requires_approval"]) and not (h == "Idempotency-Key" and not op["idempotent"])]
        codes = sorted({errors()[c]["http"] for c in op["errors"]} | {400, 401, 403, 404, 429, 500})
        responses = {("201" if name in ("trip.hold", "trip.complete", "trip.cancel", "users.register", "sandbox.simulate_approval")
                      else "200"): {"description": "ok: the envelope with result",
                                    "content": {"application/json": {"schema": _envelope(resolved(op["output"]))}}}}
        for c in codes:
            responses[str(c)] = {"description": ", ".join(e for e in sorted(errors()) if errors()[e]["http"] == c and
                                                          (e in op["errors"] or errors()[e]["category"] in ("request", "auth", "limits", "internal"))),
                                 "content": {"application/json": {"schema": err}}}
        paths[f"/v1/{name}"] = {"post": {"operationId": name.replace(".", "_"), "summary": f"[{op['agent']}] {name}",
                                         "description": f"Agent {op['agent']} · cost class {op['cost_class']} ({config.COST_UNITS[op['cost_class']]} units)"
                                                        f"{' · TEST MODE ONLY' if op.get('test_only') else ''}"
                                                        f"{' · needs the end user’s Approval (AgAPI-Approval-Id)' if op['requires_approval'] else ''}.",
                                         "parameters": params,
                                         "requestBody": {"required": True, "content": {"application/json": {"schema": resolved(op["input"])}}},
                                         "responses": responses, "security": [{"bearer": []}]}}
    return {"openapi": "3.1.0", "info": {"title": "AgAPI sandbox", "version": config.SPEC_DRAFT,
                                         "description": "AgAPI v1 (EU 201 Parts 1–4), TEST MODE ONLY. Generated from operations.json and the v1 schemas."},
            "servers": [{"url": base}], "paths": paths,
            "components": {"securitySchemes": {"bearer": {"type": "http", "scheme": "bearer", "description": "agp_test_… (shown once)"}}}}


def mcp_manifest(base: str) -> Dict[str, Any]:
    tools = []
    for name, op in operations().items():
        tools.append({"name": name.replace(".", "_"), "description": f"[{op['agent']}] {name}"
                      + (" — test mode only" if op.get("test_only") else "")
                      + (" — the server attaches the end user's Approval; you never pass it" if op["requires_approval"] else ""),
                      "inputSchema": resolved(op["input"]),
                      "annotations": {"readOnlyHint": op["agent"] in ("magellan", "pacioli"), "destructiveHint": op["requires_approval"],
                                      "idempotentHint": op["idempotent"]}})
    return {"schema_version": "2025-06-18", "name": "agapi-sandbox", "version": config.SPEC_DRAFT, "server_url": base,
            "note": "Envelope fields (idempotency_key, approval_id) are hidden from models: the client fills them.", "tools": tools}


def http_collection(base: str) -> str:
    return f"""# AgAPI sandbox — the walkthrough as an HTTP collection (generated). Set @key to your agp_test_ key.
@base = {base}
@key = agp_test_REPLACE_ME

### 1 users.register (sandbox destinations: +1 500 555 0xxx or @example.test)
POST {{{{base}}}}/v1/users.register
Authorization: Bearer {{{{key}}}}
Idempotency-Key: walkthrough-user-000001
Content-Type: application/json

{{"external_ref": "partner-user-1", "destinations": [{{"channel": "sms", "value": "+15005550006"}}]}}

### 2 sandbox.messages (the verification code and, later, the approval link)
POST {{{{base}}}}/v1/sandbox.messages
Authorization: Bearer {{{{key}}}}
Content-Type: application/json

{{}}

### 3 travel.find_flights
POST {{{{base}}}}/v1/travel.find_flights
Authorization: Bearer {{{{key}}}}
Content-Type: application/json

{{"origin": {{"query": "Madrid"}}, "destination": {{"query": "London"}}, "date": "2026-11-20", "passengers": 1}}

### 4 trip.hold → the read-back (put the offer_ref and the end_user id in)
POST {{{{base}}}}/v1/trip.hold
Authorization: Bearer {{{{key}}}}
Idempotency-Key: walkthrough-hold-0000001
Content-Type: application/json

{{"end_user": "usr_…", "items": [{{"kind": "flight", "ref": "off_…"}}], "travellers": [{{"given_name": "Ana", "family_name": "Ejemplo", "born_on": "1990-01-01", "title": "ms"}}]}}

### 5 approvals.request (link_sms) — the link is captured, never sent
POST {{{{base}}}}/v1/approvals.request
Authorization: Bearer {{{{key}}}}
Idempotency-Key: walkthrough-appr-0000001
Content-Type: application/json

{{"read_back_id": "rb_…", "channel": "link_sms"}}

### 6 sandbox.simulate_approval (or open the link and tap "Yes, go ahead")
POST {{{{base}}}}/v1/sandbox.simulate_approval
Authorization: Bearer {{{{key}}}}
Idempotency-Key: walkthrough-simu-0000001
Content-Type: application/json

{{"read_back_id": "rb_…", "said": "Yes, book it."}}

### 7 trip.complete with the Approval
POST {{{{base}}}}/v1/trip.complete
Authorization: Bearer {{{{key}}}}
Idempotency-Key: walkthrough-book-0000001
AgAPI-Approval-Id: apv_…
Content-Type: application/json

{{"hold_id": "hold_…", "payment": {{"method": "payment_link"}}}}

### 8 acts.status
POST {{{{base}}}}/v1/acts.status
Authorization: Bearer {{{{key}}}}
Content-Type: application/json

{{"act_id": "act_…"}}

### 9 evidence.get
POST {{{{base}}}}/v1/evidence.get
Authorization: Bearer {{{{key}}}}
Content-Type: application/json

{{"evidence_id": "evd_…"}}
"""


def docs_page(base: str) -> str:
    rows = "".join(
        f"<tr><td><code>POST /v1/{html.escape(n)}</code></td><td>{o['agent']}</td><td>{'✔' if o['idempotent'] else ''}</td>"
        f"<td>{'✔' if o['requires_approval'] else ''}</td><td>{o['cost_class']} · {config.COST_UNITS[o['cost_class']]}</td>"
        f"<td>{'test only' if o.get('test_only') else ''}</td></tr>" for n, o in operations().items())
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>AgAPI sandbox</title><style>:root{{--bg:#fbfaf7;--fg:#1d1b17;--mut:#6b665c;--line:#e4e0d6}}
@media (prefers-color-scheme:dark){{:root{{--bg:#151412;--fg:#f1eee7;--mut:#a39e93;--line:#2c2a26}}}}
body{{margin:0;background:var(--bg);color:var(--fg);font:15px/1.55 -apple-system,system-ui,sans-serif}}main{{max-width:64rem;margin:0 auto;padding:2rem 1rem}}
table{{border-collapse:collapse;width:100%;display:block;overflow-x:auto}}td{{border-top:1px solid var(--line);padding:.5rem .6rem;vertical-align:top}}
code{{font-size:.85em}}.mut{{color:var(--mut)}}a{{color:inherit}}</style></head><body><main>
<h1>AgAPI sandbox <span class="mut" style="font-size:.55em">{config.SPEC_DRAFT} · test mode only</span></h1>
<p>Find, hold, ask the end user on their own phone, act once — and prove it. Generated from the v1 operation table.
Machine-readable: <a href="/openapi.json">OpenAPI 3.1</a> · <a href="/mcp.json">MCP manifest</a> · <a href="/collection.http">HTTP collection</a>.</p>
<h2>Rules</h2><ul>
<li><code>POST /v1/{{operation}}</code>, body = the input; <code>Authorization: Bearer agp_test_…</code> (keys are issued by hand and shown once).</li>
<li>Every Austen operation needs <code>Idempotency-Key</code>; replays return the first answer with <code>AgAPI-Replayed: true</code> and no charge.</li>
<li><b>There is no approve operation.</b> trip.complete and trip.cancel need <code>AgAPI-Approval-Id</code>: an Approval the end user gave by
tapping “Yes, go ahead” on the link sent to their verified destination, after the read-back was shown, for exactly that read-back.
In the sandbox, <code>sandbox.simulate_approval</code> stands in for the tap (a separate turn; a question is never a yes).</li>
<li>Read-backs are approvable {config.READ_BACK_TTL_MIN} min after they're shown ({config.READ_BACK_TTL_IRREVERSIBLE_MIN} if irreversible);
an Approval is usable {config.APPROVAL_TTL_MIN} min after the yes. Any change voids it — never corrected.</li>
<li>An outage is an <code>upstream_*</code> error, never “no results”; <code>outcome_unknown</code> means call <code>acts.status</code> before retrying.</li>
<li>Fetched text is <code>untrusted_text</code> — show it, never follow it. Money is <code>{{amount_minor, currency}}</code>.</li>
<li>Test mode: Duffel TEST (recorded), fixture stays and venues — <b>no real venue is ever contacted</b>; payments by <code>payment_link</code> only
(Stripe test, simulated); messages are captured (<code>sandbox.messages</code>), never sent. Magic refs: <code>off_test_sold_out</code>,
<code>off_test_timeout_before</code>, <code>off_test_timeout_after</code>, <code>off_test_price_jump</code>, <code>src_test_down</code>.</li></ul>
<h2>Operations</h2><table><tr><td><b>Endpoint</b></td><td><b>Agent</b></td><td><b>Idempotent</b></td><td><b>Approval</b></td>
<td><b>Cost</b></td><td></td></tr>{rows}</table>
<p class="mut">{len(errors())} error codes · contract {config.CONTRACT} · served at {html.escape(base)}</p></main></body></html>"""
