"""CR 33 · rehearse CampusMe's live hand-over READ-ONLY on a school's real visit-registration form: a FICTIONAL student, every
outgoing write aborted in the cloud browser, SUBMIT never pressed; the session is ended right after the capture.

    python scripts/cr33_campus.py <school> <YYYY-MM-DD> [session-title-word]
Output under $CR33_OUT (default /tmp/cr33): JSON + the filled page's PNG. The key comes from Railway, never printed.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from cr23_handover import railway_env  # noqa: E402

OUT = Path(os.getenv("CR33_OUT", "/tmp/cr33"))


async def main(argv):
    from booking_signer import handover as HO
    from products.campus import live as LV, schools as SC, slate as SL
    OUT.mkdir(parents=True, exist_ok=True)
    school, day = argv[0], argv[1]
    word = (argv[2] if len(argv) > 2 else "tour").lower()
    ss = [x for x in await SL.sessions(SC.SCHOOLS[school], day, 2) if x.status == "open"]
    pick = next((x for x in ss if word in x.title.lower()), None)
    if not pick:
        sys.exit(f"no open session with '{word}' on {day}: {[x.title for x in ss]}")
    print(json.dumps({"session": pick.title, "start": pick.start, "form": pick.form_url}))
    try:
        rec = await LV.open_campus_handover(session=pick, profile=dict(LV.FICTIONAL), attendees=2, account=None, read_only=True,
                                            fictional=True)
    except HO.Refused as e:
        print(json.dumps({"refused": e.rule, "say": e.say}, ensure_ascii=False))
        return
    (OUT / "handover.png").write_bytes(rec.get("_screenshot") or b"")
    keep = {k: v for k, v in rec.items() if not k.startswith("_") and k not in ("token", "live_url", "session_id")}
    (OUT / "handover.json").write_text(json.dumps(keep, indent=1, default=str, ensure_ascii=False))
    print(json.dumps({k: keep.get(k) for k in ("state", "venue", "taps_left", "book_label", "box_label", "ready_ms", "timings_ms",
                                               "filled", "summary")}, default=str, ensure_ascii=False))
    rec["_watch"].cancel()
    await HO._end(rec, "read_only_stopped", "filled up to the last two taps; SUBMIT never pressed; nothing was sent")
    print(json.dumps({"ended": rec["state"]}))


if __name__ == "__main__":
    railway_env()
    asyncio.run(main(sys.argv[1:]))
