"""Sasha 198 · THE LIVE DUFFEL SUITE, ON A SCHEDULE — it alerts, it never blocks a deploy.

The deploy gate (scripts/gate.py) replays recorded Duffel answers, so a Duffel timeout, a rate limit or a withdrawn TEST fare can
no longer stop a deploy. Whether Duffel ITSELF still answers as recorded is this suite's job: the same flight suite, against
Duffel TEST for real, every SASHA_LIVE_SUITE_HOURS (default 6; 0 = off), each run in its own process (the suite swaps module
functions for its scratch guest — never inside the serving process). A failure is logged and emailed to SASHA_FOUNDER_EMAIL with
the failing lines; a pass is logged only.
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys

log = logging.getLogger(__name__)
_task = None
LAST: dict = {}
BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


async def run_once() -> dict:
    p = await asyncio.create_subprocess_exec(sys.executable, "-m", "scripts.flight_suite", cwd=BACKEND,
                                             stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
    try:
        out, _ = await asyncio.wait_for(p.communicate(), timeout=900)
    except asyncio.TimeoutError:
        p.kill()
        out = b"FAIL \xc2\xb7 the live suite ran over 15 minutes and was stopped"
    text = out.decode("utf-8", "replace")
    fails = [ln for ln in text.splitlines() if ln.startswith("FAIL")]
    summary = next((ln for ln in text.splitlines() if ln.startswith("flight suite:")), "flight suite: no summary line")
    return {"ok": p.returncode == 0 and not fails, "summary": summary, "fails": fails}


async def _alert(r: dict) -> None:
    to = os.getenv("SASHA_FOUNDER_EMAIL", "").strip()
    if not to:
        log.error("[live_suite] FAILED and no SASHA_FOUNDER_EMAIL to alert: %s", r["summary"])
        return
    from booking_signer import emailing as E, ladder_routes as LR
    sent = await E.send(LR.HTTP, {"from": os.getenv("SASHA_EMAIL_FROM", "").strip(), "to": to,
                                  "subject": "Sasha · the live Duffel suite FAILED (deploys are not blocked)",
                                  "text": "\n".join([r["summary"], ""] + r["fails"][:20] +
                                                    ["", "The deploy gate replays recorded Duffel answers; this scheduled run checks Duffel itself."])})
    if not sent.sent:
        log.error("[live_suite] the alert email was not sent: %s", sent.why)


async def _forever() -> None:
    hours = float(os.getenv("SASHA_LIVE_SUITE_HOURS", "6") or 0)
    await asyncio.sleep(20 * 60)   # not at boot: the deploy just passed its gate
    while True:
        try:
            r = await run_once()
            LAST.clear(); LAST.update(r)
            if r["ok"]:
                log.info("[live_suite] %s", r["summary"])
            else:
                log.error("[live_suite] %s — %s", r["summary"], r["fails"][:5])
                await _alert(r)
        except Exception as e:
            log.error("[live_suite] did not run: %s: %s", type(e).__name__, e)
        await asyncio.sleep(hours * 3600)


def start() -> None:
    global _task
    hours = float(os.getenv("SASHA_LIVE_SUITE_HOURS", "6") or 0)
    if _task is None and hours > 0 and os.getenv("DATABASE_URL", "").strip() and os.getenv("SASHA_PAID_LOOP", "1") == "1":
        _task = asyncio.create_task(_forever())


if __name__ == "__main__":
    print(asyncio.run(run_once()))
