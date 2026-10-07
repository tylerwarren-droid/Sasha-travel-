"""Sasha 194 · THE DEPLOY GATE (Railway preDeployCommand): the flight suite, then the core-flow suites (itinerary, restaurant,
spa, spaces). Any failure → exit 1 → Railway keeps the old deploy. SASHA_FLIGHT_SUITE=skip skips both (said in the log)."""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scripts import flight_suite as F, core_suites as C  # noqa: E402


async def main() -> int:
    a = await F.main()
    b = await C.main()
    print(f"\nDEPLOY GATE: {'PASS' if a == 0 and b == 0 else 'FAIL'}")
    return 1 if (a or b) else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
