"""Sasha 248 · ONE VENUE TRUTH — the three demo paths, in the deploy gate (offline: the venue engine's saved answers, no Places, no
AgAPI, no venue contacted). Tyler's S2 test (12 Oct): (a) a Spanish restaurant labelled "Korean"; (b) the booking form never brought
up; (c) the thumbnails didn't open.

  (a) a Spanish restaurant whose Google category is WRONG ("Korean Restaurant") → shown as Spanish, quoted from its own site
  (b) "a spa for two tomorrow at 17:00" → Hammam Al Ándalus → the fill-or-request question, word for word → "fill it now" → their
      own booking page with every detail, on the phone (the prepared card), recorded as human_tap
  (c) a tap on a place → its detail (the one place shape: what it is, hours, photos, site, Book) — /s2 and /next's sheet, and
      WhatsApp's text + link
"""
from __future__ import annotations

import asyncio
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
    from agapi import venue_truth as VT, venues as VN, s2_outcomes as OC
    print("VENUE TRUTH — the three demo paths (Sasha 248)", flush=True)

    # (a) ── the wrong Google category never stated; the site's own words are
    cards = [dict(CASA)]
    await VT.enrich(cards, budget_s=5)
    c = cards[0]
    check("(a) Spanish, from its own site", c.get("type") == "traditional Spanish restaurant" and c.get("type_source") == "site", f"got {c.get('type')!r}")
    check("(a) quoted, with its page", bool((c["place"]["type"] or {}).get("quote")) and str((c["place"]["type"] or {}).get("source_url", "")).startswith("https://"))
    check("(a) never 'Korean'", "korean" not in str(c.get("type")).lower() and c.get("google_type") == "Korean Restaurant")
    nosite = [{"place_id": "x", "name": "No Site", "type": "Korean Restaurant"}]
    await VT.enrich(nosite, budget_s=1)
    check("(a) Google's category only labelled", nosite[0]["type"] == "listed on Google as Korean Restaurant", nosite[0]["type"])

    # (b) ── the fill-or-request question, then "fill it now" → the prepared page, recorded human_tap
    p = await VT.profile(dict(HAMMAM))
    ch = p.get("channel") or {}
    check("(b) its own booking engine, from the engine", ch.get("kind") == "own_engine" and "madridreservas" in str(ch.get("url")), str(ch))
    check("(b) the question, word for word", ch.get("ask") == VT.ASK_FILL and VT.ASK_FILL.startswith("Want me to fill it in now so you just tap confirm on your phone"))

    class GW:
        STORE = None
        @staticmethod
        def summary(res): return "tomorrow at 17:00, 2 people"
        @staticmethod
        def plain_venue(v): return str(v).replace(" (test)", "")
    real_api, real_addr = VN._API, None
    from booking_signer import guest_receipt as GR
    real_addr = GR.address_of

    async def addr(account): return "guest@example.com"
    VN._API, GR.address_of = (lambda: GW), addr
    try:
        ctx = type("C", (), {"account": "00000000-0000-4000-8000-000000000248", "surface": "s2", "started": datetime.now(timezone.utc)})()
        rd = {"venue": HAMMAM["name"], "place_id": HAMMAM["place_id"], "rungs": {}, "country": "ES"}
        res = {"who": {"name": "Alex Gate", "contact": {"mobile_e164": "+34600000000"}}, "how_many": {"count": 2},
               "when": {"at": (datetime.now(timezone.utc) + timedelta(days=1)).strftime("%Y-%m-%dT17:00")}, "what": {"category": "spa"}}
        at = res["when"]["at"]
        q = await VN._engine_route(ctx, {}, rd, res, at, datetime.now(timezone.utc), None, ch, HAMMAM)
        check("(b) asks before acting", q.get("status") == "choose_route" and q.get("ask") == VT.ASK_FILL
              and [o["route"] for o in q["options"]] == ["page", "email"], str(q)[:200])
        held = await VN._engine_route(ctx, {}, rd, res, at, datetime.now(timezone.utc), "page", ch, HAMMAM)
        check("(b) 'fill it now' → read back first, nothing sent", held.get("status") == "awaiting_yes" and VN._HELD[ctx.account]["rung"] == "prepared")
        out = await VN._book_inner(ctx, VN._HELD[ctx.account], {"said": "yes"}, "Hammam Al Ándalus", "prepared")
        prep = out.get("prepared") or {}
        check("(b) their page + every detail", "madridreservas" in str(prep.get("url")) and {"Day", "Time", "People", "Name", "Mobile"} <= {f["label"] for f in prep.get("fields") or []}, str(prep)[:200])
        from app.agent import sasha as AG
        ev = AG.render("book_venue", out, {})
        check("(b) the prepared card renders", (ev or {}).get("kind") == "prepared")
        check("(b) recorded as human_tap", OC.RUNG.get("prepared") == ("human_tap", "page_handover"))
    finally:
        VN._API, GR.address_of = real_api, real_addr
        VN._HELD.pop("00000000-0000-4000-8000-000000000248", None)

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
