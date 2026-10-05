"""CR 27 · rehearse the Guestcentric hand-over READ-ONLY on a real hotel's own engine: a fictional guest, every outgoing
write aborted in the cloud browser, Book Now never pressed; the session is ended right after the capture.

    python scripts/cr27_guestcentric.py rates   <engine_url> <checkin> <checkout>
    python scripts/cr27_guestcentric.py handover <engine_url> <checkin> <checkout> "<rate>" "<room>" "<hotel>"
Output under $CR27_OUT (default /tmp/cr27): JSON + the filled page's PNG. The key comes from Railway, never printed.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from cr23_handover import railway_env  # noqa: E402

OUT = Path(os.getenv("CR27_OUT", "/tmp/cr27"))


async def main(argv):
    from booking_signer import handover as HO, handover_guestcentric as GC
    OUT.mkdir(parents=True, exist_ok=True)
    mode, engine, ci, co = argv[:4]
    stay = {"checkin": date.fromisoformat(ci), "checkout": date.fromisoformat(co), "adults": 2, "children": 0, "rooms": 1}
    if not await HO._robots_ok(engine):
        sys.exit("robots.txt does not allow it")
    if mode == "rates":
        rates = await GC.list_rates(engine, stay)
        (OUT / "rates.json").write_text(json.dumps(rates, indent=1, ensure_ascii=False))
        for r in rates:
            print(json.dumps({k: r[k] for k in ("rate", "room", "price", "cancel", "eligible", "why")}, ensure_ascii=False))
        return
    rate, room, hotel = argv[4], (argv[5] or None), argv[6]
    try:
        rec = await GC.open_gc_handover(engine_url=engine, stay=stay, rate=rate, room=room, guest=dict(GC.FICTIONAL), hotel=hotel,
                                        account=None, read_only=True, fictional=True)
    except HO.Refused as e:
        print(json.dumps({"refused": e.rule, "say": e.say}, ensure_ascii=False))
        return
    (OUT / "handover.png").write_bytes(rec.get("_screenshot") or b"")
    keep = {k: v for k, v in rec.items() if not k.startswith("_") and k not in ("token", "live_url", "session_id")}
    (OUT / "handover.json").write_text(json.dumps(keep, indent=1, default=str, ensure_ascii=False))
    print(json.dumps({k: keep.get(k) for k in ("state", "rate", "room", "taps_left", "book_label", "terms_label", "ready_ms",
                                               "timings_ms", "filled", "rate_terms")}, default=str, ensure_ascii=False))
    rec["_watch"].cancel()
    await HO._end(rec, "read_only_stopped", "filled up to the last two taps; Book Now never pressed; nothing was sent")
    print(json.dumps({"ended": rec["state"]}))


if __name__ == "__main__":
    railway_env()
    asyncio.run(main(sys.argv[1:]))
