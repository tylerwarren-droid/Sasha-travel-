"""Sasha 194 · THE DEPLOY GATE (Railway preDeployCommand): the flight suite, then the core-flow suites (itinerary, restaurant,
spa, spaces). Any failure → exit 1 → Railway keeps the old deploy. SASHA_FLIGHT_SUITE=skip skips both (said in the log).
Sasha 198 · DETERMINISTIC: Duffel is replayed from recorded fixtures (scripts/duffel_fake.py) — a Duffel timeout, rate limit or
withdrawn fare can no longer block a deploy. SASHA_GATE_DUFFEL=live runs it against Duffel TEST instead; the live suite also runs
on a schedule (scripts/live_suite.py), alerting without blocking."""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scripts import flight_suite as F, core_suites as C, basket_suite as BS, agent_suite as AS, whatsapp_suite as WS, postgres_suite as PG  # noqa: E402


async def _clean_orphans(since) -> None:
    """Sasha 203 · the suites' scratch guests are deleted, and their payment events lose their item (on delete set null):
    THIS run's orphaned order events go too. Real Duffel webhooks (duffel_webhook) are never touched."""
    try:
        from booking_signer import plan_store as PS
        run = PS._run()
        n = await run(lambda c: c.execute("delete from basket_events where item_id is null and source = 'duffel_order' and received_at >= $1", since))
        print(f"gate: scratch order events cleaned ({n})")
    except Exception as e:
        print(f"gate: scratch order events NOT cleaned: {type(e).__name__}")


async def main() -> int:
    from datetime import datetime, timezone
    since = datetime.now(timezone.utc)
    if os.getenv("SASHA_GATE_DUFFEL", "fixtures") != "live":
        from scripts import duffel_fake
        duffel_fake.install()
    a = await F.main()
    b = await C.main()
    c = await BS.main()   # Sasha 198 · the trip basket (grows R2 → R10)
    d = await AS.main()   # Sasha 203 · the agent's tools (AgAPI v0) in the real database
    await _clean_orphans(since)
    e = await __import__("asyncio").to_thread(WS.main)   # Sasha 206 · WhatsApp: spaces, R1, R2, the guest pipeline (offline)
    f = await __import__("asyncio").to_thread(PG.main)   # Sasha 207 · the stores on a real, throwaway Postgres (never production)
    print(f"\nDEPLOY GATE: {'PASS' if not (a or b or c or d or e or f) else 'FAIL'}")
    return 1 if (a or b or c or d or e or f) else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
