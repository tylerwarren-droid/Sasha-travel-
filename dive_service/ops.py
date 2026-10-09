"""DIVE's operations — the operator's (EU 212 api.md A) and the generated API's (B), one function each, the same envelope as AgAPI.
In dive_service ONLY: not AgAPI 1.1, not the frozen spec. (v1.2 lives here until Tyler says otherwise.)"""
from __future__ import annotations

from typing import Any, Dict, Optional
from urllib.parse import urlparse

from . import bundles as BN, channels as CH, config, model as M, onboard as ON, rules as R
from .model import DiveError
from .store import Store, dumps, loads, ts

FIXTURE_RECIPE = [   # Discover Mykonos (EU 212 bundles.md §1), built from the CONFIRMED suppliers by kind
    {"kind": "boat", "title": "Guided dive + boat, Paradise Reef", "unit": "person", "amount_minor": 8000, "duration": 240, "policy": "request_confirm",
     "required": True, "offset": 0, "label": "Guided dive + boat, Paradise Reef"},
    {"kind": "gear", "title": "Gear: BCD, regulator, wetsuit", "unit": "person", "amount_minor": 3000, "duration": 240, "policy": "request_confirm",
     "required": True, "offset": 0, "label": "Gear (BCD, regulator, wetsuit)"},
    {"kind": "restaurant", "title": "Lunch by the harbour", "unit": "person", "amount_minor": 2500, "duration": 90, "policy": "request_confirm",
     "required": False, "offset": 270, "label": "Lunch"},
    {"kind": "hotel_feed", "title": "Hotel Kyma View, 1 night", "unit": "item", "amount_minor": 14000, "duration": 1440, "policy": "instant",
     "required": True, "offset": -900, "label": "Hotel Kyma View"},
]


def operator(s: Store, slug: str = "blue-kyma") -> dict:
    o = s.one("select * from operators where slug = ?", slug)
    if not o:
        raise DiveError("not_found", "No such operator.")
    return o


def _sup(s: Store, o: dict, sid: str) -> dict:
    x = s.one("select * from suppliers where id = ? and operator_id = ?", sid, o["id"])
    if not x:
        raise DiveError("not_found", "No such supplier.")
    return x


async def run(s: Store, o: dict, op: str, inp: Dict[str, Any], *, key_id: Optional[str] = None) -> Dict[str, Any]:
    f = OPS.get(op)
    if not f:
        raise DiveError("not_found", f"There is no operation {op} here.")
    return await f(s, o, inp, key_id)


# ── A · the operator's ──────────────────────────────────────────────────────────────────────────────────────────────────

async def operators_put(s, o, inp, _):
    return M.operator_out(M.put_operator(s, inp["slug"], inp["name"], inp["timezone"], inp["languages"], inp.get("site_url"), inp.get("footer")))


async def suppliers_draft_from_site(s, o, inp, _):
    got = await ON.draft_from_site(s, o, inp.get("url"))
    return {"drafts": [M.supplier_out(s, s.one("select * from suppliers where id = ?", i)) for i in got["supplier_ids"]], "coverage": got["coverage"]}


async def suppliers_put(s, o, inp, _):
    """Only a PERSON's click in the console makes a draft 'confirmed'; 'rejected' is [Not ours]."""
    x = _sup(s, o, inp["supplier_id"])
    if inp.get("name"):
        s.x("update suppliers set name = ? where id = ?", inp["name"][:120], x["id"])
    if inp.get("kind"):
        s.x("update suppliers set kind = ? where id = ?", inp["kind"], x["id"])
    if inp.get("status"):
        s.x("update suppliers set status = ? where id = ?", inp["status"], x["id"])
        M.event(s, o["id"], "supplier", f"{x['name']}: {inp['status']}")
    return M.supplier_out(s, s.one("select * from suppliers where id = ?", x["id"]))


async def suppliers_list(s, o, inp, _):
    await check_verifications(s, o)
    q = "select * from suppliers where operator_id = ?" + (" and status = ?" if inp.get("status") else " and status != 'rejected'")
    rows = s.q(q + " order by created_at", o["id"], *([inp["status"]] if inp.get("status") else []))
    return {"suppliers": [M.supplier_out(s, x) for x in rows]}


async def channels_put(s, o, inp, _):
    x = _sup(s, o, inp["supplier_id"])
    c = M.add_channel(s, x, inp["kind"], inp["address"], inp.get("language", "en"), inp.get("answer_timeout_s"), inp.get("quiet_hours"))
    return M.channel_out(c)


async def channels_verify(s, o, inp, _):
    """WhatsApp: the first message (asks them to reply YES); email: a verification email; form: a DRY RUN (read, never submit);
    feed: a test search. 'verified' only on their YES / a successful dry run — nothing is ever sent to an unverified channel otherwise."""
    c = s.one("select c.* from channels c join suppliers x on x.id = c.supplier_id where c.id = ? and x.operator_id = ?", inp["channel_id"], o["id"])
    if not c:
        raise DiveError("not_found", "No such channel.")
    x = s.one("select * from suppliers where id = ?", c["supplier_id"])
    if x["status"] != "confirmed":
        raise DiveError("supplier_not_confirmed", f"{x['name']} is still a draft.")
    if c["kind"] == "whatsapp":
        text = f"{o['name'].split(' (')[0]} will send you booking requests through this number. Reply YES to accept."
        got = await CH.whatsapp_send(s, o, c["address"], x["name"], text)       # their window closed → the approved first message instead
        if not got.get("ok"):
            raise DiveError("upstream_unreachable", f"Couldn't reach {x['name']} on WhatsApp just now — not a no.")
        s.x("update channels set verify_state = ? where id = ?", dumps({"state": "sent", "at": ts(), "ref": got["reference"]}), c["id"])
        eid = M.evidence(s, o["id"], "channels.verify", sources=[{"service": "whatsapp_sent", "retrieved_at": ts()[:19] + "Z", "sha256": got["body_sha256"]}],
                         digest_of={"channel_id": c["id"]}, outcome={"kind": "REQUESTED", "reference": got["reference"]})
        M.event(s, o["id"], "verify", f"Asked {x['name']} to reply YES on WhatsApp", evidence_id=eid)
        return {"channel_id": c["id"], "state": "sent", "evidence_id": eid, "say": f"Waiting for {x['name']} to reply YES."}
    if c["kind"] == "email":
        got = await CH.email_send(s, c["address"], f"{o['name']} — booking requests", f"{o['name']} will send you booking requests by email. Reply YES to accept.")
        s.x("update channels set verify_state = ? where id = ?", dumps({"state": "sent", "at": ts(), "ref": got.get("reference")}), c["id"])
        M.event(s, o["id"], "verify", f"Asked {x['name']} to reply YES by email" + ("" if got.get("real") else " (captured in test)"))
        return {"channel_id": c["id"], "state": "sent", "say": f"Waiting for {x['name']} to reply YES." + ("" if got.get("real") else " (Test: the email was captured.)")}
    if c["kind"] == "web_form":
        import re as _re
        try:
            st, page = await ON.FETCH(c["address"])
        except Exception:
            st, page = 0, ""
        ok = st == 200 and _re.search(r'<form[^>]+id="booking-form"', page) and all(f'name="{n}"' in page for n in ("date", "time", "party_size", "name"))
        if not ok:
            raise DiveError("upstream_unreachable", f"Couldn't read {x['name']}'s form — not a no.")
        return _verified(s, o, c, x, "a dry run read their form (nothing submitted)")
    if c["kind"] == "feed":
        feed, _, hotel = c["address"].partition("#")
        if hotel not in CH.FEED.get(feed, {}):
            raise DiveError("upstream_unreachable", "The feed didn't return that hotel.")
        return _verified(s, o, c, x, "a test search found it")
    raise DiveError("invalid_input", "That channel kind can't be verified here yet.")


def _verified(s, o, c, x, how):
    s.x("update channels set verified = 1, verified_at = ?, verified_how = ?, verify_state = ? where id = ?", ts()[:19] + "Z", how,
        dumps({"state": "verified"}), c["id"])
    M.event(s, o["id"], "verified", f"{x['name']}: {c['kind'].replace('_', ' ')} verified")
    return {"channel_id": c["id"], "state": "verified", "say": f"{x['name']} verified — {how}."}


async def check_verifications(s: Store, o: dict) -> None:
    """A WhatsApp verification sent → their YES (via messages.replies) → verified. A NO or unclear: stays unverified, said."""
    for c in s.q("select c.* from channels c join suppliers x on x.id = c.supplier_id where x.operator_id = ? and c.verified = 0 "
                 "and c.kind = 'whatsapp' and c.verify_state like '%\"sent\"%'", o["id"]):
        vs = loads(c["verify_state"])
        for r in await CH.whatsapp_replies(s, o, c["address"]):
            if r["received_at"] > vs["at"]:
                p = R.supplier_reply(r["text"]["text"])["parse"]
                x = s.one("select * from suppliers where id = ?", c["supplier_id"])
                if p == "yes":
                    _verified(s, o, c, x, f"they replied YES on WhatsApp ({r['reply_id']})")
                else:
                    s.x("update channels set verify_state = ? where id = ?", dumps({**vs, "state": p, "reply": r["text"]["text"][:200]}), c["id"])
                break


async def products_put(s, o, inp, _):
    x = _sup(s, o, inp["supplier_id"])
    pid = R.new_id("prd")
    s.x("insert into products (id, operator_id, supplier_id, title, unit, price, capacity, duration_minutes, policy, cutoff, created_at) "
        "values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", pid, o["id"], x["id"], inp["title"][:120], inp["unit"], dumps(inp["price"]), inp.get("capacity"),
        inp.get("duration_minutes"), inp["policy"], inp.get("cutoff"), ts())
    return product_out(s.one("select * from products where id = ?", pid))


def product_out(p):
    return {"product_id": p["id"], "supplier_id": p["supplier_id"], "title": p["title"], "unit": p["unit"], "price": loads(p["price"]),
            **({"capacity": p["capacity"]} if p["capacity"] else {}), **({"duration_minutes": p["duration_minutes"]} if p["duration_minutes"] is not None else {}),
            "policy": p["policy"], **({"cutoff": p["cutoff"]} if p["cutoff"] else {})}


async def products_list(s, o, inp, _):
    return {"products": [product_out(p) for p in s.q("select * from products where operator_id = ? order by created_at", o["id"])]}


async def packages_put(s, o, inp, _):
    for c in inp["components"]:
        if not s.one("select 1 from products where id = ? and operator_id = ?", c["product_id"], o["id"]):
            raise DiveError("not_found", "A component's product isn't yours.")
    pid = R.new_id("pkg")
    s.x("insert into packages (id, operator_id, title, description, components, price, created_at) values (?, ?, ?, ?, ?, ?, ?)", pid, o["id"],
        inp["title"][:120], (inp.get("description") or "")[:600], dumps(inp["components"]), dumps(inp["price"]), ts())
    return package_out(s.one("select * from packages where id = ?", pid))


def package_out(p):
    return {"package_id": p["id"], "operator_id": p["operator_id"], "title": p["title"], **({"description": p["description"]} if p["description"] else {}),
            "components": loads(p["components"]), "price": loads(p["price"]), "published": bool(p["published"])}


async def packages_list(s, o, inp, key_id):
    q = "select * from packages where operator_id = ?" + (" and published = 1" if key_id else "")
    return {"packages": [package_out(p) for p in s.q(q + " order by created_at", o["id"])]}


async def packages_from_fixture(s, o, inp, _):
    """FIXTURE (the demo's 'read-only editor'): Discover Mykonos from the CONFIRMED suppliers, one product per kind."""
    comps = []
    for r in FIXTURE_RECIPE:
        x = s.one("select * from suppliers where operator_id = ? and kind = ? and status = 'confirmed' order by created_at", o["id"], r["kind"])
        if not x:
            raise DiveError("supplier_not_confirmed", f"Confirm a {r['kind'].replace('_', ' ')} supplier first.")
        p = s.one("select * from products where supplier_id = ? and title = ?", x["id"], r["title"]) or \
            s.one("select * from products where id = ?", (await products_put(s, o, {"supplier_id": x["id"], "title": r["title"], "unit": r["unit"],
                  "price": {"amount_minor": r["amount_minor"], "currency": "EUR"}, "duration_minutes": r["duration"], "policy": r["policy"]}, None))["product_id"])
        comps.append({"product_id": p["id"], "required": r["required"], "quantity_rule": "per_person" if r["unit"] == "person" else "per_item",
                      "offset_minutes": r["offset"], "label": r["label"]})
    ex = s.one("select * from packages where operator_id = ? and title = 'Discover Mykonos'", o["id"])
    if ex:
        s.x("update packages set components = ? where id = ?", dumps(comps), ex["id"])
        return package_out(s.one("select * from packages where id = ?", ex["id"]))
    return await packages_put(s, o, {"title": "Discover Mykonos", "description": "Two guided dives from the boat, your gear, lunch by the harbour "
                                     "and a night at Hotel Kyma View.", "components": comps,
                                     "price": {"amount_minor": 16500, "currency": "EUR", "unit": "person"}}, None)


async def operator_api_publish(s, o, inp, _):
    ids = inp.get("package_ids") or [p["id"] for p in s.q("select id from packages where operator_id = ?", o["id"])]
    for pid in ids:
        pkg = s.one("select * from packages where id = ? and operator_id = ?", pid, o["id"])
        if not pkg:
            raise DiveError("not_found", "No such package.")
        for c in loads(pkg["components"]):
            p = s.one("select * from products where id = ?", c["product_id"])
            x = s.one("select * from suppliers where id = ?", p["supplier_id"])
            if x["status"] != "confirmed":
                raise DiveError("supplier_not_confirmed", f"{x['name']} isn't confirmed yet.")
            if not M.best_channel(s, x["id"]):
                raise DiveError("channel_not_verified", f"{x['name']} has no verified channel yet — send a verification first.")
        s.x("update packages set published = 1 where id = ?", pid)
    M.event(s, o["id"], "published", f"API published ({len(ids)} package{'s' if len(ids) != 1 else ''})")
    return {"base_url": f"{config.PUBLIC_URL}/o/{o['slug']}/v1", "docs_url": f"{config.PUBLIC_URL}/o/{o['slug']}/docs", "published": ids}


async def operator_keys_issue(s, o, inp, _):
    k = M.issue_key(s, o["id"], inp["label"])
    M.event(s, o["id"], "key", f"Key issued: {k['label']}")
    return k


async def operator_keys_revoke(s, o, inp, _):
    if s.x("update op_keys set state = 'revoked' where key_id = ? and operator_id = ?", inp["key_id"], o["id"]) != 1:
        raise DiveError("not_found", "No such key.")
    return {"key_id": inp["key_id"], "state": "revoked"}


async def sandbox_supplier_reply(s, o, inp, _):
    if config.MODE != "test":
        raise DiveError("mode_not_available", "Test mode only.")
    if inp.get("channel_id"):     # a verification answer (WhatsApp through the sandbox; email recorded)
        c = s.one("select c.* from channels c join suppliers x on x.id = c.supplier_id where c.id = ? and x.operator_id = ?", inp["channel_id"], o["id"])
        if not c:
            raise DiveError("not_found", "No such channel.")
        if c["kind"] == "whatsapp":
            await CH.whatsapp_simulate_reply(c["address"], inp["text"])
            await check_verifications(s, o)
        elif R.supplier_reply(inp["text"])["parse"] == "yes":
            _verified(s, o, c, s.one("select * from suppliers where id = ?", c["supplier_id"]), "they replied YES by email (test)")
        c = s.one("select * from channels where id = ?", c["id"])
        return {"channel_id": c["id"], "parse": R.supplier_reply(inp["text"])["parse"], "leg_state": "verified" if c["verified"] else "unverified"}
    return await BN.supplier_reply(s, o, inp["leg_id"], inp["text"])


# ── B · the generated API ───────────────────────────────────────────────────────────────────────────────────────────────

async def packages_get(s, o, inp, key_id):
    p = s.one("select * from packages where id = ? and operator_id = ? and published = 1", inp["package_id"], o["id"])
    if not p:
        raise DiveError("package_not_published", "That package isn't published.")
    return package_out(p)


async def availability_check(s, o, inp, key_id):
    p = await packages_get(s, o, inp, key_id)
    legs, complete = [], True
    for c in p["components"]:
        prod = s.one("select * from products where id = ?", c["product_id"])
        x = s.one("select * from suppliers where id = ?", prod["supplier_id"])
        ch = M.best_channel(s, x["id"])
        if prod["policy"] == "instant":
            ok = ch and ch["kind"] == "feed" and not CH.FEED_DOWN
            a, w = ("available", "Available") if ok else ("unknown", f"We can't check {x['name']} right now. This isn't a no.")
            complete = complete and bool(ok)
        elif prod["policy"] == "request_confirm":
            a, w = "likely", f"Likely: {x['name']} confirms within 2 h"
        else:
            a, w = "on_request", "On request"
        legs.append({"product_id": prod["id"], "supplier": x["name"], "availability": a, "words": w})
    return {"package_id": p["package_id"], "legs": legs, "coverage": {"complete": complete}}


async def bookings_quote(s, o, inp, key_id):
    return await BN.quote(s, o, inp["package_id"], inp["date"], inp["start_time"], int(inp["party"]), inp["customer"], key_id)


async def bookings_confirm(s, o, inp, key_id, approval_id=None):
    return await BN.confirm(s, o, inp["bundle_id"], approval_id)


async def bookings_status(s, o, inp, key_id):
    b = s.one("select * from bundles where id = ? and operator_id = ?", inp["bundle_id"], o["id"])
    if not b:
        raise DiveError("not_found", "No such booking.")
    return await BN.sync(s, o, b["id"])


async def approvals_request(s, o, inp, key_id):
    """The customer's phone gets the read-back link (test: captured — the demo's right screen opens it)."""
    b = s.one("select * from bundles where id = ? and operator_id = ?", inp["bundle_id"], o["id"])
    if not b:
        raise DiveError("not_found", "No such booking.")
    token = BN.approval_link(s, b["id"])
    cust = loads(b["customer"])
    url = f"{config.PUBLIC_URL}/o/{o['slug']}/a/{token}"
    s.x("insert into captured (channel, to_, body, real, at) values ('sms', ?, ?, 0, ?)", cust.get("phone") or cust.get("email") or "customer",
        f"{o['name']}: please review and approve your booking: {url}", ts())
    return {"bundle_id": b["id"], "sent_to": "the customer's phone", "link_expires_in_minutes": BN.APPROVAL_MIN}


async def sandbox_reset(s, o, inp, _):
    """TEST ONLY: the operator's console back to empty (suppliers, packages, bookings, keys, activity) — for a clean rehearsal."""
    if config.MODE != "test":
        raise DiveError("mode_not_available", "Test mode only.")
    sups = [x["id"] for x in s.q("select id from suppliers where operator_id = ?", o["id"])]
    for sid in sups:
        s.x("delete from channels where supplier_id = ?", sid)
    bids = [b["id"] for b in s.q("select id from bundles where operator_id = ?", o["id"])]
    for bid in bids:
        s.x("delete from legs where bundle_id = ?", bid)
        s.x("delete from approvals where bundle_id = ?", bid)
        s.x("delete from approval_links where bundle_id = ?", bid)
    for t in ("suppliers", "products", "packages", "bundles", "evidence", "op_keys", "events"):
        s.x(f"delete from {t} where operator_id = ?", o["id"])
    s.x("delete from captured")
    return {"reset": True, "suppliers": len(sups), "bookings": len(bids)}


OPS = {"operators.put": operators_put, "sandbox.reset": sandbox_reset, "suppliers.draft_from_site": suppliers_draft_from_site, "suppliers.put": suppliers_put,
       "suppliers.list": suppliers_list, "channels.put": channels_put, "channels.verify": channels_verify, "products.put": products_put,
       "products.list": products_list, "packages.put": packages_put, "packages.list": packages_list, "packages.from_fixture": packages_from_fixture,
       "operator_api.publish": operator_api_publish, "operator_keys.issue": operator_keys_issue, "operator_keys.revoke": operator_keys_revoke,
       "sandbox.supplier_reply": sandbox_supplier_reply}
GENERATED = {"packages.list": packages_list, "packages.get": packages_get, "availability.check": availability_check,
             "bookings.quote": bookings_quote, "bookings.confirm": bookings_confirm, "bookings.status": bookings_status,
             "approvals.request": approvals_request}
