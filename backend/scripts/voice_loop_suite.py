"""Sasha 210 · ONE FULL LOOP, SMOOTH — ten scripted voice conversations with the /next agent (the voice path itself:
turn_with_quiver, its acknowledgements and its spoken phrases), plan → flights → "book it" → the payment link on the phone.
Scratch guests, each with a fictional linked WhatsApp number (Ofcom's drama range) whose messages are CAPTURED, never sent;
Duffel replayed in the gate; Stripe TEST; all cleaned up after. Part of the deploy gate (scripts/gate.py).

Checked in every conversation:
  · no repeated opener — no "Lovely"/"Great"/"Ooh" twice in what she says (acknowledgements included)
  · no process talk — never her tools, errors, mix-ups, "I don't want to pass on bad info"
  · no test disclaimers — never "not real", "test", "demo", "nothing is charged" in her words (the cards carry the tag)
  · flights in the first proposal — a card per leg with 3–5 options, one already chosen, and a € total in her words
  · the payment link reaching the phone — one Stripe checkout link to the guest's number, only after their yes
  · and (what reading the first run's transcripts found): no sentence said twice in a turn, no list read out, and a tapped
    flight swapped straight in (choose_offer, no new search)
The models are real (not deterministic). Sasha 212: each conversation runs ONCE — the conversation-7 "flake" was the
database pooler running out of session slots (fixed in store.py), not chance; VOICE_LOOP_ATTEMPTS can allow more, off by default.
"""
from __future__ import annotations

import asyncio
import os
import re
import sys
import time
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scripts.flight_suite import RESULTS, ok  # noqa: E402

_DAY = date.today() + timedelta(days=45)
WHEN = f"{_DAY.day} {_DAY.strftime('%B')}"
ALL_IN_ONE = f"Hi, I'm Tyler. Two of us, Vietnam for 8 nights from {WHEN}, beaches and food, flying from Madrid."
TWO = "Tyler Warren, Mr, born 1 February 1980; and Sam Warren, Ms, born 3 March 1982."
THREE = TWO[:-1] + "; and Alex Warren, Mr, born 5 May 1990."
TAP_OUT, TAP_BACK = "<tap:out>", "<tap:back>"   # a tap on an option the proposal did NOT choose (the card's own words)

# (name, scripted lines in order, the travellers' answer if she asks, whether it ends with a yes → a payment link)
SCENARIOS = [
    ("1 · book it without picking", [ALL_IN_ONE, "Book it.", "Yes."], TWO, True),
    ("2 · picks another flight by voice, then book it", [ALL_IN_ONE, "Can we have the cheapest flight out instead?", "Book it.", "Yes, go ahead."], TWO, True),
    ("3 · taps another flight, then book it", [ALL_IN_ONE, TAP_OUT, "Book it.", "Yes."], TWO, True),
    ("4 · what's the total, then book it", [ALL_IN_ONE, "What's the total?", "Book it.", "Yes."], TWO, True),
    ("5 · one thing at a time", ["Hi, I'd love to go to Vietnam.", "Two of us.", f"From {WHEN}, for 8 nights.", "Beaches and food.",
                                 "From Madrid.", "Book it.", "Yes."], TWO, True),
    ("6 · travellers given up front", [ALL_IN_ONE + " The travellers are " + TWO, "Book it.", "Yes."], TWO, True),
    ("7 · not yet, then yes", [ALL_IN_ONE, "Book it.", "Hmm, not yet.", "OK, go ahead."], TWO, True),
    ("8 · is it booked?", [ALL_IN_ONE, "Book it.", "Yes.", "Is it booked?"], TWO, True),
    ("9 · make it three of us", [ALL_IN_ONE, "Actually, make it three of us.", "Book it.", "Yes."], THREE, True),
    ("10 · taps the flight home, total, book it", [ALL_IN_ONE, TAP_BACK, "What's the total now?", "Book it.", "Yes."], TWO, True),
]
# Sasha 211 · ANY COUNTRY: the full loop for each (the plan in that country, real hotels with ESTIMATED prices, flights)
def _country_line(where: str, days: int, love: str) -> str:
    return f"Hi, I'm Tyler. Two of us, {days} days around {where} from {WHEN}, {love}, flying from Madrid."


COUNTRIES = [("Ecuador", 12, "nature and food", "EC"), ("Japan", 10, "temples and food", "JP"),
             ("Morocco", 8, "markets and the desert", "MA"), ("Portugal", 7, "wine and the coast", "PT"),
             ("Vietnam", 8, "beaches and food", "VN")]
SCENARIOS += [(f"{11 + i} · {c}, the full loop", [_country_line(c, d, love), "Book it.", "Yes."], TWO, True, code)
              for i, (c, d, love, code) in enumerate(COUNTRIES)]
_ASKS_TRAVELLERS = re.compile(r"(?i)full names?|dates? of birth|birthdays?|titles?\b|passport names?|names? (?:and|&) (?:dates|birth)")
_YESLINE = re.compile(r"(?i)^(?:yes|ok, go ahead)")
_EUR = re.compile(r"€\s?\d")


async def one(name: str, steps: list, travellers: str, ends_paid: bool, country: Optional[str] = None, *, n: int, captured: dict) -> dict:
    from booking_signer import guest_accounts as GA, guest_whatsapp as GW
    from app.agent import sasha as AG
    g, why = await GA.create_guest("voice-loop")
    if not g:
        return {"name": name, "fail": [f"no scratch guest: {why}"], "turns": []}
    a = g["account_id"]
    number = f"+44770090{n:04d}"[:13]
    c = GW.consent()
    now = datetime.now(timezone.utc)
    await GW.STORE.link({"account_id": a, "wa_id_sha256": GW.wa_key(number), "number_e164": number, "linked_at": now, "consent_at": now,
                         "consent_wording_version": c["version"], "consent_text_sha256": c["sha256"]})
    captured[GW.wa_key(number)] = []
    session = f"voice-loop-{uuid.uuid4().hex[:8]}"
    history, turns, cards, gave = [], [], [], 0
    todo = list(steps)
    try:
        for _ in range(len(steps) + 3):
            last = history[-1]["content"] if history else ""
            if gave < 2 and history and _ASKS_TRAVELLERS.search(last) and travellers not in (todo[0] if todo else ""):
                said, gave = travellers, gave + 1
            elif todo:
                said = todo.pop(0)
            else:
                break
            if said in (TAP_OUT, TAP_BACK):   # the card's Choose button: the words of an option the proposal didn't choose
                leg = "out" if said == TAP_OUT else "back"
                card = next((x for x in cards if x.get("leg") == leg), None)
                pick = next((o for o in (card or {}).get("options") or [] if not o.get("chosen")), None)
                said = pick["pick"] if pick else "the other flight out, please"
            sent_before = len(captured[GW.wa_key(number)])
            t = {"user": said, "spoken": [], "tools": [], "renders": [], "text": "", "guard": [], "first_sound": None}
            t0 = time.perf_counter()
            async for ev in AG.turn_with_quiver(a, said, history, session):
                if ev["type"] in ("say", "filler"):
                    t["spoken"].append((ev["type"], ev["text"]))
                    t["first_sound"] = t["first_sound"] or int((time.perf_counter() - t0) * 1000)
                elif ev["type"] == "replace" and ev.get("speak"):
                    t["spoken"].append(("replace", ev.get("say") or ev["text"]))
                elif ev["type"] == "tool":
                    t["tools"].append(ev["name"] + ("" if ev["ok"] else f"!{ev.get('error')}"))
                elif ev["type"] == "render":
                    t["renders"].append(ev)
                    if ev.get("kind") == "flights" and ev.get("cards"):
                        cards = ev["cards"]
                elif ev["type"] == "done":
                    t["text"], t["guard"] = ev["text"], ev["guard"]
                elif ev["type"] == "error":
                    t["text"] = ev["message"]
            t["links"] = [m for m in captured[GW.wa_key(number)][sent_before:] if "checkout.stripe.com" in m]
            history += [{"role": "user", "content": said}, {"role": "assistant", "content": t["text"]}]
            turns.append(t)
        plan = None
        if country:   # Sasha 211 · the plan is in THAT country, and its stays are real hotels with estimates (or Vietnam's list)
            from booking_signer import plan_store as PS
            plan = ((await PS.latest(a)) or {}).get("plan") or {}
    finally:
        await cleanup(a)
    r = judge(name, turns, ends_paid)
    if country:
        days = plan.get("days") or []
        hotels = [d.get("hotel") for d in days[:-1] if isinstance(d.get("hotel"), dict)]
        world = country != "VN"
        if not days or (world and (plan.get("country_code") != country or not hotels or not all(h.get("est") and h.get("source") == "google" for h in hotels))):
            r["fail"].append(f"the plan isn't {country} with real hotels and estimates: {plan.get('country_code')} · "
                             f"{[(h or {}).get('name') for h in hotels][:3]}")
        if not world and any(h.get("source") == "google" for h in hotels):
            r["fail"].append("Vietnam didn't use its own planner")
    return r


def judge(name: str, turns: list, ends_paid: bool) -> dict:
    from app.agent import sasha as AG
    spoken = [x for t in turns for _, x in t["spoken"]]
    openers = [AG.opener_of(x) for x in spoken]
    openers = [o for o in openers if o]
    words = spoken + [t["text"] for t in turns]
    internal = sorted({s for w in words for s in AG.internal_sentences(w)})
    fail = []
    if len(openers) != len(set(openers)):
        fail.append(f"repeated opener: {openers}")
    if internal:
        fail.append(f"process talk or a test disclaimer: {internal[:3]}")
    first = next((t for t in turns if any(x.startswith("propose_trip") for x in t["tools"])), None)
    fr = next((r for r in (first or {}).get("renders") or [] if r.get("kind") == "flights" and r.get("cards")), None)
    if not first or not fr or not all(3 <= len(c["options"]) <= 5 and sum(1 for o in c["options"] if o.get("chosen")) == 1 for c in fr["cards"]) \
            or not _EUR.search(first["text"]):
        fail.append(f"the first proposal lacked its flights (cards, one chosen) or a € total: tools {first and first['tools']} · "
                    f"{(first or {}).get('text', '')[:120]}")
    links = [(i, l) for i, t in enumerate(turns) for l in t["links"]]
    yes_at = next((i for i, t in enumerate(turns) if _YESLINE.match(t["user"]) or t["user"].startswith("OK, go ahead")), None)
    if ends_paid and len(links) != 1:
        fail.append(f"payment links on the phone: {len(links)} (want exactly one)")
    if links and (yes_at is None or links[0][0] < yes_at):
        fail.append("a payment link reached the phone before their yes")
    for t in turns:
        sents = [AG._norm(x) for _, u in t["spoken"] for x in re.split(r"(?<=[.!?])\s+", u) if x.strip()]
        if len(sents) != len(set(sents)):
            fail.append(f"a sentence said twice: {t['user'][:40]}")
            break
    if any(re.search(r"(?m)^\s*[-*•]\s|\*\*", u) for _, u in [x for t in turns for x in t["spoken"]]):
        fail.append("a list or markdown read out")
    for t in turns:
        if t["user"].startswith("the ") and " flight " in t["user"] and not (any(x.startswith("choose_offer") and "!" not in x for x in t["tools"])
                                                                          and not any(x.startswith("search_flights") for x in t["tools"])):
            fail.append(f"a tapped flight wasn't swapped straight in: {t['tools']}")
    # Sasha 212 · C: what she SAYS has no raw figures (the chat keeps them); D: a proposal is offered, never "your trip" done;
    # B: one total — a turn that states the total states ONE figure (never the flights and the hotels as separate totals)
    said_digits = [u for t in turns for k, u in t["spoken"] if re.search(r"\d", u)]
    if said_digits:
        fail.append(f"figures spoken aloud: {said_digits[:1]}")
    done_deal = [x for t in turns for x in [t["text"]] + [u for _, u in t["spoken"]]
                 if re.search(r"(?i)I'?ve put together your|here'?s what I'?ve put together|I'?ve put your (?:\w+ )?trip together", x or "")]
    if done_deal:
        fail.append(f"a proposal said as done: {done_deal[0][:120]}")
    for t in turns:
        if any(x.split("!")[0] in ("propose_trip", "get_total", "hold_booking") and "!" not in x for x in t["tools"]):
            amounts = {round(float(m.replace(",", ""))) for m in re.findall(r"€\s?(\d[\d,]*(?:\.\d+)?)", t["text"] or "")}
            if len(amounts) > 1:
                fail.append(f"more than one total in a turn: {sorted(amounts)} · {t['text'][:120]}")
                break
    claims = [t["text"] for t in turns if AG._claims(t["text"] or "")]
    if claims:
        fail.append(f"claimed booked with nothing paid: {claims[:1]}")
    return {"name": name, "fail": fail, "turns": turns}


async def cleanup(a: str) -> None:
    from booking_signer import guest_whatsapp as GW, ops, plan_store as PS
    try:
        await GW.STORE.delete_account(a)
    except Exception as e:
        print(f"   voice-loop {a[:8]} WhatsApp rows NOT cleaned: {type(e).__name__}")
    try:
        run = PS._run()

        async def fn(conn):
            await conn.execute("delete from basket_events where item_id in (select id from trip_basket_items where account_id = $1)", uuid.UUID(a))
        await run(fn)
    except Exception as e:
        print(f"   voice-loop {a[:8]} events NOT cleaned: {type(e).__name__}")
    try:
        s, _ = await ops.ADMIN("DELETE", f"/admin/users/{a}", {})
        if s >= 300:
            print(f"   voice-loop {a[:8]} NOT deleted (HTTP {s})")
    except Exception as e:
        print(f"   voice-loop {a[:8]} NOT deleted: {type(e).__name__}")


def write_report(results: list, path: str) -> None:
    lines = [f"# Sasha 210 · the full loop — ten scripted voice conversations ({datetime.now(timezone.utc):%d %b %Y %H:%M} UTC)", "",
             "| # | conversation | turns | result | retried | first sound, median ms |", "|---|---|---|---|---|---|"]
    med = lambda xs: sorted(xs)[len(xs) // 2] if xs else "—"
    for r in results:
        fs = [t["first_sound"] for t in r["turns"] if t["first_sound"]]
        lines.append(f"| {r['name'].split(' · ')[0]} | {r['name'].split(' · ', 1)[1]} | {len(r['turns'])} | "
                     f"{'✅' if not r['fail'] else '❌ ' + '; '.join(r['fail'])[:200]} | {'yes' if r.get('retried') else ''} | {med(fs)} |")
    for r in [x for res in results for x in ([res] + ([{**res["first"], "name": res["name"] + " — FIRST RUN (failed: "
                                                                    + "; ".join(res["first"]["fail"])[:160] + ")"}] if res.get("first") else []))]:
        lines += ["", f"## {r['name']}", ""]
        for t in r["turns"]:
            lines.append(f"- **Traveller:** {t['user']}")
            for kind, x in t["spoken"]:
                lines.append(f"  - *{kind}:* {x}")
            if t["tools"]:
                lines.append(f"  - tools: {', '.join(t['tools'])}")
            if t["links"]:
                lines.append("  - 📱 the payment link reached the phone")
            if t["guard"]:
                lines.append(f"  - guard: {'; '.join(t['guard'])[:300]}")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


async def main() -> int:
    from scripts import places_fake   # Sasha 213 · NO live Google Places from a suite (it costs money) — the founder's say-so only
    places_fake.install()
    if os.getenv("SASHA_FLIGHT_SUITE", "") == "skip":
        print("voice loop suite SKIPPED (SASHA_FLIGHT_SUITE=skip) — this deploy is not covered")
        return 0
    if os.getenv("SASHA_GATE_DUFFEL", "fixtures") != "live":
        from scripts import duffel_fake
        duffel_fake.install()
    from booking_signer import routes  # noqa: F401
    from booking_signer import guest_whatsapp as GW
    t0, start = time.time(), len(RESULTS)
    captured: dict = {}
    real_tell = GW._tell

    async def capture(ch, text, template=None):   # the phone: captured, never sent
        if ch.get("wa_id_sha256") not in captured:
            return "not sent: not a voice-loop number"
        captured[ch["wa_id_sha256"]].append(text)
        return "sent (captured)"
    GW._tell = capture
    sem = asyncio.Semaphore(int(os.getenv("VOICE_LOOP_PARALLEL", "5")))

    async def run(i, s):
        async with sem:
            r = None
            attempts = max(1, int(os.getenv("VOICE_LOOP_ATTEMPTS", "1")))   # Sasha 212 · ONE run: a flake is found, not retried
            for attempt in range(1, attempts + 1):
                try:
                    r = await one(*s, n=100 + i * 2 + attempt, captured=captured)
                except Exception as e:
                    r = {"name": s[0], "fail": [f"the run failed: {type(e).__name__}: {e}"], "turns": []}
                if not r["fail"]:
                    break
                if attempt < attempts:
                    first = r
                    print(f"   voice loop {s[0]}: failed once ({'; '.join(r['fail'])[:160]}) — running it again", flush=True)
            r["retried"] = attempt > 1
            if r["retried"]:
                r["first"] = first
            return r
    try:
        results = await asyncio.gather(*[run(i, s) for i, s in enumerate(SCENARIOS)])
    finally:
        GW._tell = real_tell
    for r in results:
        ok(f"VOICE LOOP {r['name']}" + (" (passed on its second run)" if r.get("retried") and not r["fail"] else ""), not r["fail"],
           "; ".join(r["fail"])[:240])
    out = os.getenv("VOICE_LOOP_REPORT", "")
    if out:
        write_report(results, out)
        print("wrote", out)
    mine = RESULTS[start:]
    failed = [n for n, p, _ in mine if not p]
    print(f"\nvoice loop suite: {len(mine) - len(failed)}/{len(mine)} passed in {time.time() - t0:.0f}s" + (f" — FAILED: {failed}" if failed else ""))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
