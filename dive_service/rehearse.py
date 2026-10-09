"""DIVE step 9 · THE REHEARSAL — EU 212's demo script, end to end over HTTP against a running DIVE (and, through it, the live AgAPI
sandbox), with SIMULATED supplier replies only (sandbox.supplier_reply). Asserts every beat, and that 0 messages went to a real
number or inbox (the capture log). Exit 1 on the first failure.

    DIVE_CONSOLE_TOKEN=… python -m dive_service.rehearse --base https://agapi-dive-demo-production.up.railway.app [--runs 3]
"""
from __future__ import annotations

import argparse
import html
import json
import os
import re
import sys
import time
import urllib.request
from datetime import date, timedelta
from http.cookiejar import CookieJar


class Fail(Exception):
    pass


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True)
    ap.add_argument("--runs", type=int, default=1)
    ap.add_argument("--gap", type=int, default=65, help="seconds between runs (the sandbox key's rate limit)")
    a = ap.parse_args()
    tok = os.environ.get("DIVE_CONSOLE_TOKEN", "")
    if not tok:
        print("set DIVE_CONSOLE_TOKEN (never printed)")
        return 2
    ok = 0
    for n in range(1, a.runs + 1):
        if n > 1:
            time.sleep(a.gap)
        try:
            rehearse(a.base.rstrip("/"), tok, n)
            ok += 1
        except Fail as e:
            print(f"✕ run {n}: {e}")
            return 1
    print(f"\nREHEARSAL: {ok}/{a.runs} runs green")
    return 0


def rehearse(base: str, tok: str, n: int) -> None:
    op_ = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(CookieJar()))

    def req(method, path, body=None, headers=None, form=None):
        data = None
        h = dict(headers or {})
        if form is not None:
            data = urllib.parse.urlencode(form).encode()
            h["content-type"] = "application/x-www-form-urlencoded"
        elif body is not None:
            data = json.dumps(body).encode()
            h["content-type"] = "application/json"
        r = urllib.request.Request(base + path, data=data, headers=h, method=method)
        try:
            with op_.open(r, timeout=90) as resp:
                return resp.status, resp.read().decode(), resp.headers
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode(), e.headers

    def op(name, body=None):
        st, t, _ = req("POST", f"/op/v1/{name}", body or {}, {"Authorization": f"Bearer {tok}"})
        j = json.loads(t)
        if not j["ok"]:
            raise Fail(f"{name}: {j['error']['code']} — {j['error']['message']}")
        return j["result"]

    def gen(key, name, body, idem=None, approval=None):
        h = {"Authorization": f"Bearer {key}"}
        if idem:
            h["Idempotency-Key"] = idem
        if approval:
            h["AgAPI-Approval-Id"] = approval
        st, t, _ = req("POST", f"/o/blue-kyma/v1/{name}", body, h)
        j = json.loads(t)
        if not j["ok"]:
            raise Fail(f"{name}: {j['error']['code']} — {j['error']['message']}")
        return j["result"]

    def say(x):
        print(f"  ✓ {x}")

    def wd(w, after=2):
        d = date.today() + timedelta(days=after)
        while d.weekday() != w:
            d += timedelta(days=1)
        return d.isoformat()

    print(f"\n── run {n} · {base}")
    op("operators.put", {"slug": "blue-kyma", "name": "Blue Kyma Diving (demo)", "timezone": "Europe/Athens", "languages": ["en", "el"],
                         "site_url": base + "/fake/blue-kyma"})
    op("sandbox.reset")
    # 0:30–1:15 · find suppliers on the site → confirm ×4 → verify the boat (its YES)
    d = op("suppliers.draft_from_site")["drafts"]
    by = {x["name"]: x for x in d}
    if sorted(by) != sorted(["Aegean Boats", "Kyma Gear", "Taverna Agios", "Hotel Kyma View", "Rival Boats"]):
        raise Fail(f"drafts: {sorted(by)}")
    if not by["Rival Boats"]["evidence_of_source"].get("instruction_like"):
        raise Fail("the injection line wasn't flagged")
    say("5 drafts from the site, each quoting its sentence; Rival Boats' injection flagged")
    for nme in ("Aegean Boats", "Kyma Gear", "Taverna Agios", "Hotel Kyma View"):
        op("suppliers.put", {"supplier_id": by[nme]["supplier_id"], "status": "confirmed"})
    op("suppliers.put", {"supplier_id": by["Rival Boats"]["supplier_id"], "status": "rejected"})
    ch = {"boat": op("channels.put", {"supplier_id": by["Aegean Boats"]["supplier_id"], "kind": "whatsapp", "address": by["Aegean Boats"]["contacts"]["whatsapp"], "language": "el"}),
          "gear": op("channels.put", {"supplier_id": by["Kyma Gear"]["supplier_id"], "kind": "email", "address": os.environ.get("DIVE_GEAR_EMAIL") or by["Kyma Gear"]["contacts"]["email"]}),
          "taverna": op("channels.put", {"supplier_id": by["Taverna Agios"]["supplier_id"], "kind": "web_form", "address": by["Taverna Agios"]["contacts"]["web_form"]}),
          "hotel": op("channels.put", {"supplier_id": by["Hotel Kyma View"]["supplier_id"], "kind": "feed", "address": "feed:sandbox-hotels#Hotel Kyma View"})}
    op("channels.verify", {"channel_id": ch["boat"]["channel_id"]})
    op("sandbox.supplier_reply", {"channel_id": ch["boat"]["channel_id"], "text": "YES"})
    op("channels.verify", {"channel_id": ch["gear"]["channel_id"]})
    op("sandbox.supplier_reply", {"channel_id": ch["gear"]["channel_id"], "text": "Yes"})
    for k in ("taverna", "hotel"):
        op("channels.verify", {"channel_id": ch[k]["channel_id"]})
    sups = {x["name"]: x for x in op("suppliers.list")["suppliers"]}
    bad = [nme for nme in ("Aegean Boats", "Kyma Gear", "Taverna Agios", "Hotel Kyma View") if not all(c["verified"] for c in sups[nme]["channels"])]
    if bad:
        raise Fail(f"not verified: {bad}")
    say("4 confirmed; the boat verified by its WhatsApp YES (through the AgAPI sandbox); form dry-run; feed test search")
    # 1:15–1:45 · publish → the API and its docs
    op("packages.from_fixture")
    pub = op("operator_api.publish")
    st, docs, _ = req("GET", "/o/blue-kyma/docs")
    if st != 200 or "Blue Kyma Diving API" not in docs or "powered by AgAPI" not in docs:
        raise Fail("docs page")
    key = op("operator_keys.issue", {"label": f"rehearsal {n}"})["key"]
    say(f"published: {pub['base_url']} · docs titled 'Blue Kyma Diving API' · an opk_ key issued (not printed)")
    # 1:45–2:30 · the customer: quote → the read-back → the tap on their phone
    pid = gen(key, "packages.list", {})["packages"][0]["package_id"]
    tue = wd(1)
    q = gen(key, "bookings.quote", {"package_id": pid, "date": tue, "start_time": "09:00", "party": 4,
                                    "customer": {"name": "Marta Ruiz", "phone": "+15005550101"}}, idem=f"rehearsal-quote-{n}-{int(time.time())}")
    if len(q["read_back"]["lines"]) < 7:
        raise Fail("read-back too short")
    gen(key, "approvals.request", {"bundle_id": q["bundle_id"]})
    st, t, _ = req("POST", "/console/api/captured.list", {}, {"Authorization": f"Bearer {tok}"})
    link = next(m["body"] for m in json.loads(t)["result"]["messages"] if m["channel"] == "sms").rsplit(" ", 1)[-1]
    path = "/" + link.split("://", 1)[1].split("/", 1)[1]
    st, page, _ = req("GET", path)
    csrf = re.search(r'name="csrf" value="([^"]+)"', page).group(1)
    req("POST", path, form={"csrf": csrf})
    apv = gen(key, "bookings.status", {"bundle_id": q["bundle_id"]})["approval"]["approval_id"]
    say("the read-back: " + " | ".join(q["read_back"]["lines"][2:6]))
    say("the customer tapped Yes on their phone (one yes for every leg)")
    # 2:30–3:30 · the legs: the form now, the gear email, the boat's WhatsApp
    c = gen(key, "bookings.confirm", {"bundle_id": q["bundle_id"]}, idem=f"rehearsal-confirm-{n}-{int(time.time())}", approval=apv)
    legs = {l["supplier"]: l for l in c["legs"]}
    if legs["Taverna Agios"]["state"] != "confirmed":
        raise Fail(f"taverna: {legs['Taverna Agios']['state']}")
    say(f"Taverna Agios booked on its own form: {legs['Taverna Agios'].get('reference')}")
    op("sandbox.supplier_reply", {"leg_id": legs["Kyma Gear"]["leg_id"], "text": "YES"})
    r = op("sandbox.supplier_reply", {"leg_id": legs["Aegean Boats"]["leg_id"], "text": "ΝΑΙ"})
    if r["bundle_state"] != "confirmed":
        raise Fail(f"bundle: {r}")
    s = gen(key, "bookings.status", {"bundle_id": q["bundle_id"]})
    if s["customer_sentence"] != "All confirmed. Here's your plan.":
        raise Fail(s["customer_sentence"])
    say("Kyma Gear: YES · Aegean Boats: ΝΑΙ (through the sandbox's messages.replies) · the hotel booked → All confirmed")
    # 3:30–4:00 · proof
    for l in s["legs"] + [{"evidence_id": s["evidence_id"], "supplier": "the booking"}]:
        st, t, _ = req("POST", "/console/api/evidence.get", {"evidence_id": l["evidence_id"]}, {"Authorization": f"Bearer {tok}"})
        if not json.loads(t)["result"]["verified"]:
            raise Fail(f"proof for {l['supplier']} doesn't verify")
    say("proof on every leg and the booking: ✓ the record matches")
    # 4:00–4:40 · the failure beat: Thursday, the boat says NO
    st, t, _ = req("POST", "/console/api/bookings.test_quote", {}, {"Authorization": f"Bearer {tok}"})
    tq = json.loads(t)
    if not tq["ok"]:
        raise Fail(f"test quote: {tq['error']['message']}")
    tl = {l["supplier"]: l for l in tq["result"]["legs"]}
    op("sandbox.supplier_reply", {"leg_id": tl["Kyma Gear"]["leg_id"], "text": "YES"})
    r = op("sandbox.supplier_reply", {"leg_id": tl["Aegean Boats"]["leg_id"], "text": "NO, full"})
    if r["bundle_state"] != "failed":
        raise Fail(f"failure beat: {r}")
    st, t, _ = req("POST", "/console/api/bookings.list", {}, {"Authorization": f"Bearer {tok}"})
    fb = json.loads(t)["result"]["bookings"][0]
    if not fb["customer_sentence"].startswith("Aegean Boats can't take your group on Thu") or "Nothing has been charged" not in fb["customer_sentence"]:
        raise Fail(fb["customer_sentence"])
    if sorted(l["state"] for l in fb["legs"]) != ["declined", "released", "released", "released"]:
        raise Fail(f"released: {[l['state'] for l in fb['legs']]}")
    say("failure beat: '" + fb["customer_sentence"] + "' — the other three released, the hotel never booked")
    st, t, _ = req("POST", "/console/api/captured.list", {}, {"Authorization": f"Bearer {tok}"})
    real = [m for m in json.loads(t)["result"]["messages"] if m["real"]]
    if real:
        raise Fail(f"{len(real)} REAL message(s) went out")
    say("0 messages to a real number or inbox")


if __name__ == "__main__":
    import urllib.parse  # noqa: F401
    sys.exit(main())
