"""CR 70 · PLACES (Google), live: Sasha's own booking_signer.venue_read.find_venues with the real HTTP, through the same mapping the sandbox
uses (providers.find_venues), so a live answer has exactly the sandbox's shape. AgAPI's OWN daily cap (AGAPI_PLACES_DAILY_CAP, counted per
Google day = midnight Pacific) keeps AgAPI from using up the daily Text Search quota Sasha shares; Google's own 429 → upstream_rate_limited.
Stays (priced hotels) are not connected: Sasha has no real priced-stay provider."""
from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from .. import config, providers as PV
from ..adapters import Places, not_connected
from ..registry import AgapiError
from ..store import ts

PACIFIC = ZoneInfo("America/Los_Angeles")


def google_day_start() -> str:
    """Google's daily quotas reset at midnight Pacific."""
    now = datetime.now(PACIFIC)
    return ts(now.replace(hour=0, minute=0, second=0, microsecond=0))


def _store():
    from . import STORE
    return STORE() if STORE else None


def _table(store) -> None:
    store.x("create table if not exists provider_calls (provider text not null, kind text not null, at text not null)")


def calls_today(store) -> int:
    _table(store)
    return store.one("select count(*) as n from provider_calls where provider = 'google_places' and at >= ?", google_day_start())["n"]


def _count(store, kind: str) -> None:
    _table(store)
    store.x("insert into provider_calls (provider, kind, at) values ('google_places', ?, ?)", kind, ts())


class LivePlaces(Places):
    async def find_venues(self, inp, up):
        from . import http
        st = _store()
        if st is not None:
            if calls_today(st) >= config.PLACES_DAILY_CAP:
                raise AgapiError("upstream_rate_limited", f"AgAPI live's own daily cap for Google Places ({config.PLACES_DAILY_CAP} searches) is reached; "
                                 "it keeps Sasha's shared quota safe. It resets at midnight Pacific.", {"provider": "places", "cap": config.PLACES_DAILY_CAP},
                                 retry_after_s=3600)
            _count(st, "search")
        return await PV.find_venues(inp, up, http=http)

    async def find_stays(self, inp, up):
        raise not_connected("stays")

    async def smoke(self) -> dict:
        """Spends nothing, contacts nobody: Text Search with the IDs-only field mask (Google's free 'Essentials IDs Only' SKU), one result.
        Counts as one request against the daily quota, so it is counted here too. Returns no place names."""
        from booking_signer import venue_read as V
        from . import http
        key = V.places_key()
        if not key:
            return {"ok": False, "why": "GOOGLE_PLACES_API_KEY isn't set on agapi-live"}
        st = _store()
        if st is not None:
            _count(st, "smoke")
        r = await http("POST", V.PLACES_URL, headers={"X-Goog-Api-Key": key, "X-Goog-FieldMask": "places.id", "content-type": "application/json"},
                       json={"textQuery": "cafe in Madrid", "maxResultCount": 1})
        try:
            n = len((r.json() or {}).get("places") or [])
        except ValueError:
            n = 0
        return {"ok": r.status_code == 200 and n >= 1, "status": r.status_code, "results": n, "sku": "Text Search Essentials (IDs only): no charge",
                "calls_today": calls_today(st) if st is not None else None, "cap": config.PLACES_DAILY_CAP}
