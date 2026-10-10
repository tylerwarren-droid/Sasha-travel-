"""CR 74b step 5 · CLAIMS (EU 216 §4): the claims administrator's route + deadlines from the card's OWN terms → the evidence pack (the
Keep + uploads) → the read-back → the person's yes → filed → tracked.

  start    the route (administrator, claims portal/email/phone) and the deadlines (notice / documents) — quoted, scoped to the benefit when
           the terms scope them; a deadline the terms don't give is SAID missing, never assumed. The clause the claim relies on, quoted:
           no clause → no claim (Sasha never files what the terms don't support). The evidence checklist, each missing item with where to get it.
  attach   an upload (receipt, letter, photo…) — sealed under the person's own Keep key (AES-256-GCM), never stored plainly
  file     AgAPI's read-back (the administrator, the clause quoted, the amount, the evidence attached / to follow, the deadline) → the
           person's yes in a later turn (AP6) → one email to the administrator's address from the terms (test mode: captured, never sent;
           live: the email allow-list — a real insurer is refused until Tyler adds it). A portal behind a login: everything prepared, the
           person logs in themselves.
  status   the state, the deadlines with their reminders (−14 / −3 / −1 days), the administrator's replies (their words, untrusted)
Refusal drafting is EU 216's step 8 — not here."""
from __future__ import annotations

import base64
import hashlib
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

from .. import config, rules as R
from ..registry import AgapiError
from ..store import dumps, loads, ts
from . import model as M

KINDS: Dict[str, dict] = {
    "baggage_delay": {"benefit": "travel_insurance", "words": "baggage delay", "clause": ("baggage_delay_limit", "baggage_delay_threshold_hours"),
                      "evidence": ("card_statement_line", "booking_confirmation", "airline_delay_report", "receipts")},
    "baggage_loss": {"benefit": "travel_insurance", "words": "lost baggage", "clause": ("baggage_loss_limit",),
                     "evidence": ("card_statement_line", "booking_confirmation", "airline_delay_report", "receipts", "photos")},
    "trip_delay": {"benefit": "travel_insurance", "words": "trip delay", "clause": ("trip_delay_limit", "trip_delay_threshold_hours"),
                   "evidence": ("card_statement_line", "booking_confirmation", "airline_delay_letter", "receipts")},
    "trip_cancellation": {"benefit": "travel_insurance", "words": "trip cancellation", "clause": ("trip_cancellation_limit", "trip_interruption_limit"),
                          "evidence": ("card_statement_line", "booking_confirmation", "cancellation_proof", "medical_certificate")},
    "rental_damage": {"benefit": "car_rental", "words": "rental car damage", "clause": ("damage_theft_covered", "limit"),
                      "evidence": ("card_statement_line", "rental_agreement", "damage_report", "accident_statement", "photos", "repair_invoice")},
    "purchase_damage_theft": {"benefit": "purchase_protection", "words": "purchase protection", "clause": ("per_claim_limit", "days"),
                              "evidence": ("card_statement_line", "receipts", "photos", "police_report")},
}
WHERE = {
    "card_statement_line": "your card statement, showing it was paid with this card (the bank's app or statement PDF)",
    "booking_confirmation": "the booking confirmation email from the airline, hotel or agent",
    "airline_delay_report": "the airline's Property Irregularity Report (PIR) from the baggage desk, or its delay email",
    "airline_delay_letter": "the airline's written confirmation of the delay (its email or the desk's letter)",
    "receipts": "the receipts for what you spent",
    "photos": "photos of the damage or the item",
    "cancellation_proof": "the confirmation that the trip was cancelled and what wasn't refunded",
    "medical_certificate": "a doctor's certificate, if the reason was illness or injury",
    "rental_agreement": "the rental agreement from the counter",
    "damage_report": "the rental company's damage report or check-in sheet",
    "accident_statement": "the European Accident Statement, if another vehicle was involved",
    "repair_invoice": "the rental company's charge or repair invoice",
    "police_report": "the police report (for a theft)",
}
REMIND_DAYS = (14, 3, 1)
MAX_B64, MEDIA = 7_000_000, ("application/pdf", "image/png", "image/jpeg", "image/webp", "image/heic", "text/plain")


def _tables(store) -> None:
    store.x("create table if not exists claim_cases (account text not null, id text not null, end_user text not null, item_id text not null, "
            "product_id text not null, kind text not null, data text not null, state text not null, created_at text not null, updated_at text not null)")
    store.x("create table if not exists claim_files (account text not null, id text not null, case_id text not null, end_user text not null, "
            "kind text not null, name text not null, media_type text not null, sha256 text not null, size integer not null, nonce blob not null, "
            "ciphertext blob not null, created_at text not null)")
    store.x("create table if not exists claim_replies (account text not null, id text not null, case_id text not null, body text not null, "
            "received_at text not null)")


def _q(c: dict) -> dict:
    return {"claim_id": c["id"], "quote": c["quote"], "source_url": c["source_url"], "read_at": c["read_at"][:10]}


SUBJECT = {"baggage_delay": ("baggage", "luggage", "equipaje"), "baggage_loss": ("baggage", "luggage", "equipaje"),
           "trip_delay": ("delay", "retraso", "trip"), "trip_cancellation": ("cancel", "interrupt", "cancelación", "trip"),
           "rental_damage": ("rental", "vehicle", "auto", "alquiler"), "purchase_damage_theft": ("purchase", "item", "compra")}


def _claims_for(cl: List[dict], field: str, benefit: str, kind: Optional[str] = None) -> Optional[dict]:
    """The claims fact for this benefit (field@benefit) — the one whose quote names the claim's subject first — then a general one."""
    scoped = [c for c in cl if c["benefit"] == "claims" and c["field"] == f"{field}@{benefit}"]
    if kind and len(scoped) > 1:
        words = SUBJECT.get(kind, ())
        scoped.sort(key=lambda c: -sum(1 for w in words if w in c["quote"].lower()))
    return scoped[0] if scoped else next((c for c in cl if c["benefit"] == "claims" and c["field"] == field), None)


def plan(kind: str, incident_date: str, product: str, cl: List[dict], today: Optional[date] = None) -> Dict[str, Any]:
    """Pure: the route, deadlines, clause and checklist from one card's live claims. Vectors pin it."""
    k = KINDS[kind]
    b = k["benefit"]
    route = {f: _claims_for(cl, f, b, kind) for f in ("administrator", "email", "url", "phone")}
    inc = date.fromisoformat(incident_date)
    today = today or date.today()
    deadlines, reminders = [], []
    for f, what in (("notice_deadline_days", "notify the claims administrator"), ("documents_deadline_days", "send the documents")):
        c = _claims_for(cl, f, b, kind)
        if c:
            due = inc + timedelta(days=int(c["value"]))
            deadlines.append({"what": what, "due": due.isoformat(), "days": c["value"], "say": f"{what.capitalize()} by {due.isoformat()}.", **_q(c)})
            reminders += [{"on": (due - timedelta(days=n)).isoformat(), "for": what, "due": due.isoformat()} for n in REMIND_DAYS
                          if due - timedelta(days=n) >= today]
        else:
            deadlines.append({"what": what, "due": None, "say": f"The terms I've read don't give a deadline to {what}: ask the claims line, and don't wait."})
    clause = [c for c in cl if c["benefit"] == b and c["field"].split("@")[0] in k["clause"]]
    return {"kind": kind, "benefit": b, "card": product,
            "route": {f: ({"value": c["value"], **_q(c)} if c else None) for f, c in route.items()},
            "deadlines": deadlines, "reminders": sorted(reminders, key=lambda r: r["on"]),
            "clause": [_q(c) for c in clause], "covered_in_terms": bool(clause)}


def checklist(kind: str, files: List[dict], keep_refs: List[str]) -> List[dict]:
    have: Dict[str, List[str]] = {}
    for f in files:
        have.setdefault(f["kind"], []).append(f["name"])
    out = []
    for item in KINDS[kind]["evidence"]:
        got = have.get(item) or ([f"from your Keep: {m}" for m in keep_refs] if item == "booking_confirmation" and keep_refs else [])
        out.append({"item": item, "have": got, **({} if got else {"missing": True, "where": WHERE[item]})})
    return out


async def _card(ctx, uid: str, item_id: str):
    from .ops import _live, _my_cards
    c = next((c for c in await _my_cards(ctx, uid) if c["item_id"] == item_id), None)
    if not c:
        raise AgapiError("not_found", "That card isn't in this person's cards.", {"card_item_id": item_id})
    p = c["_p"]
    if not p or not p["accepted_at"] or not M.is_beta(p):
        raise AgapiError("invalid_input", "This card's official terms haven't been read and checked yet, so no claim can be prepared from them.",
                         {"path": "/card_item_id", "rule": "terms_not_checked"})
    return c, p, _live(ctx.store, p)


def _case(ctx, uid: str, cid: str) -> dict:
    _tables(ctx.store)
    row = ctx.store.one("select * from claim_cases where account = ? and end_user = ? and id = ?", ctx.account, uid, cid)
    if not row:
        raise AgapiError("not_found", "No such claim for this person.", {"case_id": cid})
    return row


def _files(ctx, cid: str) -> List[dict]:
    return ctx.store.q("select id, kind, name, media_type, sha256, size, created_at from claim_files where account = ? and case_id = ? order by created_at",
                       ctx.account, cid)


def _keep_refs(ctx, uid: str) -> List[str]:
    return [r["masked"] for r in ctx.store.q("select masked from keep_items where account = ? and end_user = ? and type = 'booking_reference'",
                                            ctx.account, uid)]


def _out(ctx, row: dict) -> dict:
    d = loads(row["data"])
    files = _files(ctx, row["id"])
    reps = ctx.store.q("select id, body, received_at from claim_replies where account = ? and case_id = ? order by received_at", ctx.account, row["id"])
    return {"case_id": row["id"], "state": row["state"], "card": d["plan"]["card"], "kind": row["kind"], "incident": d["incident"],
            "route": d["plan"]["route"], "deadlines": d["plan"]["deadlines"], "reminders": d["plan"]["reminders"], "clause": d["plan"]["clause"],
            "evidence": checklist(row["kind"], files, _keep_refs(ctx, row["end_user"])),
            "files": [{k: f[k] for k in ("id", "kind", "name", "media_type", "sha256", "size")} for f in files],
            "replies": [{"reply_id": r["id"], "received_at": r["received_at"], "text": R.wrap(r["body"], "claims_administrator", r["received_at"][:19] + "Z", cap=4000)}
                        for r in reps], **({"act_id": d["act_id"]} if d.get("act_id") else {}), **({"note": d["note"]} if d.get("note") else {})}


async def start(ctx, inp: dict):
    from ..engine import _end_user
    uid = inp["end_user"]
    _end_user(ctx, uid)
    _tables(ctx.store)
    try:
        date.fromisoformat(inp["incident_date"])
    except ValueError:
        raise AgapiError("invalid_input", "The incident date is YYYY-MM-DD.", {"path": "/incident_date", "rule": "date"})
    c, p, cl = await _card(ctx, uid, inp["card_item_id"])
    pl = plan(inp["kind"], inp["incident_date"], c["product"], cl)
    if not pl["covered_in_terms"]:
        return {"state": "not_in_terms", "card": c["product"], "kind": inp["kind"],
                "say": f"The terms I've read for {c['product']} don't cover {KINDS[inp['kind']]['words']}, so I won't file a claim they don't support. "
                       "Ask the claims line if you think they do.", "route": pl["route"]}, 200, None
    cid = R.new_id("clm")
    incident = {"date": inp["incident_date"], "description": R.wrap(inp.get("description") or "", "user_named", ts()[:19] + "Z", cap=1000)["text"],
                **({"amount": {"amount_minor": inp["amount_minor"], "currency": inp.get("currency") or "EUR"}} if inp.get("amount_minor") else {})}
    ctx.store.x("insert into claim_cases (account, id, end_user, item_id, product_id, kind, data, state, created_at, updated_at) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                ctx.account, cid, uid, inp["card_item_id"], p["id"], inp["kind"], dumps({"plan": pl, "incident": incident}), "preparing", ts(), ts())
    return _out(ctx, _case(ctx, uid, cid)), 201, None


async def attach(ctx, inp: dict):
    from agapi import keep as K
    from .. import keep_ops as KO
    uid = inp["end_user"]
    row = _case(ctx, uid, inp["case_id"])
    if inp["kind"] not in KINDS[row["kind"]]["evidence"]:
        raise AgapiError("invalid_input", "That isn't evidence this claim uses.", {"path": "/kind", "rule": "enum"})
    if inp["media_type"] not in MEDIA or len(inp["content_base64"]) > MAX_B64:
        raise AgapiError("invalid_input", "A PDF, an image or plain text, 5 MB at most.", {"path": "/media_type", "rule": "enum"})
    try:
        raw = base64.b64decode(inp["content_base64"], validate=True)
    except Exception:
        raise AgapiError("invalid_input", "The file isn't valid base64.", {"path": "/content_base64", "rule": "base64"})
    if K.looks_like_card(raw[:200_000].decode("latin-1", "ignore")):
        raise AgapiError("invalid_input", "That file shows a full card number; cover it (keep only the last four) and upload it again.",
                         {"path": "/content_base64", "rule": "never_card"})
    dek = await KO._dek(ctx, uid, create=True)
    fid = R.new_id("cfl")
    nonce, ct = K.seal(dek, K.item_aad(ctx.account, uid, fid, "claim_file"), {"b64": base64.b64encode(raw).decode()})
    ctx.store.x("insert into claim_files (account, id, case_id, end_user, kind, name, media_type, sha256, size, nonce, ciphertext, created_at) "
                "values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", ctx.account, fid, row["id"], uid, inp["kind"], (inp.get("name") or inp["kind"])[:120],
                inp["media_type"], "sha256:" + hashlib.sha256(raw).hexdigest(), len(raw), nonce, ct, ts())
    raw = None
    return _out(ctx, _case(ctx, uid, row["id"])), 201, None


async def file(ctx, inp: dict):
    from .. import adapters as AD, engine as E
    uid = inp["end_user"]
    row = _case(ctx, uid, inp["case_id"])
    if row["state"] == "filed":
        raise AgapiError("already_completed", "This claim was already filed.", {"act_id": loads(row["data"]).get("act_id")})
    d = loads(row["data"])
    pl, inc = d["plan"], d["incident"]
    email = (pl["route"].get("email") or {}).get("value")
    if not email:
        url = (pl["route"].get("url") or {}).get("value")
        d["note"] = (f"The claims administrator's route in the terms is {'their portal: ' + url if url else 'not an email'}; it needs your own login. "
                     "Everything is prepared below; you file it there yourself — Sasha never logs in for you.")
        ctx.store.x("update claim_cases set data = ?, state = 'ready_for_portal', updated_at = ? where account = ? and id = ?", dumps(d), ts(), ctx.account, row["id"])
        return _out(ctx, _case(ctx, uid, row["id"])), 200, None
    files = _files(ctx, row["id"])
    ev = checklist(row["kind"], files, _keep_refs(ctx, uid))
    admin = (pl["route"].get("administrator") or {}).get("value") or "the claims administrator"
    amount = inc.get("amount")
    amt = f"{amount['currency']} {amount['amount_minor'] / 100:,.2f}" if amount else "to be confirmed with the receipts"
    notice = next((x for x in pl["deadlines"] if x.get("due") and x["what"].startswith("notify")), None)
    lines = [f"File a {KINDS[row['kind']]['words']} claim on your {pl['card']} with {admin}, by email to {email}.",
             f"What happened ({inc['date']}): {(inc['description'][:200] or 'as you described it').rstrip('.')}.",
             f"Amount claimed: {amt}.",
             "The terms it relies on: " + " ".join(f"\"{q}\"" for q in list(dict.fromkeys(c["quote"] for c in pl["clause"]))[:2]),
             "Attached: " + (", ".join(f"{f['name']} ({f['kind'].replace('_', ' ')})" for f in files) or "nothing yet") + ".",
             "To follow: " + (", ".join(e["item"].replace("_", " ") for e in ev if e.get("missing")) or "nothing") + ".",
             (f"Deadline: notify by {notice['due']} (the terms: \"{notice['quote']}\")." if notice else
              "Deadline: the terms I've read don't give one — this goes now.")]
    body = "\n".join(["Hello,", f"I'd like to make a {KINDS[row['kind']]['words']} claim under the benefits of my {pl['card']}.",
                      f"Date of the incident: {inc['date']}.", f"What happened: {inc['description'] or '-'}", f"Amount: {amt}.",
                      "Documents: " + (", ".join(f"{f['name']} (sha256 {f['sha256'][7:19]}…)" for f in files) or "to follow") + ".",
                      "Please confirm receipt and tell me what else you need.", "Thank you."])
    if ctx.mode == "live":   # allow-listed only, BEFORE the read-back (a real insurer is refused until it's on the list)
        AD.precheck_live("messages.send_email", {"to": {"address": email}}, ctx.store, ctx.account)
    payload = {"case_id": row["id"], "to": email, "body_sha256": R.sha256(body), "files": [f["sha256"] for f in files]}
    psha = R.sha256(payload)
    rb = ctx.store.one("select r.* from read_backs r join intents i on i.account = r.account and i.id = r.intent_id where r.account = ? "
                       "and i.operation = 'cards.claim_file' and i.state = 'open' and i.end_user = ? and r.payload_sha256 = ? "
                       "order by r.created_at desc", ctx.account, uid, psha)
    if not rb or E._rb_state(rb) in ("expired", "void"):
        iid = R.new_id("int")
        ctx.store.x("insert into intents (account, id, operation, end_user, state, created_at) values (?, ?, 'cards.claim_file', ?, 'open', ?)",
                    ctx.account, iid, uid, ts())
        rb = E._new_read_back(ctx, iid, "cards.claim_file", lines, payload, None, uid, True)
    it = ctx.store.one("select * from intents where account = ? and id = ?", ctx.account, rb["intent_id"])
    apv = E._check_and_consume(ctx, rb, {"intent_id": it["id"], "operation": "cards.claim_file", "lines": lines, "payload": payload}, 1)
    aid = R.new_id("act")
    sent = await AD.messenger("email", ctx.mode).adeliver(ctx.store, ctx.account, uid, email, "email",
                                                          f"From: {config.EMAIL_FROM}\nReply-To: {config.EMAIL_FROM}\nSubject: {KINDS[row['kind']]['words'].capitalize()} "
                                                          f"claim — {pl['card']}\n\n{body}", None)
    now = ts()[:19] + "Z"
    words = f"Claim filed with {admin} by email" + (" (sandbox: captured, never sent)" if not sent else f" (message {sent})") + "."
    outcome = {"kind": "REQUESTED", "reference": sent or f"sbx_claim_{aid[-8:].lower()}", "target_words": R.wrap(words, "agapi", now)}
    E._new_act(ctx, aid, it, "card_claim", None, outcome, target=row["id"])
    eid = E._evidence(ctx, "cards.claim_file", aid, it["id"], {"case_id": row["id"]}, outcome, apv,
                      [{"service": "card_terms", "retrieved_at": now, "sha256": R.sha256([c["quote"] for c in pl["clause"]]),
                        "snippet": R.wrap(pl["clause"][0]["quote"], "card_terms", now)},
                       {"service": "message", "retrieved_at": now, "sha256": R.sha256(body), "snippet": R.wrap(f"to {email}", "agapi", now)}])
    ctx.store.x("update acts set evidence_id = ? where account = ? and id = ?", eid, ctx.account, aid)
    ctx.store.x("update intents set state = 'confirmed' where account = ? and id = ?", ctx.account, it["id"])
    d["act_id"] = aid
    ctx.store.x("update claim_cases set data = ?, state = 'filed', updated_at = ? where account = ? and id = ?", dumps(d), ts(), ctx.account, row["id"])
    return {**_out(ctx, _case(ctx, uid, row["id"])), "outcome": outcome, "evidence_id": eid}, 201, eid


async def status(ctx, inp: dict):
    return _out(ctx, _case(ctx, inp["end_user"], inp["case_id"])), 200, None


async def simulate_reply(ctx, inp: dict):
    """Test mode: the claims administrator answers (EU 216's fake insurer inbox). Their words, stored as untrusted text."""
    row = _case(ctx, inp["end_user"], inp["case_id"])
    if row["state"] != "filed":
        raise AgapiError("invalid_input", "Only a filed claim gets replies.", {"path": "/case_id", "rule": "not_filed"})
    ctx.store.x("insert into claim_replies (account, id, case_id, body, received_at) values (?, ?, ?, ?, ?)", ctx.account, R.new_id("rpl"), row["id"],
                str(inp["text"])[:4000], ts())
    return _out(ctx, _case(ctx, inp["end_user"], row["id"])), 200, None


OPS = {"cards.claim_start": start, "cards.claim_attach": attach, "cards.claim_file": file, "cards.claim_status": status,
       "cards.claim_simulate_reply": simulate_reply}
