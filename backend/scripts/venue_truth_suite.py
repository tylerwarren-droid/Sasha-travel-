"""Sasha 248 · ONE VENUE TRUTH — the three demo paths, in the deploy gate (offline: the venue engine's saved answers, no Places, no
AgAPI, no venue contacted). Tyler's S2 test (12 Oct): (a) a Spanish restaurant labelled "Korean"; (b) the booking form never brought
up; (c) the thumbnails didn't open.

  (a) a Spanish restaurant whose Google category is WRONG ("Korean Restaurant") → shown as Spanish, quoted from its own site
  (b) "a spa for two tomorrow at 17:00" → Hammam Al Ándalus → AgAPI's ONE decision (Sasha 378 · CR 188: venue.profile →
      handoff.decide — their own email, Kanoe sends) → followed: AgAPI's read-back held for the ONE yes; Sasha asks no question of
      her own and chooses no channel
  (c) a tap on a place → its detail (the one place shape: what it is, hours, photos, site, Book) — /s2 and /next's sheet, and
      WhatsApp's text + link
"""
from __future__ import annotations
from kanoe_contract import OP  # Sasha 374 · THE ONE generated contract (CR 186)

import asyncio
import os
import uuid
from datetime import datetime, timedelta, timezone

OK: list = []
FAIL: list = []


def check(name: str, cond: bool, why: str = "") -> None:
    (OK if cond else FAIL).append(name)
    print(f"  {'✓' if cond else '✗'} {name}" + ("" if cond else f" — {why}"), flush=True)


CASA = {"place_id": "ChIJtestcasalucio", "name": "Casa Lucio (test)", "website": "https://www.casalucio.es", "type": "Korean Restaurant",
        "rating": 4.5, "rating_count": 5200, "listing_url": "https://www.google.com/maps/place/?q=place_id:ChIJtestcasalucio",
        "gphoto": {"uri": "https://lh3.googleusercontent.com/test-casa"}}
HAMMAM = {"place_id": "ChIJtesthammam", "name": "Hammam Al Ándalus (test)", "website": "https://madrid.hammamalandalus.com", "type": "Spa",
          "rating": 4.6, "rating_count": 6100}


async def main() -> bool:
    from scripts import venue_engine_fake
    venue_engine_fake.install()
    from agapi import venue_truth as VT, venues as VN
    print("VENUE TRUTH — the three demo paths (Sasha 248)", flush=True)

    # (a) ── the wrong Google category never stated; the site's own words are
    cards = [dict(CASA)]
    await VT.enrich(cards, budget_s=5)
    c = cards[0]
    check("(a) Spanish, from its own site", "spanish" in str(c.get("type")).lower() and c.get("type_source") == "site", f"got {c.get('type')!r}")
    check("(a) the map's 'Korean' kept only as what the map says", (c["place"]["type"] or {}).get("map_says") == "Korean restaurant")
    check("(a) its own photos first", str((c["place"].get("photos") or [""])[0]).startswith("https://casalucio.es/") and c["place"].get("photos_source") == "site")
    check("(a) quoted, with its page", bool((c["place"]["type"] or {}).get("quote")) and str((c["place"]["type"] or {}).get("source_url", "")).startswith("https://"))
    check("(a) never 'Korean'", "korean" not in str(c.get("type")).lower() and c.get("google_type") == "Korean Restaurant")
    nosite = [{"place_id": "x", "name": "No Site", "type": "Korean Restaurant"}]
    await VT.enrich(nosite, budget_s=1)
    check("(a) no site read: nothing said about what it is — never the map's category (Sasha 250)", nosite[0]["type"] is None
          and nosite[0]["place"].get("map_says") == "Korean Restaurant", str(nosite[0].get("type")))

    # (b) ── Sasha 378 · CR 188: how they book is AgAPI's ONE decision (venue.profile → handoff.decide); Sasha follows it
    p = await VT.profile(dict(HAMMAM))
    ch = p.get("channel") or {}
    check("(b) AgAPI's decision: their own email, Kanoe sends (CR 188's order)",
          (ch.get("route"), str(ch.get("channel") or "").lower()) == ("message", "email") and "ask" not in ch, str(ch))
    check("(b) no question of Sasha's own, no channel of Sasha's own (ASK_FILL / read_channel / rules_for are gone)",
          not any(hasattr(m, n) for m, n in ((VT, "ASK_FILL"), (VN, "read_channel"), (VN, "rules_for"), (VN, "_execute"), (VN, "chosen_route"))))

    from agapi import venue_submit as VS
    from booking_signer import guest_receipt as GR
    real_addr, real_call = GR.address_of, VS.CALL

    async def addr(account): return "guest@example.com"
    GR.address_of = addr
    VS.CALL = venue_engine_fake.submit_answer   # AgAPI's sender, answered from the saved shape — nothing reaches AgAPI or the venue
    acct = "00000000-0000-4000-8000-000000000248"
    # Sasha 381 · a signed-in turn (the in-app session its instruction is proved by, CR 196); AgAPI is the gate's double here
    tok = VS.TAP.set({"kind": "supabase", "token": "venue-truth"})
    scratch = not os.getenv("SASHA_AGAPI_TAP_SECRET")
    if scratch:
        os.environ["SASHA_AGAPI_TAP_SECRET"] = "venue-truth-" + uuid.uuid4().hex
    try:
        ctx = type("C", (), {"account": acct, "surface": "s2", "started": datetime.now(timezone.utc), "user_said": "a spa for two tomorrow at 17:00",
                             "idem": None, "act_name": None, "claimed": None, "session": "venue-truth-" + uuid.uuid4().hex,
                             "turn": "turn_" + uuid.uuid4().hex, "said_before": ""})()
        rd = {"venue": HAMMAM["name"], "place_id": HAMMAM["place_id"], "rungs": {}, "country": "ES"}
        res = {"who": {"name": "Alex Gate", "contact": {"mobile_e164": "+34600000000"}}, "how_many": {"count": 2},
               "when": {"at": (datetime.now(timezone.utc) + timedelta(days=1)).strftime("%Y-%m-%dT17:00")}, "what": {"category": "spa"}}
        before = len(venue_engine_fake.CALLS)
        out = await VN.one_decision(ctx, {}, rd, res, res["when"]["at"], datetime.now(timezone.utc), dict(HAMMAM), VT.decision(dict(HAMMAM)))
        calls = venue_engine_fake.CALLS[before:]
        check("(b) followed: AgAPI's act on the instruction — sent in the same turn, nothing waits for a yes (Sasha 381)",
              out.get("status") in ("requested", "confirmed") and str(out.get("line") or "").startswith("Booking now: ")
              and acct not in VN._HELD, str(out)[:240])
        after = calls[calls.index(OP.VENUE_PREPARE_BOOKING):] if OP.VENUE_PREPARE_BOOKING in calls else []
        check("(b) prepared by AgAPI (venue.prepare_booking), the instruction recorded (approvals.mandate, CR 196), then ONE submit — no tap",
              [c for c in after if c != OP.USERS_REGISTER] == [OP.VENUE_PREPARE_BOOKING, OP.APPROVALS_MANDATE, OP.VENUE_SUBMIT_BOOKING],
              str(calls))
    finally:
        GR.address_of, VS.CALL = real_addr, real_call
        VN._HELD.pop(acct, None)
        VS.TAP.reset(tok)
        if scratch:
            os.environ.pop("SASHA_AGAPI_TAP_SECRET", None)

    ch2 = (await VT.profile(dict(CASA))).get("channel") or {}
    check("(b) a WhatsApp venue: AgAPI's decision — a message they send", (ch2.get("route"), ch2.get("channel")) == ("message", "WhatsApp"), str(ch2))

    # (c) ── a tap opens the detail: the one shape (sheet on /s2 and /next) and WhatsApp's text + link
    d = await VT.profile(dict(CASA))
    check("(c) the sheet's facts", all(k in d for k in ("type", "hours", "photos", "website", "channel")) and d["photos"] and d["website"])
    t = VT.text(d)
    check("(c) WhatsApp: the same, as text + link", "Casa Lucio" in t and "https://www.casalucio.es" in t and "their site" in t, t[:160])
    VN.remember_cards("00000000-0000-4000-8000-000000000249", [dict(CASA)])
    from booking_signer import wa_agent as WA

    class Out:
        def __init__(self): self.items = []
        def text(self, s): self.items.append(s)
    o = Out()
    await WA.place_detail("00000000-0000-4000-8000-000000000249", CASA["place_id"], o)
    check("(c) WhatsApp's tap sends it", bool(o.items) and "casalucio.es" in o.items[0])

    print(f"VENUE TRUTH: {len(OK)} passed, {len(FAIL)} failed", flush=True)
    return not FAIL


if __name__ == "__main__":
    raise SystemExit(0 if asyncio.run(main()) else 1)
