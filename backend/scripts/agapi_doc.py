"""Sasha 203 · writes docs/agapi/api-v0.md FROM the contract (agapi/v0.py) — the doc is never written by hand, so it can't drift.
    python -m scripts.agapi_doc            (from backend/)"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "docs", "agapi", "api-v0.md")


def render() -> str:
    from agapi import v0 as API
    out = [f"# AgAPI {API.VERSION} — the contract",
           "",
           "*Generated from `backend/agapi/v0.py` by `backend/scripts/agapi_doc.py`. Do not edit by hand.*",
           "",
           "One contract for every client.",
           "",
           "- **Today:** Sasha's own agent at `/next` uses it.",
           "- **Later:** the same tools as a REST API (`POST /agapi/v0/{tool}`) and as an MCP server (one MCP tool per entry,",
           "  the same input schema).",
           "",
           "## Rules every call obeys",
           "",
           "- **Scope.** Every call runs for ONE account: the caller's authenticated account. It's never an id in the input.",
           "- **Mode.** `test` only in v0: Duffel TEST, Stripe TEST, TEST hotel bookings. `live` is refused with `mode_not_available`.",
           "- **Idempotency.** Austen's calls require `idempotency_key`. The same key returns the first result (`replayed: true`)",
           "  and never repeats the action.",
           "- **Explicit yes.** `book` requires `approval.said`: the person's own words in the current turn, an explicit yes",
           "  (\"Yes\", \"Then book it.\", \"Go ahead\"). Anything else is refused with `no_explicit_yes`. A client fills it",
           "  from the person's real message, never from a model.",
           "- **Truth.** Prices and totals only from results. Booked / paid / confirmed only from Pacioli (`get_status`).",
           "- **Errors.** Errors are `{\"ok\": false, \"error\": {\"code\", \"message\"}}`, honest, for the caller to explain.",
           "  Success is `{\"ok\": true, \"result\": …}`.",
           "",
           "## The agents",
           "",
           "| Agent | Role | Tools |",
           "|---|---|---|"]
    roles = {"Magellan": "finds", "Sherlock": "checks", "Austen": "acts (idempotent; book needs a yes)", "Pacioli": "records — the only source of booked/paid"}
    for ag in ("Magellan", "Sherlock", "Austen", "Pacioli"):
        out.append(f"| **{ag}** | {roles[ag]} | {', '.join('`' + t['name'] + '`' for t in API.TOOLS if t['agent'] == ag)} |")
    for ag in ("Magellan", "Sherlock", "Austen", "Pacioli"):
        out += ["", f"## {ag}"]
        for t in [t for t in API.TOOLS if t["agent"] == ag]:
            out += ["", f"### `{t['name']}`", "", t["description"], "",
                    f"**Errors:** {', '.join('`' + e + '`' for e in t['errors'] + ['missing_input', 'internal']) }"
                    + (" · **idempotent** (`idempotency_key` required)" if t["idempotent"] else ""), "",
                    "**Input**", "", "```json", json.dumps(t["input_schema"], indent=1, ensure_ascii=False), "```", "",
                    "**Output** (`result`)", "", "```json", json.dumps(t["output_schema"], indent=1, ensure_ascii=False), "```"]
    out += ["", "## Error envelope", "", "```json", json.dumps(API.ERR, indent=1), "```", ""]
    return "\n".join(out)


if __name__ == "__main__":
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    open(OUT, "w", encoding="utf-8").write(render())
    print("wrote", OUT)
