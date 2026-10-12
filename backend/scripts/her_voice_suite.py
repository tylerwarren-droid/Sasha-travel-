"""Sasha 249 · HER VOICE, in the deploy gate (EU 246 §2; offline: the venue engine's saved answers, no model, no Places, no venue
contacted). Fails on a channel named in anything she is handed to say, and on a second question for the same detail.

  1. the persona carries the voice on /s2, on WhatsApp and on /next under parity — and /next with parity off is untouched
  2. the transcript check itself: it catches a channel name and a re-ask, and passes the demo path's own words
  3. the booking path's words (D3/D4): the question word for word, both choices, the prefilled form's confirmation, the request's
     confirmation, the message they send themselves — every one clean
  4. Sasha 251 · HONEST RESULTS: a scripted turn where search_venues FAILS and the model claims cards → the reply that reaches
     the person says it didn't work (on /s2, WhatsApp and /next under parity; /next with parity off untouched), and the check
     itself catches a claim after a failed tool
"""
from __future__ import annotations

import asyncio
import os
from datetime import datetime, timedelta, timezone

OK: list = []
FAIL: list = []


def check(name: str, cond: bool, why: str = "") -> None:
    (OK if cond else FAIL).append(name)
    print(f"  {'✓' if cond else '✗'} {name}" + ("" if cond else f" — {why}"), flush=True)


DEMO_D3 = [   # the demo path's restaurant beat, as EU 246 §3 writes it
    ("user", "A table for two in Madrid this Thursday at 9pm, somewhere traditional near Sol."),
    ("assistant", "Three traditional places near Sol for Thursday at 9 — the options are below."),
    ("user", "That one."),
    ("assistant", "I'll book it. Want a prefilled form you just confirm, or shall I handle it and let you know?"),
    ("user", "Handle it."),
    ("assistant", "For two on Thursday at 9 — what name should it be under?"),
    ("user", "Alex."),
    ("assistant", "Sent. I'll tell you when they reply."),
]


async def main() -> bool:
    from app.agent import voice as V
    print("HER VOICE — no channel names, one question per detail (Sasha 249)", flush=True)

    # 1 ── the persona, on every surface
    from app.agent import s2 as S2
    from app.services import persona as P
    check("1 /s2 carries her voice", V.RULES.strip() in S2.s2_system() and V.ASK_BOOK in S2.s2_system())
    check("1 WhatsApp carries it (/s2's text + the WhatsApp note)", V.RULES.strip() in S2.s2_system() + S2.WA_NOTE)
    check("1 /next carries it under parity", V.RULES.strip() in S2.S1_CAN)
    check("1 /next with parity off is untouched", V.ASK_BOOK not in P.AGENT_SYSTEM)

    # 2 ── the check itself
    check("2 the demo path's own words are clean", V.faults(DEMO_D3) == [], str(V.faults(DEMO_D3)))
    bad = V.faults([("assistant", "I'll send it on WhatsApp."), ("assistant", "Their SevenRooms page is open."),
                    ("assistant", "I'll try the next rung of the ladder.")])
    check("2 catches a channel named", {b.split(":")[0] for b in bad} == {"turn 0", "turn 1", "turn 2"}, str(bad))
    again = V.faults([("assistant", "What name should it be under?"), ("user", "Alex"), ("assistant", "Great — and what name should I use?")])
    check("2 catches a second question for the same detail", len(again) == 1 and "name again" in again[0], str(again))
    check("2 one question asking for two details is still one each",
          V.faults([("assistant", "What time, and how many people?")]) == [])
    check("2 a URL's /api/ is not the word API", V.channel_words("open https://x.test/api/booking") == [])

    # 3 ── the booking path's words
    from scripts import venue_engine_fake
    venue_engine_fake.install()
    from agapi import venue_truth as VT, venues as VN
    from booking_signer import guest_receipt as GR
    from scripts.venue_truth_suite import CASA, HAMMAM

    class GW:
        STORE = None
        @staticmethod
        def summary(res): return "Thursday at 21:00, 2 people"
        @staticmethod
        def plain_venue(v): return str(v).replace(" (test)", "")
    real_api, real_addr = VN._API, GR.address_of

    async def addr(account): return "guest@example.com"
    VN._API, GR.address_of = (lambda: GW), addr
    said: list = []
    acct = "00000000-0000-4000-8000-000000000250"
    try:
        for venue, surface in ((HAMMAM, "s2"), (CASA, "wa")):
            ctx = type("C", (), {"account": acct, "surface": "s2", "started": datetime.now(timezone.utc), "act_name": None, "idem": None})()
            ch = (await VT.profile(dict(venue))).get("channel") or {}
            rd = {"venue": venue["name"], "place_id": venue["place_id"], "rungs": {}, "country": "ES"}
            res = {"who": {"name": "Alex Gate", "contact": {"mobile_e164": "+34600000000"}}, "how_many": {"count": 2},
                   "when": {"at": (datetime.now(timezone.utc) + timedelta(days=3)).strftime("%Y-%m-%dT21:00")}, "what": {"category": "restaurant"}}
            at = res["when"]["at"]
            q = await VN._engine_route(ctx, {}, rd, res, at, datetime.now(timezone.utc), None, ch, venue)
            said += [q.get("ask") or ""] + [o["title"] for o in q.get("options") or []] + list(q.get("read_back") or [])
            got = await VN._engine_route(ctx, {}, rd, res, at, datetime.now(timezone.utc), "page", ch, venue)
            said += [got.get("say") or "", got.get("line") or ""] + list(got.get("read_back") or [])
            VN._HELD.pop(acct, None)
        check("3 the question, word for word", V.ASK_BOOK in said, str(said[:2]))
        check("3 both choices", "Prefilled form" in said and "Handle it" in said)
        check("3 the prefilled form's confirmation", any(s.startswith(V.DONE_FORM) for s in said))
        lines = [s for s in said if s]
        check("3 nothing she's handed names a channel", V.check(lines) == [], str(V.check(lines)))
        check("3 the request's confirmation is her voice", V.SENT == "Sent. I'll tell you when they reply." and V.check([V.SENT, V.DONE_FORM, V.DONE_FORM_WA]) == [])
    finally:
        VN._API, GR.address_of = real_api, real_addr
        VN._HELD.pop(acct, None)

    # 4 ── Sasha 251 · honest results: a failed tool is never followed by a claim of what it would have shown
    from unittest import mock
    import app.services.llm as LLM
    from agapi import v0 as API
    from app.agent import sasha as AG
    from app.agent.fakes import Block, client
    claim = "Here are a few spots near Sol. Have a look whenever you like and tap one if it tempts you."
    failed = [{"tool": "search_venues", "ok": False}]
    bad = V.honest_faults([{"said": claim, "calls": failed, "rendered": False}])
    check("4 catches a claim after a failed tool", bool(bad) and "search_venues failed" in bad[0], str(bad))
    check("4 her failed line is clean", V.honest_faults([{"said": V.failed_line("search_venues"), "calls": failed}]) == []
          and V.check([V.failed_line(t) for t in V.SHOWS]) == [])

    async def failing(ctx, name, args):
        return {"ok": False, "error": {"code": "unavailable", "message": "the places search isn't answering right now"}}

    async def one(surface: str, parity: str) -> str:
        steps = [[Block(type="tool_use", id="t1", name="search_venues", input={"what": "dinner", "where": "Sol, Madrid"})],
                 [Block(type="text", text=claim)]]
        text = ""
        with mock.patch.object(LLM, "client", client(steps)), mock.patch.object(API, "call", failing), \
                mock.patch.dict(os.environ, {"SASHA_S1_PARITY": parity}):
            async for ev in AG.turn("00000000-0000-4000-8000-000000000251", "Dinner near Sol tonight?", [], f"hv251-{surface}-{parity}",
                                    surface=surface):
                if ev["type"] == "done":
                    text = ev["text"]
        return text
    for surface, parity in (("s2", "on"), ("wa", "on"), ("s1", "on")):
        got = await one(surface, parity)
        check(f"4 {surface}: a failed search is said, never its cards",
              V.honest_faults([{"said": got, "calls": failed}]) == [] and "didn't work" in got, got)
    got = await one("s1", "off")
    check("4 /next with parity off is untouched", got == claim, got)

    print(f"HER VOICE: {len(OK)} passed, {len(FAIL)} failed", flush=True)
    return not FAIL


if __name__ == "__main__":
    os.environ.setdefault("SASHA_GATE", "1")
    raise SystemExit(0 if asyncio.run(main()) else 1)
