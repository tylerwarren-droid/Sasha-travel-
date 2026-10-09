"""CR 70 · CALENDAR, live: no outside provider — the .ics and the add-to-calendar links are AgAPI's own (Sasha's agapi/powers.py ics(), the
same code as the sandbox's). Google Calendar sync (OAuth per person) is a later, separate step."""
from __future__ import annotations

from ..adapters import SimCalendar


class LiveCalendar(SimCalendar):
    async def smoke(self) -> dict:
        """Nothing leaves the service: one event rendered as .ics and checked."""
        from agapi import powers as P
        ev = P.event("smoke@agapi.kanoe", "Smoke check", "2026-11-12T10:00:00Z", "2026-11-12T11:00:00Z", "Madrid", "AgAPI live smoke")
        text = P.ics(ev, "20261009T000000Z")
        return {"ok": text.startswith("BEGIN:VCALENDAR") and "END:VCALENDAR" in text, "lines": text.count("\r\n")}
