"""Sasha 213 · SAY = SHOW — thirty conversations with the /next agent (the voice path: turn_with_quiver), scratch guests,
EVERY SEND BLOCKED in the process (no venue, no phone, no booking), Duffel replayed, Google Places and the models live.
Part of the deploy gate (scripts/gate.py).

Checked in every turn (each judged on what reached the screen and the speaker, not on what the code meant to do):
  · every place she NAMES is a card (or an item on screen) of THAT turn — names found independently of the agent's own
    check (a separate extractor), matched against the turn's render events
  · the ribbon agrees with what she says: "no X found" is never beside a place she names; cards on the ribbon are never
    described as "none found"
  · no stale results: every render event of a turn carries that turn's id; the state's cards are that turn's cards; the
    highlight is one of them
And it MEASURES (for 4 · cards arrive with her words): her first word → the cards visible, per venue turn —
  after:  the cards are in the render event (the tool's own result) → visible when it arrives
  before: the cards came from a SECOND search the card made when it mounted (/venues/find, cold) → visible after that too;
          reconstructed per turn as render + that search's measured latency for the same query
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import sys
import time
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scripts.flight_suite import RESULTS, ok  # noqa: E402

C = [  # (name, lines) — venue-heavy: the place where words and cards drifted
    ("seafood Madrid", ["Find me a seafood restaurant in Madrid tonight for 2, around 9pm.", "Which one would you pick?"]),
    ("tapas Madrid", ["Somewhere for tapas in La Latina on Friday at 8, four of us.", "Tell me about the second one."]),
    ("spa Madrid", ["Find me a spa in Madrid for a massage for 2 on Saturday at 11am.", "Your favourite, please."]),
    ("tattoo Madrid", ["A tattoo studio in Madrid for a consultation next Tuesday at 5pm, just me.", "Which has the best reviews?"]),
    ("brunch Madrid", ["Brunch in Malasaña on Sunday at 11 for 2.", "Any of them with a terrace?"]),
    ("sushi Madrid", ["The best sushi in Salamanca, Madrid, tomorrow at 9pm for 2.", "What's your pick and why?"]),
    ("rooftop bar Madrid", ["A rooftop bar in Madrid tonight at 10 for 3.", "Which is the most relaxed?"]),
    ("vegan Madrid", ["A vegan restaurant in Madrid on Thursday at 8:30 for 2.", "Is the first one any good?"]),
    ("Indian Madrid", ["Indian food in Madrid tonight for 2 at 9.", "Which one would you book?"]),
    ("hotel Madrid", ["A boutique hotel in Madrid for two nights from next Friday for 2.", "Which is the best rated?"]),
    ("Lisbon dinner", ["A restaurant in Lisbon with fado on Saturday at 9pm for 2.", "Which would you go to?"]),
    ("Lisbon pastry", ["A café in Lisbon for pastéis de nata tomorrow morning at 10.", "Pick one for me."]),
    ("Paris bistro", ["A classic bistro in Paris on Friday at 8pm for 2.", "Which one is the most romantic?"]),
    ("Paris spa", ["A spa in Paris on Sunday at 3pm for one.", "Your favourite?"]),
    ("Rome trattoria", ["A trattoria in Trastevere, Rome, Saturday at 8:30 for 4.", "Which do you like best?"]),
    ("Tokyo ramen", ["Ramen in Shinjuku, Tokyo, tomorrow at 7pm for 2.", "Which is the most famous?"]),
    ("NYC steak", ["A steakhouse in Manhattan on Friday at 8 for 2.", "Which would you choose?"]),
    ("London pub", ["A pub with Sunday roast in London this Sunday at 1pm for 4.", "Any recommendation?"]),
    ("Barcelona tapas", ["Tapas in the Gothic Quarter, Barcelona, Saturday 9pm for 2.", "Which is your favourite?"]),
    ("Mexico City tacos", ["Tacos in Roma Norte, Mexico City, tonight at 8 for 2.", "Which should we try?"]),
    ("Marrakech riad dinner", ["Dinner in a riad in Marrakech on Friday at 8pm for 2.", "Which is the most beautiful?"]),
    ("Kyoto kaiseki", ["A kaiseki dinner in Kyoto next Wednesday at 7pm for 2.", "Which one?"]),
    ("Madrid book (no yes)", ["A seafood restaurant in Madrid on Saturday at 9pm for 2.", "The first one, please.", "Hmm, let me think."]),
    ("spa book (no yes)", ["A spa in Madrid on Saturday at 11 for 2.", "The second one, please.", "Not yet."]),
    ("Lisbon trip", ["Hi, I'm Tyler. Two of us, a week in Portugal from 22 November, wine and the coast, flying from Madrid.",
                     "Which hotel is in Lisbon?"]),
    ("Japan trip", ["Ten days in Japan from 22 November for 2, temples and food, flying from Madrid.", "Where do we stay in Kyoto?"]),
    ("Morocco trip", ["Eight days in Morocco from 22 November, two of us, markets and the desert, flying from Madrid.",
                      "Tell me about the hotel in Marrakech."]),
    ("Ecuador trip", ["Twelve days around Ecuador from 22 November for 2, nature and food, from Madrid.", "What's the hotel in Quito like?"]),
    ("restaurant then change", ["A seafood restaurant in Madrid tonight for 2.", "Actually, make it Italian instead."]),
    ("two cities", ["A wine bar in Lisbon on Friday at 7.", "And one in Porto on Saturday at 7?"]),
]
_STALE_WORDS = re.compile(r"(?i)\b(?:couldn'?t find|none (?:fit|found)|no (?:places|restaurants|spas|bars|hotels|cafés|studios)\b)")


async def extract_names(text: str) -> list:
    """An INDEPENDENT extractor (its own prompt, its own model), so the suite never grades the agent's check with itself."""
    if not text or not re.search(r"[A-Z]", text[1:]):
        return []
    from app.services.llm import client
    r = await client.messages.create(model=os.getenv("SAY_SHOW_JUDGE_MODEL", "claude-sonnet-5-5"), max_tokens=300, system=(
        "You audit a travel assistant's reply. List every specific named business it mentions — a restaurant, bar, café, "
        "hotel, spa, studio, shop or similar — exactly as written. Exclude cities, neighbourhoods, streets, landmarks, "
        "countries, airlines, platforms, dishes, cuisines and people. Answer with a JSON array of strings, [] if none."),
        messages=[{"role": "user", "content": text[:2000]}])
    raw = "".join(getattr(b, "text", "") for b in r.content)
    try:
        return [str(x) for x in json.loads(raw[raw.find("["): raw.rfind("]") + 1])] if "[" in raw else []
    except ValueError:
        return []


async def one(name: str, lines: list, timing: list) -> dict:
    from booking_signer import guest_accounts as GA, guest_whatsapp as GW, ops
    from app.agent import sasha as AG
    g, why = await GA.create_guest("say-show")
    if not g:
        return {"name": name, "fail": [f"no scratch guest: {why}"], "turns": []}
    a = g["account_id"]
    s, cj = await GW.api(a, "GET", "/api/booking/contact")
    c = (cj or {}).get("consent") or {}
    await GW.api(a, "PUT", "/api/booking/contact", {"name": "Alex Show", "mobile": "+447700900213", "consent_version": c.get("version"),
                                                     "consent_sha256": c.get("sha256")})
    session = f"say-show-{uuid.uuid4().hex[:8]}"
    history, turns, fail = [], [], []
    try:
        for said in lines:
            t0 = time.perf_counter()
            tr = {"user": said, "spoken": [], "text": "", "renders": [], "state": None, "first_say": None, "render_at": None, "key": None}
            async for ev in AG.turn_with_quiver(a, said, history, session):
                now = time.perf_counter() - t0
                if ev["type"] == "say":
                    tr["spoken"].append(ev["text"])
                    tr["first_say"] = tr["first_say"] if tr["first_say"] is not None else now
                elif ev["type"] == "render":
                    tr["renders"].append(ev)
                    if ev.get("kind") == "venues" and tr["render_at"] is None:
                        tr["render_at"] = now
                elif ev["type"] == "state":
                    tr["state"] = ev
                elif ev["type"] == "done":
                    tr["text"] = ev["text"]
            history += [{"role": "user", "content": said}, {"role": "assistant", "content": tr["text"]}]
            turns.append(tr)
        if "trip" not in name and not any(((r.get("preset") or {}).get("cards") or r.get("card") or r.get("cards")) for tr in turns for r in tr["renders"]):
            fail.append("a venue conversation that put no cards on screen (a failed search is a failure, never a pass)")
        for tr in turns:
            key = (tr["state"] or {}).get("turn")
            on_screen = set()
            for ev in tr["renders"]:
                if ev.get("turn") != key:
                    fail.append(f"a stale render (turn {ev.get('turn')} in turn {key})")
                for cd in ((ev.get("preset") or {}).get("cards") or []):
                    on_screen.add(cd.get("name") or "")
                for card in ev.get("cards") or []:
                    for o in card.get("options") or []:
                        on_screen.add(o.get("name") or "")
                if ev.get("card"):
                    for o in ev["card"].get("options") or []:
                        on_screen.add(o.get("name") or "")
            st = tr["state"] or {}
            ids = {cd.get("place_id") for ev in tr["renders"] for cd in ((ev.get("preset") or {}).get("cards") or [])}
            if not st.get("carried") and set(st.get("cards") or []) - ids:
                fail.append("the state shows cards no render of this turn carried")
            if set(st.get("highlight") or []) - set(st.get("cards") or []):
                fail.append("a highlight that isn't a card of the turn")
            plan_names = set()
            if any(r.get("kind") == "flights" for r in tr["renders"]) or "trip" in name:
                from booking_signer import plan_store as PS
                p = await PS.latest(a)
                for d in ((p or {}).get("plan") or {}).get("days") or []:
                    h = d.get("hotel")
                    if isinstance(h, dict) and h.get("name"):
                        plan_names.add(h["name"])
            allowed = {x for x in on_screen | plan_names | set(st.get("names") or []) if x}   # the screen during THIS turn
            heard = " ".join(tr["spoken"]) or tr["text"]
            named = await extract_names(tr["text"] or heard)
            stray = [n for n in named if not AG.name_matches(n, allowed)]
            if stray:
                fail.append(f"named, not on screen: {stray[:3]} · on screen {sorted(allowed)[:5]}")
            rib = st.get("ribbon") or ""
            if rib.lower().startswith("no ") and named and not stray:
                fail.append(f"ribbon “{rib}” beside named places {named[:2]}")
            if st.get("cards") and _STALE_WORDS.search(tr["text"] or ""):
                fail.append(f"cards on screen but she says none: {tr['text'][:100]}")
            if tr["render_at"] is not None and tr["first_say"] is not None:
                timing.append({"conv": name, "q": tr["user"], "first_say": tr["first_say"], "render_at": tr["render_at"],
                               "find": next(((ev.get("find") or {}) for ev in tr["renders"] if ev.get("kind") == "venues"), {})})
    finally:
        try:
            await GW.STORE.delete_account(a)
        except Exception:
            pass
        try:
            await ops.ADMIN("DELETE", f"/admin/users/{a}", {})
        except Exception as e:
            print(f"   say-show {a[:8]} NOT deleted: {type(e).__name__}")
    return {"name": name, "fail": fail, "turns": turns}


def _block_sends():
    """EVERY send blocked in this process: no form, call, email, hand-over, page or WhatsApp leaves."""
    from booking_signer import guest_whatsapp as GW
    from agapi import venues as VN
    real = (GW.api, GW._tell, VN.book_venue)

    async def guarded(account, method, path, body=None, timeout=90.0):
        if method == "POST" and path.rstrip("/").split("/")[-1] in ("send", "place", "handover", "opened", "booked", "cancel"):
            return 451, {"rule": "suite_stop", "message": "the say-show suite never sends"}
        return await real[0](account, method, path, body, timeout)

    async def no_tell(ch, text, template=None):
        return "not sent: suite"

    async def no_book(ctx, a):
        from agapi.v0 import ToolError
        raise ToolError("suite_stop", "the suite never books")
    GW.api, GW._tell, VN.book_venue = guarded, no_tell, no_book
    return real


def _restore(real):
    from booking_signer import guest_whatsapp as GW
    from agapi import venues as VN
    GW.api, GW._tell, VN.book_venue = real


async def before_latency(timing: list) -> None:
    """For 4's BEFORE: the second search the card used to make when it mounted (/venues/find), measured cold for the same
    query (a fresh scratch account, so no cache)."""
    from booking_signer import guest_accounts as GA, guest_whatsapp as GW, ops
    g, _ = await GA.create_guest("say-show-before")
    try:
        for t in timing:
            f = t["find"]
            body = {k: f[k] for k in ("what", "where", "country", "open_at") if f.get(k)}
            body["what"] = (body.get("what") or "restaurant") + " "   # a different cache key: a cold search, as the card's was
            t0 = time.perf_counter()
            await GW.api(g["account_id"], "POST", "/api/booking/venues/find", body)
            t["second_search"] = time.perf_counter() - t0
    finally:
        await ops.ADMIN("DELETE", f"/admin/users/{g['account_id']}", {})


def _pct(xs: list, p: float):
    if not xs:
        return None
    xs = sorted(xs)
    return round(xs[min(len(xs) - 1, int(round(p * (len(xs) - 1))))], 2)


async def main() -> int:
    from scripts import places_fake   # Sasha 213 · NO live Google Places from a suite (it costs money) — the founder's say-so only
    places_fake.install()
    if os.getenv("SASHA_FLIGHT_SUITE", "") == "skip":
        print("say-show suite SKIPPED (SASHA_FLIGHT_SUITE=skip) — this deploy is not covered")
        return 0
    if os.getenv("SASHA_GATE_DUFFEL", "fixtures") != "live":
        from scripts import duffel_fake
        duffel_fake.install()
    from booking_signer import routes  # noqa: F401
    t0, start = time.time(), len(RESULTS)
    timing: list = []
    real = _block_sends()
    sem = asyncio.Semaphore(int(os.getenv("SAY_SHOW_PARALLEL", "6")))
    only = int(os.getenv("SAY_SHOW_N", "30"))

    async def run(c):
        async with sem:
            try:
                return await one(*c, timing)
            except Exception as e:
                return {"name": c[0], "fail": [f"the run failed: {type(e).__name__}: {e}"], "turns": []}
    try:
        results = await asyncio.gather(*[run(c) for c in C[:only]])
    finally:
        _restore(real)
    for r in results:
        ok(f"SAY=SHOW {r['name']}", not r["fail"], "; ".join(r["fail"])[:240])
    after = [max(0.0, t["render_at"] - t["first_say"]) for t in timing]
    print(f"   cards (after): her first word → cards visible, p50 {_pct(after, .5)} s · p95 {_pct(after, .95)} s · "
          f"cards before her words in {sum(1 for t in timing if t['render_at'] <= t['first_say'])}/{len(timing)} venue turns", flush=True)
    if os.getenv("SAY_SHOW_BEFORE", "") == "1":
        await before_latency(timing)
        before = [max(0.0, t["render_at"] + t.get("second_search", 0) - t["first_say"]) for t in timing]
        print(f"   cards (before, reconstructed): p50 {_pct(before, .5)} s · p95 {_pct(before, .95)} s "
              f"(the card's own second search: p50 {_pct([t.get('second_search', 0) for t in timing], .5)} s)", flush=True)
    out = os.getenv("SAY_SHOW_REPORT", "")
    if out:
        with open(out, "w", encoding="utf-8") as f:
            json.dump({"results": [{"name": r["name"], "fail": r["fail"], "turns": [{k: v for k, v in t.items() if k != "renders"}
                                                                                    for t in r["turns"]]} for r in results],
                       "timing": timing}, f, default=str, indent=1)
    mine = RESULTS[start:]
    failed = [n for n, p, _ in mine if not p]
    print(f"\nsay-show suite: {len(mine) - len(failed)}/{len(mine)} passed in {time.time() - t0:.0f}s" + (f" — FAILED: {failed}" if failed else ""))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
