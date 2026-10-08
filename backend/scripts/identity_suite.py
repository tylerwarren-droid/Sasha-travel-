"""Sasha 213 · ONE IDENTITY — Sasha is a travel concierge for anywhere, never "Vietnam trips". Twenty conversations that never
mention Vietnam (openers with no destination, other countries, venues, small talk): nothing she says or shows names Vietnam
or a Vietnamese place unless the traveller did. Scratch guests; Duffel and Google Places replayed; every send blocked.
Part of the deploy gate."""
from __future__ import annotations

import asyncio
import os
import re
import sys
import time
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scripts.flight_suite import RESULTS, ok  # noqa: E402

VIETNAM = re.compile(r"(?i)\b(vietnam\w*|hanoi|ha ?long|hoi ?an|da ?nang|saigon|ho chi minh|mekong|hu[eế]\b|sapa|phu ?quoc|nha trang|"
                     r"da ?lat|ninh binh|mui ne|con dao)\b")
# Sasha 215 (c) · Vietnam may be ONE of two or three suggestions, never the only one: a line naming it passes only when it
# also names another destination
OTHERS = re.compile(r"(?i)\b(thailand|bangkok|chiang mai|cambodia|siem reap|laos|malaysia|penang|kuala lumpur|singapore|indonesia|bali|java|"
                    r"philippines|japan|tokyo|kyoto|osaka|korea|seoul|taiwan|taipei|china|hong kong|india|sri lanka|nepal|maldives|"
                    r"portugal|lisbon|porto|spain|italy|greece|france|croatia|turkey|istanbul|morocco|marrakech|egypt|kenya|tanzania|"
                    r"zanzibar|south africa|mexico|oaxaca|peru|cusco|colombia|ecuador|costa rica|brazil|argentina|chile|caribbean|"
                    r"canaries|canary islands|madeira|azores|mauritius|seychelles|fiji|australia|new zealand|iceland|norway|scotland)\b")
C = [
    ("hello", ["Hi Sasha!", "What can you do?"]),
    ("no idea", ["I want a holiday but I've no idea where.", "Somewhere warm in November, two of us."]),
    ("beach", ["Where's good for a beach week in February?", "We love snorkelling."]),
    ("honeymoon", ["We're planning our honeymoon!", "We like food and quiet."]),
    ("weekend", ["A long weekend in Europe from Madrid?", "Something with good wine."]),
    ("family", ["A family trip with two kids, ten days in summer.", "Not too much travelling."]),
    ("Japan", ["Ten days in Japan from 22 November for 2, temples and food, flying from Madrid."]),
    ("Portugal", ["A week in Portugal from 22 November, two of us, wine and the coast, flying from Madrid."]),
    ("Morocco", ["Eight days in Morocco from 22 November for 2, markets and the desert, from Madrid."]),
    ("Ecuador", ["Twelve days around Ecuador from 22 November for 2, nature and food, from Madrid."]),
    ("Italy", ["A week in Italy in October for 2, art and pasta, flying from Madrid."]),
    ("Mexico", ["Mexico for 9 nights from 1 December, two of us, food and ruins, from Madrid."]),
    ("restaurant", ["A seafood restaurant in Madrid tonight for 2.", "Which would you pick?"]),
    ("spa", ["A spa in Madrid on Saturday at 11 for 2."]),
    ("tattoo", ["A tattoo studio in Madrid for a consultation next Tuesday at 5pm."]),
    ("rain", ["When's the rainy season in Peru?"]),
    ("budget", ["What could I do for 1,500 euros for a week?"]),
    ("asia generic", ["Somewhere in Asia for street food, three weeks, solo."]),
    ("islands", ["Which islands would you pick for a quiet week?"]),
    ("surprise", ["Surprise me with a trip idea for March."]),
]


async def one(name: str, lines: list) -> dict:
    from booking_signer import guest_accounts as GA, guest_whatsapp as GW, ops
    from app.agent import sasha as AG
    g, why = await GA.create_guest("identity")
    if not g:
        return {"name": name, "fail": [f"no scratch guest: {why}"]}
    a, fail, history = g["account_id"], [], []
    session = f"identity-{uuid.uuid4().hex[:8]}"
    try:
        for said in lines:
            text, shown = "", []
            async for ev in AG.turn_with_quiver(a, said, history, session):
                if ev["type"] in ("say", "filler"):
                    shown.append(ev["text"])
                elif ev["type"] == "render":
                    shown.append(str({k: v for k, v in ev.items() if k in ("cards", "card", "preset", "ribbon", "total")}))
                elif ev["type"] == "done":
                    text = ev["text"]
            history += [{"role": "user", "content": said}, {"role": "assistant", "content": text}]
            if not VIETNAM.search(said):
                # Vietnam alone — in what she says, or on screen — is a default; beside other places it's one suggestion
                hit = [m.group(0) for x in [text] + shown for m in [VIETNAM.search(x or "")] if m and not OTHERS.search(x or "")]
                if hit:
                    fail.append(f"“{said[:40]}” → Vietnam named alone: {hit[:2]} · {text[:100]}")
    finally:
        try:
            await GW.STORE.delete_account(a)
        except Exception:
            pass
        await ops.ADMIN("DELETE", f"/admin/users/{a}", {})
    return {"name": name, "fail": fail}


async def main() -> int:
    from scripts import places_fake   # NO live Google Places from a suite
    places_fake.install()
    if os.getenv("SASHA_GATE_DUFFEL", "fixtures") != "live":
        from scripts import duffel_fake
        duffel_fake.install()
    from booking_signer import routes  # noqa: F401
    from scripts.say_show_suite import _block_sends, _restore
    t0, start = time.time(), len(RESULTS)
    real = _block_sends()
    sem = asyncio.Semaphore(int(os.getenv("IDENTITY_PARALLEL", "6")))

    async def run(c):
        async with sem:
            try:
                return await one(*c)
            except Exception as e:
                return {"name": c[0], "fail": [f"the run failed: {type(e).__name__}: {e}"]}
    try:
        results = await asyncio.gather(*[run(c) for c in C])
    finally:
        _restore(real)
    for r in results:
        ok(f"IDENTITY {r['name']}", not r["fail"], "; ".join(r["fail"])[:240])
    mine = RESULTS[start:]
    failed = [n for n, p, _ in mine if not p]
    print(f"\nidentity suite: {len(mine) - len(failed)}/{len(mine)} passed in {time.time() - t0:.0f}s" + (f" — FAILED: {failed}" if failed else ""))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
