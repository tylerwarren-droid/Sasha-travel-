"""DIVE step 6 · BUNDLES — one read-back over every leg, ONE yes, each leg through its own channel (EU 212 bundles.md).
  quote    every leg is a line with its supplier and HOW it will be confirmed; instant legs are HELD; quiet hours move the promise
  confirm  the customer's approval of exactly this read-back (re-derived now: any leg's terms changed → approval_void, AP1);
           then: the form is submitted, requests go out (or wait for 08:00), held legs wait for the required ones
  sync     replies parsed (yes | no | unclear — unclear is the operator's, never guessed), deadlines → no_answer, outages retried and
           NEVER called a no; then the bundle settles: all required confirmed → the hotel is booked → confirmed; a required NO / no
           answer / unreachable-at-the-deadline → every other leg RELEASED (a "sorry" to suppliers who said yes) → failed
  evidence one per settled leg (its channel's proof + the supplier's words as untrusted_text) and one for the bundle."""
from __future__ import annotations

import secrets
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

from . import channels as CH, config, rules as R
from .model import DiveError, best_channel, event, evidence, move_leg
from .store import Store, dumps, later, loads, now, parse_ts, ts

APPROVAL_MIN, QUOTE_MIN, LEAD_MIN = 15, 15, 60


def _money(minor: int, cur: str = "EUR") -> str:
    return ("€" if cur == "EUR" else cur + " ") + (f"{minor // 100}" if minor % 100 == 0 else f"{minor / 100:.2f}")


def _when(dt_local: datetime) -> str:
    return dt_local.strftime("%a %d %b %Y").replace(dt_local.strftime("%b"), dt_local.strftime("%b").upper())


def _how(kind: str, supplier: str, answer_by_local: Optional[datetime], requested_local: Optional[datetime]) -> str:
    if kind == "feed":
        return "instant (feed)"
    if kind == "web_form":
        return "booked on their form"
    by = "by the boat" if "boat" in supplier.lower() else f"by {supplier}"
    via = "by email" if kind == "email" else ""
    if answer_by_local and requested_local and (answer_by_local - requested_local) <= timedelta(hours=2, minutes=1) and requested_local.date() == answer_by_local.date():
        return f"confirmed {via or by} within 2 h".replace("  ", " ")
    return f"confirmed {via or by} by {answer_by_local.strftime('%H:%M %d %b').upper() if answer_by_local else 'their opening time'}"


def _plan(s: Store, operator: dict, package: dict, day: str, start: str, party: int) -> Tuple[List[dict], dict]:
    """The legs + the payload, re-derivable at any time from the published package (so a changed leg voids the yes)."""
    tz = ZoneInfo(operator["timezone"])
    try:
        start_local = datetime.fromisoformat(f"{day}T{start}").replace(tzinfo=tz)
    except ValueError:
        raise DiveError("invalid_input", "A date is YYYY-MM-DD and a time HH:MM.", {"path": "/date", "rule": "format"})
    legs, total = [], 0
    for i, comp in enumerate(loads(package["components"])):
        p = s.one("select * from products where id = ?", comp["product_id"])
        sup = p and s.one("select * from suppliers where id = ?", p["supplier_id"])
        if not p or not sup:
            raise DiveError("package_not_published", "A part of this package no longer exists.")
        if sup["status"] != "confirmed":
            raise DiveError("supplier_not_confirmed", f"{sup['name']} isn't a confirmed supplier yet.")
        ch = best_channel(s, sup["id"])
        if not ch:
            raise DiveError("channel_not_verified", f"{sup['name']} has no verified way to receive bookings yet.")
        price = loads(p["price"])
        qty = party if comp["quantity_rule"] == "per_person" else 1
        leg_start = start_local + timedelta(minutes=int(comp["offset_minutes"]))
        if p["cutoff"] == "18:00 the day before" and now() > (leg_start - timedelta(days=1)).replace(hour=18, minute=0):
            raise DiveError("past_cutoff", f"{p['title']} closes for bookings at 18:00 the day before.")
        legs.append({"seq": i, "product": p, "supplier": sup, "channel": ch, "required": bool(comp["required"]), "label": comp.get("label") or p["title"],
                     "starts_local": leg_start, "amount_minor": price["amount_minor"] * qty, "currency": price["currency"]})
        total += price["amount_minor"] * qty
    pkg_price = loads(package["price"])
    total = pkg_price["amount_minor"] * (party if pkg_price.get("unit") == "person" else 1)
    payload = {"package_id": package["id"], "party": party, "starts_at": ts(start_local)[:19] + "Z",
               "legs": [{"product_id": l["product"]["id"], "starts_at": ts(l["starts_local"])[:19] + "Z", "channel_id": l["channel"]["id"],
                         "amount_minor": l["amount_minor"]} for l in legs], "total": {"amount_minor": total, "currency": pkg_price["currency"]}}
    return legs, payload


def _lines(operator: dict, package: dict, legs: List[dict], party: int, customer: dict, total: dict, quote_now: datetime) -> List[str]:
    tz = ZoneInfo(operator["timezone"])
    first = legs[0]["starts_local"]
    out = [f"{operator['name']} · {package['title']}", f"{_when(first)} · {party} {'divers' if party != 1 else 'diver'} ({customer['name']}"
           + (f" + {party - 1})" if party > 1 else ")")]
    for i, l in enumerate(legs, 1):
        kind = l["channel"]["kind"]
        send = CH.send_time(quote_now, l["channel"]["quiet_hours"]).astimezone(tz)
        by = send + timedelta(seconds=l["channel"]["answer_timeout_s"])
        dur = int(l["product"]["duration_minutes"] or 0)
        window = l["starts_local"].strftime("%H:%M") + (f"–{(l['starts_local'] + timedelta(minutes=dur)).strftime('%H:%M')}" if dur and kind != "feed" else "")
        if kind == "feed":
            nights = max(1, dur // 1440 or 1)
            window = f"{l['starts_local'].strftime('%d')}–{(l['starts_local'] + timedelta(days=nights)).strftime('%d %b').upper()}, 1 room"
        out.append(f"{i}. {l['label']}: {window} · {l['supplier']['name']} · {_how(kind, l['supplier']['name'], by, send)}")
    out.append(f"Total {_money(total['amount_minor'], total['currency'])} for {party} · nothing is charged here; money is between you and {operator['name']}")
    req = [str(i) for i, l in enumerate(legs, 1) if l["channel"]["kind"] != "feed"]
    if req:
        out.append(f"If any of {', '.join(req)} can't be confirmed, nothing is charged for it, and we'll ask before changing anything.")
    return out


async def quote(s: Store, operator: dict, package_id: str, day: str, start: str, party: int, customer: dict, key_id: Optional[str]) -> dict:
    pkg = s.one("select * from packages where id = ? and operator_id = ?", package_id, operator["id"])
    if not pkg or not pkg["published"]:
        raise DiveError("package_not_published", "That package isn't published.")
    if not 1 <= int(party) <= 30:
        raise DiveError("invalid_input", "The party is 1–30 people.", {"path": "/party", "rule": "range"})
    legs, payload = _plan(s, operator, pkg, day, start, int(party))
    bid, rbid, qnow = R.new_id("bnd"), R.new_id("rb"), now()
    payload["bundle_id"] = bid
    lines = _lines(operator, pkg, legs, int(party), customer, payload["total"], qnow)
    rsha = R.read_back_sha256(operator["id"], bid, lines, R.sha256(payload))
    s.x("insert into bundles (id, operator_id, package_id, party, starts_at, customer, total, lines, payload, read_back_id, read_back_sha256, "
        "state, key_id, expires_at, created_at, updated_at) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'quoted', ?, ?, ?, ?)", bid, operator["id"], pkg["id"],
        int(party), payload["starts_at"], dumps(customer), dumps(payload["total"]), dumps(lines), dumps(payload), rbid, rsha, key_id,
        later(QUOTE_MIN), ts(), ts())
    for l in legs:
        lid, ext, state = R.new_id("leg"), {}, "pending"
        if l["channel"]["kind"] == "feed":
            feed, _, hotel = l["channel"]["address"].partition("#")
            h = CH.feed_hold(feed, hotel, max(1, int(l["product"]["duration_minutes"] or 1440) // 1440))
            if h["state"] != "held":
                s.x("update bundles set state = 'failed' where id = ?", bid)
                raise DiveError("supplier_unreachable", f"We can't check {l['supplier']['name']} right now. This isn't a no.")
            ext, state = {"hold": h["hold"]}, "held"
        s.x("insert into legs (id, bundle_id, product_id, supplier_id, channel_id, required, title, starts_at, state, external, seq) "
            "values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", lid, bid, l["product"]["id"], l["supplier"]["id"], l["channel"]["id"], int(l["required"]),
            l["label"], ts(l["starts_local"])[:19] + "Z", state, dumps(ext), l["seq"])
    event(s, operator["id"], "quoted", f"Quote for {customer['name']} · {pkg['title']} · {party}", bundle_id=bid)
    return bundle_out(s, s.one("select * from bundles where id = ?", bid))


# ── the customer's approval: a tap on THEIR phone (v1: a partner can't approve for the user) ────────────────────────────

def approval_link(s: Store, bundle_id: str) -> str:
    token = secrets.token_urlsafe(24)
    s.x("insert into approval_links (token_hash, bundle_id, created_at, expires_at) values (?, ?, ?, ?)", R.text_sha256(token), bundle_id,
        ts(), later(APPROVAL_MIN))
    return token


def approve(s: Store, bundle: dict, *, method: str = "tap", said: Optional[str] = None) -> str:
    if said is not None and not R.explicit_yes_any(said)[0]:
        raise DiveError("no_explicit_yes", "That isn't an explicit yes.")
    aid = R.new_id("apv")
    s.x("insert into approvals (id, bundle_id, read_back_sha256, payload_sha256, said, method, state, approved_at, expires_at) "
        "values (?, ?, ?, ?, ?, ?, 'valid', ?, ?)", aid, bundle["id"], bundle["read_back_sha256"], R.sha256(loads(bundle["payload"])), said,
        method, ts(), later(APPROVAL_MIN))
    s.x("update bundles set state = 'approved', updated_at = ? where id = ? and state = 'quoted'", ts(), bundle["id"])
    event(s, bundle["operator_id"], "approved", "The customer approved the read-back on their phone", bundle_id=bundle["id"])
    return aid


async def confirm(s: Store, operator: dict, bundle_id: str, approval_id: Optional[str]) -> dict:
    b = s.one("select * from bundles where id = ? and operator_id = ?", bundle_id, operator["id"])
    if not b:
        raise DiveError("not_found", "No such booking.")
    if b["state"] not in ("quoted", "approved"):
        return bundle_out(s, b)                                     # already going: confirm is idempotent by bundle
    apv = approval_id and s.one("select * from approvals where id = ? and bundle_id = ?", approval_id, bundle_id)
    pkg = s.one("select * from packages where id = ?", b["package_id"])
    cust = loads(b["customer"])
    start_local = parse_ts(b["starts_at"]).astimezone(ZoneInfo(operator["timezone"]))
    try:
        legs, payload = _plan(s, operator, pkg, start_local.date().isoformat(), start_local.strftime("%H:%M"), b["party"])
        payload["bundle_id"] = b["id"]
    except DiveError as e:
        raise DiveError("bundle_changed", f"Something in this booking changed ({e.message}) — a new quote and a new yes are needed.")
    a = None if not apv else {"bundle_id": apv["bundle_id"], "read_back_sha256": apv["read_back_sha256"], "payload_sha256": apv["payload_sha256"],
                              "state": apv["state"], "expires_at": apv["expires_at"]}
    decision, why = R.decide_bundle(a, {"bundle_id": b["id"], "lines": loads(b["lines"]), "payload": payload}, operator["id"], ts())
    if decision == "approval_void":
        s.x("update approvals set state = 'void' where id = ?", approval_id)
        raise DiveError("bundle_changed", "A leg's terms changed after the read-back, so the yes is void — a new quote and a new yes are needed.",
                        {"void_reason": why})
    if decision != "valid":
        raise DiveError(decision, {"approval_required": "This booking needs the customer's yes on their phone first.",
                                   "approval_consumed": "That yes was already used.", "approval_expired": "That yes is over 15 minutes old."}[decision])
    if s.x("update approvals set state = 'consumed' where id = ? and state = 'valid'", approval_id) != 1:
        raise DiveError("approval_consumed", "That yes was already used.")
    s.x("update bundles set state = 'in_progress', updated_at = ? where id = ?", ts(), b["id"])
    event(s, operator["id"], "started", "Confirming with the suppliers", bundle_id=b["id"])
    for leg in s.q("select * from legs where bundle_id = ? order by seq", b["id"]):
        await _start_leg(s, operator, b, leg, cust)
    await sync(s, operator, b["id"])
    return bundle_out(s, s.one("select * from bundles where id = ?", b["id"]))


async def _start_leg(s: Store, operator: dict, b: dict, leg: dict, cust: dict) -> None:
    ch = s.one("select * from channels where id = ?", leg["channel_id"])
    sup = s.one("select * from suppliers where id = ?", leg["supplier_id"])
    tz = ZoneInfo(operator["timezone"])
    start_local = parse_ts(leg["starts_at"]).astimezone(tz)
    if ch["kind"] == "feed":
        return                                                      # held; booked once every required leg is confirmed
    if ch["kind"] == "web_form":
        got = await CH.form_submit(ch["address"], start_local, b["party"], f"{cust['name']} · {operator['name']}")
        _settle_form(s, operator, b, leg, sup, ch, got)
        return
    when = CH.send_time(now(), ch["quiet_hours"], operator["timezone"])
    if when > now():
        ext = loads(leg["external"]) or {}
        s.x("update legs set external = ? where id = ?", dumps({**ext, "send_at": ts(when)}), leg["id"])
        event(s, operator["id"], "scheduled", f"{sup['name']}: request goes at {when.astimezone(tz).strftime('%H:%M')} (quiet hours)",
              bundle_id=b["id"], leg_id=leg["id"])
        return
    await _send_request(s, operator, b, leg, sup, ch)


def _ref(b: dict) -> str:
    return "BK-" + b["id"][-3:]


async def _send_request(s: Store, operator: dict, b: dict, leg: dict, sup: dict, ch: dict) -> None:
    tz = ZoneInfo(operator["timezone"])
    start_local = parse_ts(leg["starts_at"]).astimezone(tz)
    what = f"{leg['title'].lower()} for {b['party']}"
    text = CH.template("request", ch["language"], operator=operator["name"].split(" (")[0], what=what,
                       when=start_local.strftime("%a %d %b %H:%M"), ref=_ref(b))
    if ch["kind"] == "whatsapp":
        got = await CH.whatsapp_send(s, operator, ch["address"], sup["name"], text)
    else:
        got = await CH.email_send(s, ch["address"], f"[{_ref(b)}] {operator['name']} booking request", text)
    ext = loads(leg["external"]) or {}
    if not got.get("ok"):
        tries = int(ext.get("tries") or 0) + 1
        s.x("update legs set external = ? where id = ?", dumps({**ext, "tries": tries, "why": got.get("why"), "send_at": None}), leg["id"])
        move_leg(s, leg, "unreachable")
        event(s, operator["id"], "unreachable", f"Couldn't reach {sup['name']} — not a no; trying again", bundle_id=b["id"], leg_id=leg["id"])
        return
    by = min(now() + timedelta(seconds=ch["answer_timeout_s"]), parse_ts(leg["starts_at"]) - timedelta(minutes=LEAD_MIN))
    leg = s.one("select * from legs where id = ?", leg["id"])
    move_leg(s, leg, "requested", requested_at=ts(), answer_by=ts(by),
             external=dumps({**ext, "send_at": None, "sent": {k: got.get(k) for k in ("reference", "sent_at", "kind", "body_sha256", "sandbox_evidence_id", "bridge", "real", "note")}}))
    event(s, operator["id"], "requested", f"Asked {sup['name']} by {ch['kind'].replace('_', ' ')}", bundle_id=b["id"], leg_id=leg["id"])


def _settle_form(s: Store, operator: dict, b: dict, leg: dict, sup: dict, ch: dict, got: dict) -> None:
    src = {"service": "web_form", "retrieved_at": ts()[:19] + "Z", "sha256": got.get("page_sha256") or got["fields_sha256"],
           "snippet": R.wrap(got["words"], f"form:{ch['address']}", ts()[:19] + "Z", cap=300)}
    if got["state"] == "unreachable":
        move_leg(s, leg, "unreachable", external=dumps({**(loads(leg["external"]) or {}), "why": got["words"]}))
        event(s, operator["id"], "unreachable", f"{sup['name']}'s form didn't answer — not a no", bundle_id=b["id"], leg_id=leg["id"])
        return
    eid = evidence(s, operator["id"], "dive.leg", sources=[src], digest_of={"leg_id": leg["id"], "fields_sha256": got["fields_sha256"]},
                   outcome={"kind": "CONFIRMED" if got["state"] == "confirmed" else "REFUSED", **({"reference": got["reference"]} if got.get("reference") else {}),
                            "target_words": src["snippet"]})
    move_leg(s, leg, got["state"], answered_at=ts(), reference=got.get("reference"), evidence_id=eid, reply=dumps(src["snippet"]),
             parse="yes" if got["state"] == "confirmed" else "no")
    event(s, operator["id"], got["state"], f"{sup['name']} {'confirmed on their form' if got['state'] == 'confirmed' else 'said no on their form'}",
          bundle_id=b["id"], leg_id=leg["id"], evidence_id=eid)


async def sync(s: Store, operator: dict, bundle_id: str) -> dict:
    """Bring a bundle up to date: due sends, replies, deadlines, retries — then settle it. Safe to call any number of times."""
    b = s.one("select * from bundles where id = ?", bundle_id)
    if b["state"] not in ("in_progress",):
        return bundle_out(s, b)
    for leg in s.q("select * from legs where bundle_id = ? order by seq", b["id"]):
        ch = s.one("select * from channels where id = ?", leg["channel_id"])
        sup = s.one("select * from suppliers where id = ?", leg["supplier_id"])
        ext = loads(leg["external"]) or {}
        if leg["state"] == "pending" and ext.get("send_at") and parse_ts(ext["send_at"]) <= now():
            await _send_request(s, operator, b, leg, sup, ch)
        elif leg["state"] == "unreachable" and ch["kind"] in ("whatsapp", "email") and int(ext.get("tries") or 0) < 3:
            await _send_request(s, operator, b, leg, sup, ch)        # retry: an outage, never a no
        elif leg["state"] == "requested" and ch["kind"] == "whatsapp":
            for r in await CH.whatsapp_replies(s, operator, ch["address"]):
                if r["received_at"] > leg["requested_at"] and r["reply_id"] != leg["reply_id"]:
                    _apply_reply(s, operator, b, leg, sup, ch, r["reply_id"], r["text"], r["received_at"])
                    break
        leg = s.one("select * from legs where id = ?", leg["id"])
        if leg["state"] == "requested" and leg["answer_by"] and parse_ts(leg["answer_by"]) <= now():
            eid = evidence(s, operator["id"], "dive.leg", sources=[{"service": ch["kind"], "retrieved_at": ts()[:19] + "Z",
                           "sha256": R.sha256({"leg_id": leg["id"], "answer_by": leg["answer_by"]})}], outcome={"kind": "UNKNOWN"},
                           digest_of={"leg_id": leg["id"]})
            move_leg(s, leg, "no_answer", evidence_id=eid)
            event(s, operator["id"], "no_answer", f"{sup['name']} didn't answer in time", bundle_id=b["id"], leg_id=leg["id"], evidence_id=eid)
    _settle_bundle(s, operator, s.one("select * from bundles where id = ?", b["id"]))
    return bundle_out(s, s.one("select * from bundles where id = ?", b["id"]))


def _apply_reply(s: Store, operator: dict, b: dict, leg: dict, sup: dict, ch: dict, reply_id: str, text: Any, received_at: str) -> None:
    """A supplier's answer: kept as THEIR words (untrusted); the parse reads only yes / no / unclear. Unclear → the operator."""
    words = text if isinstance(text, dict) else R.wrap(str(text), f"{ch['kind']}_supplier", ts()[:19] + "Z")
    parse = R.supplier_reply(words["text"])["parse"]
    sent = (loads(leg["external"]) or {}).get("sent") or {}
    srcs = [{"service": f"{ch['kind']}_sent", "retrieved_at": (sent.get("sent_at") or ts())[:19] + "Z",
             "sha256": sent.get("body_sha256") or R.sha256({"leg_id": leg["id"]}),
             "snippet": R.wrap(f"message {sent.get('reference')}" + (f" · {sent['bridge']}" if sent.get("bridge") else ""), "dive", ts()[:19] + "Z")},
            {"service": f"{ch['kind']}_reply", "retrieved_at": received_at[:19] + "Z", "sha256": R.text_sha256(words["text"]), "snippet": words}]
    if parse == "unclear":
        s.x("update legs set reply_id = ?, reply = ?, parse = 'unclear' where id = ?", reply_id, dumps(words), leg["id"])
        event(s, operator["id"], "unclear", f"{sup['name']} replied — unclear: for you to decide", bundle_id=b["id"], leg_id=leg["id"])
        return
    to = "confirmed" if parse == "yes" else "declined"
    eid = evidence(s, operator["id"], "dive.leg", sources=srcs, digest_of={"leg_id": leg["id"], "reply_id": reply_id},
                   outcome={"kind": "CONFIRMED" if to == "confirmed" else "REFUSED", "reference": reply_id, "target_words": words})
    move_leg(s, leg, to, answered_at=received_at, reply_id=reply_id, reply=dumps(words), parse=parse, evidence_id=eid)
    event(s, operator["id"], to, f"{sup['name']} {'confirmed' if to == 'confirmed' else 'said no'}", bundle_id=b["id"], leg_id=leg["id"], evidence_id=eid)


def _ctx(s: Store, operator: dict, b: dict) -> Dict[str, str]:
    start = parse_ts(b["starts_at"]).astimezone(ZoneInfo(operator["timezone"]))
    return {"operator": operator["name"].split(" (")[0], "date": f"{start.strftime('%a %d')} {start.strftime('%b').upper()} {start.year}",
            "total_without": ""}


def _view(s: Store, operator: dict, b: dict, deadline=False) -> Tuple[str, str]:
    legs = [{"supplier": s.one("select name from suppliers where id = ?", l["supplier_id"])["name"], "title": l["title"], "required": bool(l["required"]),
             "state": l["state"]} for l in s.q("select * from legs where bundle_id = ? order by seq", b["id"])]
    return R.bundle_view(legs, _ctx(s, operator, b), deadline_passed=deadline)


def _settle_bundle(s: Store, operator: dict, b: dict) -> None:
    legs = s.q("select * from legs where bundle_id = ? order by seq", b["id"])
    deadline = any(l["state"] == "unreachable" and l["required"] and int((loads(l["external"]) or {}).get("tries") or 0) >= 3 for l in legs)
    state, _ = _view(s, operator, b, deadline)
    if state == "failed":
        for l in legs:
            if l["state"] in ("pending", "requested", "unreachable", "held", "confirmed") and R.can_move(l["state"], "released"):
                ext = loads(l["external"]) or {}
                if l["state"] == "held" and ext.get("hold"):
                    CH.feed_release(ext["hold"])
                if l["state"] == "confirmed":
                    ch = s.one("select * from channels where id = ?", l["channel_id"])
                    if ch["kind"] in ("whatsapp", "email"):   # a "sorry, cancelled" to a supplier who said yes (captured in test)
                        s.x("insert into captured (channel, to_, body, real, at) values (?, ?, ?, 0, ?)", ch["kind"], ch["address"],
                            CH.template("release", ch["language"], operator=operator["name"].split(" (")[0], ref=_ref(b)), ts())
                move_leg(s, l, "released")
                sup = s.one("select name from suppliers where id = ?", l["supplier_id"])["name"]
                event(s, operator["id"], "released", f"Released {sup}", bundle_id=b["id"], leg_id=l["id"])
        _final(s, operator, b, "failed")
        return
    req = [l for l in legs if l["required"] and l["state"] != "held"]
    if req and all(l["state"] == "confirmed" for l in req):
        for l in [x for x in legs if x["state"] == "held"]:
            got = CH.feed_book((loads(l["external"]) or {}).get("hold", ""))
            if got["state"] != "booked":
                return                                                # the feed is down: still in progress, said as an outage
            eid = evidence(s, operator["id"], "dive.leg", sources=[{"service": "feed:sandbox-hotels", "retrieved_at": ts()[:19] + "Z",
                           "sha256": R.sha256({"reference": got["reference"]})}], outcome={"kind": "CONFIRMED", "reference": got["reference"],
                           "target_words": R.wrap(got["words"], "feed:sandbox-hotels", ts()[:19] + "Z")}, digest_of={"leg_id": l["id"]})
            move_leg(s, l, "booked", reference=got["reference"], evidence_id=eid, answered_at=ts())
            event(s, operator["id"], "booked", "Hotel booked through the feed", bundle_id=b["id"], leg_id=l["id"], evidence_id=eid)
        if all(l["state"] in ("confirmed", "booked") for l in s.q("select * from legs where bundle_id = ? and required = 1", b["id"])):
            _final(s, operator, b, "confirmed")


def _final(s: Store, operator: dict, b: dict, state: str) -> None:
    """The bundle settles: its own evidence (the read-back's sha, the approval, every leg's evidence id + state) and one Activity row."""
    legs = s.q("select * from legs where bundle_id = ? order by seq", b["id"])
    apv = s.one("select * from approvals where bundle_id = ? and state = 'consumed' order by approved_at desc", b["id"])
    eid = evidence(s, operator["id"], "bookings.confirm", digest_of={"bundle_id": b["id"]},
                   sources=[{"service": "dive", "retrieved_at": ts()[:19] + "Z", "sha256": b["read_back_sha256"],
                             "snippet": R.wrap("; ".join(f"{l['title']}: {l['state']}" + (f" ({l['evidence_id']})" if l["evidence_id"] else "")
                                                         for l in legs), "dive", ts()[:19] + "Z")}],
                   outcome={"kind": "CONFIRMED" if state == "confirmed" else "FAILED"},
                   approval={"approval_id": apv["id"], "read_back_sha256": apv["read_back_sha256"], "payload_sha256": apv["payload_sha256"],
                             "approved_at": apv["approved_at"], "method": apv["method"], **({"said": apv["said"]} if apv["said"] else {})} if apv else None)
    s.x("update bundles set state = ?, evidence_id = ?, updated_at = ? where id = ?", state, eid, ts(), b["id"])
    event(s, operator["id"], state, "All confirmed" if state == "confirmed" else "Couldn't confirm — nothing charged", bundle_id=b["id"], evidence_id=eid)


async def supplier_reply(s: Store, operator: dict, leg_id: str, text: str) -> dict:
    """TEST ONLY (EU's sandbox.supplier_reply): play a supplier's answer on any channel. WhatsApp goes through the sandbox's own
    sandbox.simulate_reply (and comes back through messages.replies, like a real one); other channels are recorded here."""
    leg = s.one("select l.* from legs l join bundles b on b.id = l.bundle_id where l.id = ? and b.operator_id = ?", leg_id, operator["id"])
    if not leg:
        raise DiveError("not_found", "No such leg.")
    ch = s.one("select * from channels where id = ?", leg["channel_id"])
    sup = s.one("select * from suppliers where id = ?", leg["supplier_id"])
    if leg["state"] != "requested":
        raise DiveError("invalid_input", f"That leg isn't waiting for an answer (it's {leg['state']}).", {"path": "/leg_id", "rule": "state"})
    if ch["kind"] == "whatsapp":
        r = await CH.whatsapp_simulate_reply(ch["address"], text)
        if not r.get("ok"):
            raise DiveError("upstream_unreachable", "The AgAPI sandbox didn't take the reply.", {"code": (r.get("error") or {}).get("code")})
    else:
        b = s.one("select * from bundles where id = ?", leg["bundle_id"])
        _apply_reply(s, operator, b, leg, sup, ch, "rpl_" + R.new_id("rb")[3:], R.wrap(text, f"{ch['kind']}_supplier", ts()[:19] + "Z"), ts())
    out = await sync(s, operator, leg["bundle_id"])
    got = s.one("select * from legs where id = ?", leg_id)
    return {"leg_id": leg_id, "parse": got["parse"] or R.supplier_reply(text)["parse"], "leg_state": got["state"], "bundle_state": out["state"]}


# ── views ───────────────────────────────────────────────────────────────────────────────────────────────────────────────

def leg_out(s: Store, l: dict) -> dict:
    sup = s.one("select name from suppliers where id = ?", l["supplier_id"])["name"]
    ch = s.one("select kind from channels where id = ?", l["channel_id"])
    return {"leg_id": l["id"], "product_id": l["product_id"], "supplier_id": l["supplier_id"], "channel_id": l["channel_id"], "required": bool(l["required"]),
            "title": l["title"], "supplier": sup, "channel_kind": ch["kind"] if ch else "", "state": l["state"], "starts_at": l["starts_at"],
            **{k: l[k] for k in ("requested_at", "answer_by", "answered_at", "reply_id", "evidence_id", "reference") if l[k]},
            **({"reply": loads(l["reply"])} if l["reply"] else {}), **({"parse": l["parse"]} if l["parse"] else {})}


def bundle_out(s: Store, b: dict) -> dict:
    op = s.one("select * from operators where id = ?", b["operator_id"])
    state = b["state"]
    notes = loads(b.get("notes")) or {}
    if state in ("in_progress", "failed", "confirmed"):
        sentence = _view(s, op, b)[1]
    elif state in ("quoted", "approved"):
        sentence = "Waiting for your yes on your phone."
    elif state == "replaced":   # CR 65 · Accept N: a new read-back for fewer people went to them
        sentence = f"{notes.get('why', 'A supplier can take fewer of you')}. We've sent you a new read-back to approve. Nothing has been charged."
    else:
        sentence = "Your booking is cancelled. Nothing more will be charged."
    out = {"bundle_id": b["id"], "package_id": b["package_id"], "party": b["party"], "starts_at": b["starts_at"],
           "legs": [leg_out(s, l) for l in s.q("select * from legs where bundle_id = ? order by seq", b["id"])], "total": loads(b["total"]),
           "read_back_id": b["read_back_id"], "read_back": {"lines": loads(b["lines"]), "read_back_sha256": b["read_back_sha256"]},
           "state": state, "customer_sentence": sentence, "expires_at": b["expires_at"]}
    if b.get("evidence_id"):
        out["evidence_id"] = b["evidence_id"]
    apv = s.one("select id, state from approvals where bundle_id = ? order by approved_at desc", b["id"])
    if apv:
        out["approval"] = {"approval_id": apv["id"], "state": apv["state"]}
    if notes:
        out["notes"] = notes
    c = s.one("select * from cancellations where bundle_id = ? and state in ('open', 'done') order by created_at desc", b["id"])
    if c:
        ca = s.one("select id, state from approvals where bundle_id = ? order by approved_at desc", c["id"])
        out["cancellation"] = {"cancellation_id": c["id"], "state": c["state"], "lines": loads(c["lines"]),
                               **({"approval": {"approval_id": ca["id"], "state": ca["state"]}} if ca else {})}
    return out
