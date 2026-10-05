"""CR 23 · rehearse the live hand-over through Browserbase (Frankfurt, unrecorded) with a FICTIONAL guest.

    python scripts/cr23_handover.py test [plain|wizard]          # our test venue: the link waits for a press, then ✅ Booked
    python scripts/cr23_handover.py readonly <venue form url>     # an approved venue's OWN form, filled up to the last press;
                                                                   # nothing can be sent (press cancelled in-page, non-GET blocked)
The key comes from Railway into this process only (never printed). Output: <out>/cr23-<mode>.json (+ .png for read-only);
the live view link (it controls the session; short-lived) goes to <out>/cr23-live-url.txt, never to the terminal.
"""
from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
from datetime import date, time as dtime
from pathlib import Path
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
OUT = Path(os.getenv("CR23_OUT", "/tmp/cr23"))
LINK = Path.home() / ".cache" / "kanoe-cr1" / "railway-link"


def railway_env() -> None:
    r = subprocess.run(["npx", "-y", "@railway/cli@latest", "variables", "--kv"], cwd=LINK, capture_output=True, text=True)
    for line in r.stdout.splitlines():
        k, _, v = line.partition("=")
        if k in ("BROWSERBASE_API_KEY", "BROWSERBASE_PROJECT_ID"):
            os.environ[k] = v
    if not os.getenv("BROWSERBASE_API_KEY"):
        sys.exit("BROWSERBASE_API_KEY not found on Railway")


def dump(rec: dict, name: str) -> dict:
    keep = {k: v for k, v in rec.items() if not k.startswith("_") and k not in ("token", "live_url", "session_id")}
    (OUT / name).write_text(json.dumps(keep, indent=1, default=str, ensure_ascii=False))
    return keep


async def main(mode: str, arg: str) -> None:
    from booking_signer import form_rung as FR, handover as HO, venue_read as V
    from booking_signer import ladder_routes as LR
    OUT.mkdir(parents=True, exist_ok=True)
    one = {"date", "time", "party_size"}
    if mode == "test":
        url = FR.test_venue_url(arg or "plain")
        m = FR.form_map(url)
        read_only = False
    else:
        url = arg
        host = (urlsplit(url).hostname or "").lower()
        if host not in FR.FORM_MAPS:
            sys.exit("only a mapped venue's own form (form_rung.FORM_MAPS)")
        m = {**FR.FORM_MAPS[host], "test": False}
        read_only = True
    if not await V._allowed(LR.HTTP, url, LR.RESOLVE):
        sys.exit("robots.txt does not allow it")
    day, at = date(2026, 12, 15), dtime(21, 0)
    vals = {**HO.FICTIONAL, "date": m["date_fmt"](day), "time": m["time_fmt"](at)}
    if m.get("phone_fmt"):
        vals["phone"] = m["phone_fmt"](vals["phone"])
    wizard = url.rstrip("/").endswith("/wizard")
    s1 = [{"name": n, "value": vals[r], "label": lbl} for n, (r, lbl) in m["fields"].items() if r in vals and (not wizard or r in one)]
    s2 = [{"name": n, "value": vals[r], "label": lbl} for n, (r, lbl) in m["fields"].items() if wizard and r in vals and r not in one]
    s1 += [{"name": n, "value": v, "label": lbl} for n, (v, lbl) in (m.get("fixed") or {}).items()]
    req = {"what": {"activity": "table", "activity_venue_lang": "mesa", "category": "restaurant"},
           "when": {"mode": "at", "at": f"{day.isoformat()}T{at.strftime('%H:%M')}"}, "how_many": {"count": 2, "unit": "people"},
           "who": {"name": HO.FICTIONAL["person_name"]}}
    try:
        rec = await HO.open_handover(page_url=url, m=m, step1=s1, step2=s2, venue="Sasha Test Venue" if m.get("test") else urlsplit(url).hostname,
                                     account=None, form_id=None, read_only=read_only, request=req, fictional=True)
    except HO.Refused as e:
        print(json.dumps({"refused": e.rule, "say": e.say}, ensure_ascii=False))
        return
    (OUT / "cr23-live-url.txt").write_text(rec["live_url"] or "")
    if read_only:
        (OUT / "cr23-readonly.png").write_bytes(rec.get("_screenshot") or b"")
    print(json.dumps({"ready": dump(rec, f"cr23-{mode}.json")}, ensure_ascii=False, default=str), flush=True)
    if read_only:                          # a real venue: filled up to the last press, NOBODY presses — the session ends here
        rec["_watch"].cancel()
        await HO._end(rec, "read_only_stopped", "filled up to the last press; not pressed; nothing was sent")
        print(json.dumps({"done": dump(rec, f"cr23-{mode}.json")}, ensure_ascii=False, default=str), flush=True)
        return
    rec["_opened"] = HO.CLOCK()            # the link is opened now (the rehearsal opens the live view itself)
    await rec["_watch"]
    print(json.dumps({"done": dump(rec, f"cr23-{mode}.json")}, ensure_ascii=False, default=str), flush=True)


if __name__ == "__main__":
    railway_env()
    asyncio.run(main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else ""))
