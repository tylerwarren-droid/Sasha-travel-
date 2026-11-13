"""Sasha 211 Part B · VENUE BOOKINGS ON THE AGENT, every route — part of the deploy gate (scripts/gate.py).

  Sasha 381 · THE INSTRUCTION IS THE APPROVAL (Tyler, 12 Nov 20:11): no yes card for a venue — a term not given is asked (only that
  term), and the complete instruction is acted on in the same turn, said in ONE line ("Booking now: …" + Booked / Requested).
  REAL, in-process, on a scratch guest signed in (the in-app session the instruction is proved by): our own Sasha Test Venue (its
  form) — read → hold_venue with the party missing (asked, nothing prepared) → their answer (acted on: AgAPI's act) → the same
  instruction again (never twice) → CONFIRMED in Pacioli's rows (get_status), then cancel_venue's two steps. No real venue is contacted.
  EVERY OTHER ROUTE, against a stand-in for the booking API (it records what was asked of it; nothing leaves the process):
  the booking rules' answers (the ONE question for a form; > 48 h a request; within 48 h a call), the platform page to the phone,
  the email, the call, the form filled in the cloud browser with "Tap to finish" on the phone (the founder's override), the
  WhatsApp-only draft — and never a send without the person's explicit yes in a LATER turn.
"""
from __future__ import annotations
from kanoe_contract import OP  # Sasha 374 · THE ONE generated contract (CR 186)

import asyncio
import os
import sys
import time
import uuid
from datetime import date, datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scripts.flight_suite import RESULTS, ok  # noqa: E402


def _ctx(a: str, said: str = "", via: str = "page", before: str = "", session: str = "venue-suite-real"):
    from agapi import v0 as API   # Sasha 381 · CR 196: a conversation's turn — its id is the instruction's proof in the app
    return API.Ctx(account=a, mode="test", user_said=said, via=via, said_before=before, session=session)   # Sasha 326 · via "wa": asked on WhatsApp


def _words(args: dict) -> str:
    """Sasha 381 · the person's instruction in their own words: every term of the booking given."""
    when = (f" on {args['day']}" if args.get("day") else "") + (f" at {args['time']}" if args.get("time") else "")
    return f"book {args.get('name')}{when} for {args.get('party')}"


async def real_test_venue(a: str) -> None:
    from agapi import v0 as API
    from booking_signer import guest_whatsapp as GW
    from booking_signer.form_rung import test_venue_url
    s, cj = await GW.api(a, "GET", "/api/booking/contact")
    c = (cj or {}).get("consent") or {}
    s, j = await GW.api(a, "PUT", "/api/booking/contact", {"name": "Alex Gate", "mobile": "+447700900211",
                                                            "consent_version": c.get("version"), "consent_sha256": c.get("sha256")})
    ok("VENUE 0: a scratch guest with a contact (fictional, Ofcom's drama range)", s == 200, str(j)[:160])
    day = (date.today() + timedelta(days=4)).isoformat()
    v = {"name": "Sasha Test Venue", "city": "Madrid", "country": "ES", "website": test_venue_url("plain"), "what": "dinner"}
    r = await API.call(_ctx(a), "read_booking_route", v)
    ok("VENUE 1 (Sherlock): read_booking_route says AgAPI's ONE decision for it — their own form, Kanoe sends it (Sasha 378 · CR 188)",
       r.get("ok") and r["result"]["routes"] == ["send_form"] and (r["result"].get("decision") or {}).get("route") == "send_form",
       str(r.get("error") or r.get("result"))[:200])
    first = f"Book the Sasha Test Venue on {day} at 21:00, the form please"
    h = await API.call(_ctx(a, first), "hold_venue", {**v, "day": day, "time": "21:00", "party": 2, "route": "form",
                                                     "idempotency_key": "venue-suite-h1"})
    ok("VENUE 2 (Austen): the party they didn't give is ASKED — only that — never 2, nothing prepared (Sasha 381)",
       h.get("ok") and h["result"]["status"] == "need_term" and h["result"]["ask"] == "For how many people?",
       str(h.get("error") or h.get("result"))[:200])
    b = await API.call(_ctx(a, "for 2", before=first), "hold_venue", {**v, "day": day, "time": "21:00", "party": 2, "route": "form",
                                                                      "idempotency_key": "venue-suite-h2"})
    res = b.get("result") or {}
    # Sasha 319 · ONE SENDER · Sasha 381: their answer completes the instruction — AgAPI's act, in the same turn, Tyler's ONE line
    ok("VENUE 3 (our test venue): the instruction is the approval → AgAPI's act → requested, said “Booking now: …”",
       b.get("ok") and res.get("status") in ("requested", "confirmed") and bool(res.get("act_id"))
       and str(res.get("line") or "").startswith("Booking now: "), str(b.get("error") or res)[:220])
    again = await API.call(_ctx(a, "for 2", before=first), "hold_venue", {**v, "day": day, "time": "21:00", "party": 2, "route": "form",
                                                                          "idempotency_key": "venue-suite-h3"})
    ok("VENUE 4: the same booking again in the conversation is never sent twice",
       again.get("ok") and again["result"]["status"] == "already_sent", str(again.get("error") or again.get("result"))[:160])
    no = await API.call(_ctx(a, "Yes, send it"), "book_venue", {"approval": {"said": "Yes, send it"}, "idempotency_key": "venue-suite-b1"})
    ok("VENUE 5: no card waits for a yes — “yes” alone sends nothing", not (no.get("result") or {}).get("act_id"), str(no)[:160])
    st = await API.call(_ctx(a), "get_status", {})
    vb = (st.get("result") or {}).get("venues") or []
    ok("VENUE 6 (Pacioli): get_status lists it on its day as AgAPI's act — never booked before the venue says so",
       st.get("ok") and any(x["date"] == day and x.get("act_id") and x["status"] in ("requested", "confirmed") for x in vb),
       str(vb)[:220])
    act = next((x["act_id"] for x in vb if x["date"] == day and x.get("act_id")), None)
    c1 = await API.call(_ctx(a, "Cancel it"), "cancel_venue", {"act_id": act, "idempotency_key": "venue-suite-c1"})
    ok("VENUE 7: cancel_venue → its read-back first, back the way it was made; nothing sent yet",
       c1.get("ok") and c1["result"]["status"] == "awaiting_yes", str(c1.get("error") or c1.get("result"))[:200])


class FakeApi:
    """The booking API as the routes answer it — records every call; nothing leaves the process."""
    def __init__(self):
        self.calls = []

    async def __call__(self, account, method, path, body=None, timeout=90.0):
        self.calls.append((method, path, body))
        if path == "/api/booking/draft":
            return 200, {"parts": {"what": {"category": "restaurant", "activity": "table"}}}
        if path == "/api/booking/contact":
            return 200, {"contact": {"name": "Alex Gate", "mobile_e164": "+447700900211"}}
        if path == "/api/booking/forms":
            if body.get("handover"):
                return 200, {"form_id": "f-1", "trip_item_id": "t-1", "read_back": {"lines": ["I'll fill their booking page"], "sha256": "a" * 64}}
            return 403, {"rule": "forms_off", "message": "forms are off"}
        if path == "/api/booking/forms/f-1/handover":
            return 200, {"ok": True, "phone": {"sent": True}, "handover_id": "h-1"}
        if path == "/api/booking/links":
            return 200, {"link_id": "l-1", "trip_item_id": "t-2", "platform": "TheFork", "slot_filled": True,
                         "url": "https://www.thefork.es/restaurante/x-r1", "read_back": {"lines": ["their TheFork page"], "sha256": "b" * 64}}
        if path == "/api/booking/links/l-1/opened":
            return 200, {"url": "https://www.thefork.es/restaurante/x-r1", "status": "link_sent"}
        if path == "/api/booking/emails":
            return 200, {"email_id": "e-1", "trip_item_id": "t-3", "read_back": {"lines": ["I'll email them"], "sha256": "c" * 64}}
        if path == "/api/booking/emails/e-1/send":
            return 200, {"status": "sent", "say": "sent"}
        if path == "/api/booking/calls":
            return 200, {"call_id": "k-1", "trip_item_id": "t-4", "read_back": {"lines": ["I'll call them"], "sha256": "d" * 64}}
        if path == "/api/booking/calls/k-1/place":
            return 200, {"status": "placed"}
        return 404, {"rule": "unknown", "message": path}


async def routes_offline(a: str) -> None:
    from agapi import v0 as API, venues as VN
    from booking_signer import guest_whatsapp as GW, wa_brain as WB
    from agapi import person_access as PA
    from scripts import agapi_decides as AD
    real = (GW.api, GW.tap_platform, VN._read, WB.trip_day_words, GW._tell, GW.STORE, VN.engine_channel)
    taps = []
    fake = FakeApi()

    PHONE = [{"kind": "phone", "value": "+34910000000", "source_kind": "site", "source_label": "their website", "source_url": "https://casagate.example/"}]

    def read_with(rungs: dict, facts=None):
        """What the venue publishes — and Sasha 378 · CR 188: AgAPI's venue.profile for it (its ONE decision, scripts/agapi_decides:
        handoff.decide's shapes in CR 188's order). hold_venue follows that decision; it decides nothing from these rungs."""
        VN.engine_channel = AD.engine_for(rungs, facts)

        async def rd(ctx, args):
            return {"read_id": "r-1", "country": "ES", "venue": "Casa Gate", "facts": facts or [], "rungs": rungs,
                    "open_now": True, "opens_at": None, "say": "", "place_id": args.get("place_id")}
        return rd

    async def tap(account, text, url, link_id=None, venue=None, when=None):
        taps.append(url)
        return "sent (captured)"

    async def where(account, day, venue):
        return "It's in your bookings"
    told = []

    async def tell(ch, text, template=None):
        told.append(text)
        return "sent (captured)"

    class _Store(GW.MemoryGuestStore):   # Sasha 288 · the real store's shape: get_state too (the gate logged its absence)
        async def channel_of_account(self, acct):
            return {"wa_id_sha256": "x" * 64}
    GW.api, GW.tap_platform, WB.trip_day_words = fake, tap, where
    GW._tell, GW.STORE = tell, _Store()
    # Sasha 254 · the founder's override paths read the RECORD: this scratch guest gets a founder record IN THIS PROCESS ONLY (the
    # person_access test hook — never a real grant), its mode kept "test" so every AgAPI call it makes still goes to the sandbox
    PA.install({a: {**PA.FOUNDER_PERSON, "mode": "test"}})
    soon = (datetime.now() + timedelta(hours=20)).strftime("%Y-%m-%d %H:%M").split()
    later = (date.today() + timedelta(days=6)).isoformat()
    v = {"name": "Casa Gate", "city": "Madrid", "country": "ES", "what": "dinner", "party": 2, "place_id": "ChIJcasagatevs"}

    async def instruct(args: dict, key: str, via: str = "page") -> dict:
        """Sasha 381 · ONE turn: their whole instruction (every term theirs) → hold_venue → AgAPI's act, or its hand-over."""
        VN._HELD.pop(a, None)
        # each route is its own conversation (the same booking twice in ONE conversation is "already sent" — VENUE 4)
        return await API.call(_ctx(a, _words({**v, **args}), via, session=f"venue-suite-{key}-{uuid.uuid4().hex[:8]}"), "hold_venue",
                              {**v, **args, "idempotency_key": key + "h"})
    try:
        # Sasha 378 · CR 188 · every route below is AgAPI's ONE decision (venue.profile → handoff.decide), followed — never Sasha's
        VN._HELD.pop(a, None)
        VN._read = read_with({"link": {"value": "TheFork"}, "email": {}, "phone": {"fact_index": 0}}, PHONE)   # a platform venue + its own email
        q = await instruct({"day": later, "time": "21:00"}, "vo-q1")
        ok("VENUE ROUTE · their own email AND a platform → AgAPI's request (CR 188: own channels first), sent on the instruction",
           q.get("ok") and q["result"]["status"] == "requested" and q["result"]["route"] == "agapi"
           and not any(p.endswith("/send") for _m, p, _b in fake.calls), str(q.get("result"))[:200])
        VN._HELD.pop(a, None)
        VN._read = read_with({"phone": {"fact_index": 0}}, PHONE)
        q2 = await instruct({"day": soon[0], "time": soon[1]}, "vo-q2")
        ok("VENUE ROUTE · their phone → AgAPI's call act on the instruction, dialled only from its plan (simulated here)",
           q2.get("ok") and q2["result"]["status"] == "calling" and q2["result"]["route"] == "agapi_call", str(q2.get("error") or q2.get("result"))[:200])
        VN._read = read_with({"form": {}, "link": {"value": "TheFork"}, "email": {}, "phone": {"fact_index": 0}})
        d = await instruct({"day": later, "time": "21:00"}, "vo-q3")
        ok("VENUE ROUTE · their own form → AgAPI's send_form on the instruction — no card, no question of Sasha's own",
           d.get("ok") and d["result"]["status"] in ("requested", "confirmed") and d["result"]["route"] == "agapi" and "options" not in d["result"],
           str(d.get("result"))[:160])
        VN._read = read_with({"link": {"value": "TheFork"}})
        h = await instruct({"day": later, "time": "21:00"}, "vo-p", via="wa")
        hp = h.get("result") or {}
        ok("VENUE ROUTE · a platform the policy keeps closed (TheFork), on WhatsApp: AgAPI's hand-over at once, in its words — never booked",
           h.get("ok") and hp.get("status") == "page_on_phone" and hp.get("route") == "platform" and not hp.get("booked")
           and "You press Book there" in str(hp.get("say")), str(hp or h.get("error"))[:200])
        nt = len(taps)
        h = await instruct({"day": later, "time": "21:00"}, "vo-p2")
        hp = h.get("result") or {}
        ok("VENUE ROUTE · the same on S2: S2's card only — nothing to his WhatsApp (326)",
           h.get("ok") and hp.get("status") in ("page_link", "page_on_phone") and len(taps) == nt and not hp.get("booked"),
           f"{hp or h.get('error')} taps={taps[nt:]}")
        own = lambda: [p for _m, p, _b in fake.calls if p.startswith(("/api/booking/emails", "/api/booking/calls", "/api/booking/forms"))]
        VN._read = read_with({"email": {}, "phone": {"fact_index": 0}}, PHONE)
        b = await instruct({"day": later, "time": "21:00"}, "vo-e")
        ok("VENUE ROUTE · the request: AgAPI's act on the instruction, Requested until they reply — never Sasha's own email (319)",
           b.get("ok") and b["result"]["status"] == "requested" and b["result"].get("act_id") and not own(), str(b.get("error") or b.get("result"))[:160])
        VN._read = read_with({"phone": {"fact_index": 0}}, PHONE)
        b = await instruct({"day": soon[0], "time": soon[1]}, "vo-c")
        ok("VENUE ROUTE · call: AgAPI's call act on the instruction, dialled only from its plan (simulated here)",
           b.get("ok") and b["result"]["status"] == "calling" and not own(), str(b.get("error") or b.get("result"))[:160])
        VN._read = read_with({"form": {}, "link": {"value": "TheFork"}, "email": {}, "phone": {"fact_index": 0}}, PHONE)
        b = await instruct({"day": later, "time": "21:00"}, "vo-f")
        ok("VENUE ROUTE · “handle it” — their form: AgAPI's act sends it (never Sasha's cloud-browser fill, 319)",
           b.get("ok") and b["result"]["status"] in ("requested", "confirmed") and not own(), str(b.get("error") or b.get("result"))[:160])
        VN._HELD.pop(a, None)
        VN._read = read_with({"whatsapp": {"value": "+34 600 000 211"}})
        w = await instruct({"day": later, "time": "21:00"}, "vo-w")
        ok("VENUE ROUTE · WhatsApp-only: AgAPI's decision (they send it from their phone) followed — nothing sent by Sasha",
           w.get("ok") and w["result"].get("route") != "agapi" and not w["result"].get("booked") and not own(),
           str(w.get("error") or w.get("result"))[:200])
        # Sasha 378 · CR 188 · a platform the policy permits (CoverManager — channel-policy/7): Sasha books it on the yes (platform_book)
        VN._read = read_with({"link": {"value": "CoverManager"}})
        h = await instruct({"day": later, "time": "11:00", "what": "a massage", "name": "Spa Gate"}, "vo-spa1", via="wa")
        hp = h.get("result") or {}
        ok("VENUE ROUTE · a permitted platform: AgAPI's platform_book on the instruction — AgAPI presses Book, Booked with its reference",
           h.get("ok") and hp.get("status") == "confirmed" and hp.get("reference") == "GATE-PB" and not own(),
           f"{hp or h.get('error')}"[:240])
        VN._read = read_with({"form": {}}, facts=[{"kind": "challenge", "value": "captcha"}])
        h = await instruct({"day": later, "time": "11:00", "what": "a massage", "name": "Spa Gate"}, "vo-spa2")
        ok("VENUE ROUTE · a spa's own form behind a CAPTCHA: never zero-touch (R13) — their page, never a form Sasha fills (319)",
           h.get("ok") and h["result"].get("status") != "tap_to_finish" and not own(), str(h.get("error") or h.get("result"))[:160])
        # a TATTOO studio that books only on Instagram: AgAPI decides none — THE FLOOR (their page), never booked; nothing sent
        VN._read = read_with({"instagram": {"value": "inkgate.madrid"}})
        h = await instruct({"day": later, "time": "17:00", "what": "a tattoo consultation", "name": "Ink Gate"}, "vo-tat")
        res = h.get("result") or {}
        ok("VENUE ROUTE · a tattoo studio on Instagram only: AgAPI's none — their page (the floor), never booked, nothing sent",
           h.get("ok") and res.get("status") in ("page_link", "page_on_phone", "awaiting_yes") and not res.get("booked") and not own(),
           str(res or h.get("error"))[:200])
        from scripts import venue_engine_fake as VF
        n0 = len(VF.CALLS)
        VN._read = read_with({"email": {}})
        nt = await API.call(_ctx(a, "book Casa Gate for 2 this week at 21:00"), "hold_venue", {**v, "day": later, "time": "21:00",
                                                                                     "idempotency_key": "vo-n"})
        ok("VENUE ROUTE · a day they didn't give: AgAPI names it (term_not_given), she asks ONLY it — nothing prepared, nothing sent (381)",
           nt.get("ok") and nt["result"]["status"] == "need_term" and nt["result"]["ask"] == "Which day?"
           and not {OP.VENUE_PREPARE_BOOKING, OP.VENUE_SUBMIT_BOOKING} & set(VF.CALLS[n0:]), str(nt.get("error") or nt.get("result"))[:160])
    finally:
        GW.api, GW.tap_platform, VN._read, WB.trip_day_words, GW._tell, GW.STORE, VN.engine_channel = real
        PA.uninstall(a)
        VN._HELD.pop(a, None)


async def main() -> int:
    """Sasha 251 · this suite runs as old S1 (SASHA_S1_PARITY=off). Sasha 378 · old S1 follows AgAPI's ONE decision like every surface;
    /s2 and /next under parity: one_truth_suite T16/T27, venue_truth_suite."""
    was = os.environ.get("SASHA_S1_PARITY")
    os.environ["SASHA_S1_PARITY"] = "off"
    try:
        return await _main()
    finally:
        if was is None:
            os.environ.pop("SASHA_S1_PARITY", None)
        else:
            os.environ["SASHA_S1_PARITY"] = was


async def _main() -> int:
    from scripts import places_fake   # Sasha 213 · NO live Google Places from a suite (it costs money) — the founder's say-so only
    places_fake.install()
    if os.getenv("SASHA_FLIGHT_SUITE", "") == "skip":
        print("venue suite SKIPPED (SASHA_FLIGHT_SUITE=skip) — this deploy is not covered")
        return 0
    from booking_signer import routes  # noqa: F401
    from booking_signer import guest_accounts as GA, ops, plan_store as PS
    t0, start = time.time(), len(RESULTS)
    g, why = await GA.create_guest("venue-suite")
    if not g:
        ok("venue suite: scratch guest", False, why)
        return 1
    a = g["account_id"]
    # Sasha 381 · CR 196 · the scratch guest's instruction is PROVED as production proves it: in the app its turn (signed in), on WhatsApp
    # its signed message — AgAPI is the gate's double here, so the proof is signed with the server's own secret, or a scratch one only for
    # this run when the server has none
    from agapi import venue_submit as VS
    tok = VS.TAP.set({"kind": "supabase", "token": "venue-suite"})
    wtok = VS.WA.set({"wa_id": "447700900211", "message_id": "SM" + uuid.uuid4().hex})
    scratch = not os.getenv("SASHA_AGAPI_TAP_SECRET")
    if scratch:
        os.environ["SASHA_AGAPI_TAP_SECRET"] = "venue-suite-" + uuid.uuid4().hex
    try:
        await real_test_venue(a)
        await routes_offline(a)
    except Exception as e:
        ok("the venue suite itself", False, f"{type(e).__name__}: {e}")
    finally:
        VS.TAP.reset(tok)
        VS.WA.reset(wtok)
        if scratch:
            os.environ.pop("SASHA_AGAPI_TAP_SECRET", None)
        try:
            s, _ = await ops.ADMIN("DELETE", f"/admin/users/{a}", {})
            print(f"scratch guest {a[:8]} deleted (HTTP {s})")
        except Exception as e:
            print(f"scratch guest {a[:8]} NOT deleted: {type(e).__name__}")
    mine = RESULTS[start:]
    failed = [n for n, p, _ in mine if not p]
    print(f"\nvenue suite: {len(mine) - len(failed)}/{len(mine)} passed in {time.time() - t0:.0f}s" + (f" — FAILED: {failed}" if failed else ""))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
