"""Sasha 329 · CR 161 · THE SANDBOX PROOF — agapi-SANDBOX only, Kanoe's own stand-in platform page (never a real venue).

The loop Sasha now runs, op by op, against the sandbox's own stand-in CoverManager widget (sandbox.platform_prepare, variant "lists"):
  1 users.register (S329_EXTERNAL_REF — a beta person: their access must already carry platform_submit)
  2 sandbox.platform_prepare, NO choices                        → decision fill_platform_form (else: said, and it stops)
  3 venue.submit_booking {prepared_id}                           → approval_required (the read-back)
  4 sandbox.simulate_approval "Yes, book it."                    → the approval
  5 venue.submit_booking + approval                              → failed + ask {choice, label, options}
  6 venue.submit_booking {SAME prepared_id, choices {<choice>: <first option>}} → approval_required, the choice on the read-back
  7 approval → venue.submit_booking {prepared_id, choices} + approval → confirmed (act_id, reference)
  8 venue.cancel_booking {act_id} → approval_required → "Yes, cancel it." → venue.cancel_booking + approval → cancelled
  9 venue.booking_status {act_id}                                → state cancelled
Every step's status is printed; the key never is. Exit 0 only when every step held.

Run it (from ~/Developer/agapi, with a minted sandbox TEST key — never printed):
    cd ~/Developer/agapi && S329_SANDBOX_KEY=<the minted agp_test_ key> S329_EXTERNAL_REF=<the beta person's external_ref> \\
      npx @railway/cli run --service agapi-sandbox -- \\
      python3 ~/Developer/Sasha-travel-/backend/scripts/s329_sandbox_proof.py
Optional: S329_SANDBOX_URL (default https://agapi-sandbox-production.up.railway.app), S329_DATE (default 2026-11-20), S329_TIME (22:00).
"""
from __future__ import annotations

import json
import os
import secrets
import sys
from typing import Any, Dict, Optional, Tuple

import httpx

URL = (os.environ.get("S329_SANDBOX_URL") or "https://agapi-sandbox-production.up.railway.app").rstrip("/")
KEY = os.environ.get("S329_SANDBOX_KEY") or ""
REF = os.environ.get("S329_EXTERNAL_REF") or ""
DAY = os.environ.get("S329_DATE") or "2026-11-20"
HHMM = os.environ.get("S329_TIME") or "22:00"
PERSON = {"name": "S329 Proof", "phone": "+15005550142", "email": "s329.proof@example.test"}   # fictional: a 555-01xx number, example.test
TIMEOUT_S = 150.0   # the stand-in walk opens a real browser on the sandbox


class Failed(Exception):
    pass


def post(c: httpx.Client, op: str, body: dict, approval: Optional[str] = None) -> Tuple[int, Dict[str, Any]]:
    """AgAPI's envelope, as backend/agapi/agapi_route.post sends it: Bearer key, a fresh Idempotency-Key, the approval when there is one."""
    h = {"Authorization": f"Bearer {KEY}", "content-type": "application/json", "Idempotency-Key": "s329proof_" + secrets.token_hex(12)}
    if approval:
        h["AgAPI-Approval-Id"] = approval
    r = c.post(f"{URL}/v1/{op}", headers=h, content=json.dumps(body))
    try:
        env = r.json()
    except Exception:
        env = {"ok": False, "error": {"code": "unreachable", "message": f"HTTP {r.status_code}"}}
    return r.status_code, env


def step(n: Any, what: str, status: Any, extra: str = "") -> None:
    print(f"[{n}] {what}: {status}" + (f" · {extra}" if extra else ""), flush=True)


def need(cond: bool, why: str) -> None:
    if not cond:
        raise Failed(why)


def read_back(c: httpx.Client, op: str, body: dict, n: Any) -> Tuple[str, list]:
    code, env = post(c, op, body)
    e = env.get("error") or {}
    step(n, f"{op} (no approval)", e.get("code") or (env.get("result") or {}).get("status") or code)
    need(e.get("code") == "approval_required", f"{op} gave no read-back: {e.get('code') or (env.get('result') or {}).get('status')}")
    d = e.get("details") or {}
    lines = list((d.get("read_back") or {}).get("lines") or d.get("lines") or [])
    need(bool(d.get("read_back_id")) and bool(lines), "the read-back had no id or no lines")
    for ln in lines:
        print(f"      read-back: {ln}", flush=True)
    return d["read_back_id"], lines


def approve(c: httpx.Client, rid: str, said: str, n: Any) -> str:
    code, env = post(c, "sandbox.simulate_approval", {"read_back_id": rid, "said": said})
    res = env.get("result") or {}
    step(n, f"sandbox.simulate_approval “{said}”", res.get("state") or (env.get("error") or {}).get("code") or code)
    need(bool(env.get("ok")) and bool(res.get("approval_id")), "no approval")
    return res["approval_id"]


def main() -> int:
    if not KEY:
        print("S329_SANDBOX_KEY is not set (a minted sandbox TEST key — never printed).", file=sys.stderr)
        return 2
    if not KEY.startswith("agp_test_"):
        print("S329_SANDBOX_KEY is not a TEST key: this proof runs on the sandbox only.", file=sys.stderr)
        return 2
    if not REF:
        print("S329_EXTERNAL_REF is not set (the beta person's external_ref).", file=sys.stderr)
        return 2
    if "sandbox" not in URL:
        print(f"S329_SANDBOX_URL must be agapi-SANDBOX (got {URL}).", file=sys.stderr)
        return 2
    print(f"Sasha 329 · CR 161 proof on {URL} · {DAY} {HHMM} · 2 people", flush=True)
    with httpx.Client(timeout=httpx.Timeout(TIMEOUT_S)) as c:
        code, env = post(c, "users.register", {"external_ref": REF})
        eu = (env.get("result") or {}).get("end_user_id")
        step(1, "users.register", "ok" if eu else (env.get("error") or {}).get("code") or code)
        need(bool(eu), "no end user")

        code, env = post(c, "sandbox.platform_prepare", {"end_user": eu, "date": DAY, "time": HHMM, "party": 2, "variant": "lists",
                                                          "person": PERSON})
        p = env.get("result") or {}
        step(2, "sandbox.platform_prepare (no choices)", p.get("decision") or (env.get("error") or {}).get("code") or code)
        need(bool(p.get("prepared_id")), "nothing prepared")
        if p.get("decision") != "fill_platform_form":
            print(f"STOP: decision is {p.get('decision')!r}, not 'fill_platform_form' — this person is not in the platform beta "
                  f"(their access needs platform_submit). AgAPI said: {p.get('say')}", flush=True)
            return 3
        pid = p["prepared_id"]

        rid, _ = read_back(c, "venue.submit_booking", {"end_user": eu, "prepared_id": pid}, 3)
        apv = approve(c, rid, "Yes, book it.", 4)
        code, env = post(c, "venue.submit_booking", {"end_user": eu, "prepared_id": pid}, approval=apv)
        r = env.get("result") or {}
        ask = r.get("ask") if isinstance(r.get("ask"), dict) else {}
        step(5, "venue.submit_booking + approval", r.get("status") or (env.get("error") or {}).get("code") or code,
             f"ask {json.dumps(ask, ensure_ascii=False)}" if ask else "")
        need(r.get("status") == "failed" and bool(ask.get("choice")) and bool(ask.get("options")),
             f"expected failed + ask, got {r.get('status')} (say: {r.get('say')})")
        choice, pick = str(ask["choice"]), str(ask["options"][0])

        body = {"end_user": eu, "prepared_id": pid, "choices": {choice: pick}}
        rid, lines = read_back(c, "venue.submit_booking", body, 6)
        need(any(f"{choice}: {pick}" in ln for ln in lines), f"the read-back doesn't carry “{choice}: {pick}”")
        apv = approve(c, rid, "Yes, book it.", "7a")
        code, env = post(c, "venue.submit_booking", body, approval=apv)
        r = env.get("result") or {}
        step("7b", "venue.submit_booking {same prepared_id, choices} + approval", r.get("status") or (env.get("error") or {}).get("code") or code,
             f"act {r.get('act_id')} · ref {r.get('reference')} · say: {r.get('say')}")
        need(r.get("status") == "confirmed" and bool(r.get("act_id")), f"not confirmed: {r.get('status')} (say: {r.get('say')})")
        aid = r["act_id"]

        rid, _ = read_back(c, "venue.cancel_booking", {"end_user": eu, "act_id": aid}, "8a")
        apv = approve(c, rid, "Yes, cancel it.", "8b")
        code, env = post(c, "venue.cancel_booking", {"end_user": eu, "act_id": aid}, approval=apv)
        r = env.get("result") or {}
        step("8c", "venue.cancel_booking + approval", r.get("status") or (env.get("error") or {}).get("code") or code, f"say: {r.get('say')}")
        need(r.get("status") == "cancelled", f"not cancelled: {r.get('status')} why {r.get('why')}")

        code, env = post(c, "venue.booking_status", {"act_id": aid})
        st = env.get("result") or {}
        step(9, "venue.booking_status", st.get("state") or (env.get("error") or {}).get("code") or code, f"say: {st.get('say')}")
        need(st.get("state") == "cancelled", f"the ONE record doesn't say cancelled: {st.get('state')}")
    print("PROOF HELD: ask → choices on the same prepared_id → confirmed → cancelled on the ONE record.", flush=True)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Failed as e:
        print(f"PROOF FAILED: {e}", flush=True)
        sys.exit(1)
    except httpx.HTTPError as e:
        print(f"PROOF FAILED: transport {type(e).__name__}", flush=True)
        sys.exit(1)
