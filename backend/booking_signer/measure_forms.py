"""S-40 · THE FORM MEASUREMENT — about 1,000 venue own-domain sites in Madrid, Lisbon and Berlin, restaurants AND
activities (tours, museums, experiences, classes), read once, as a ONE-OFF RAILWAY SERVICE.

    python -m booking_signer.measure_forms --plan                  # prints the plan and the SQL; no network
    MEASURE_FORMS_RUN=1 python -m booking_signer.measure_forms --run

⛔ WHERE IT RUNS. Only on Railway, as its own one-off service (start command above, restart policy "never").
It refuses to run unless MEASURE_FORMS_RUN=1 AND RAILWAY_ENVIRONMENT is set (Railway sets it on every deploy) — so
it cannot start on the founder's Mac, where every request would leave from his home IP, the network TheFork's
DataDome already blocks. `railway run` would execute LOCALLY, so it is refused too.

⛔ WHAT IT NEVER FETCHES. A booking platform's domain (restaurant AND activity platforms — see PLATFORM_HOSTS), a
social or aggregator host, any host other than the venue's own, anything robots.txt disallows, anything that
resolves to a non-public address. Pages are served markup only: no rendering, so no platform script or frame loads.

WHAT IT KEEPS. Not whole pages: per page, the <form> blocks, every <label>, the iframe/script hosts and the
calendar-first markers — enough for the frozen scorer (Applied Diligence `scripts/measure-forms-score.ts`, frozen at
SCORER_COMMIT) to run `extractFormMaps` + `bookingRoles` + `slotFirst` offline — gzip'd, with the page's URL, status,
byte count and sha256. Stored in Sasha's database (sql/006_measure_forms.sql). Never in a repo.

The venue list is Overture Places (CDLA Permissive 2.0 / Apache 2.0), release OVERTURE_RELEASE, each city's box read
from Overture's own divisions data in the same release — a box with provenance, never a recalled one.
"""
from __future__ import annotations

import argparse
import asyncio
import gzip
import hashlib
import json
import os
import random
import re
import sys
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urljoin, urlsplit
from urllib.robotparser import RobotFileParser

from .venue_read import PLATFORMS, public_url

# ── what is frozen before the run ─────────────────────────────────────────────────────────────
#: The Applied Diligence commit whose form reader scores this run. The scorer refuses any other.
SCORER_COMMIT = "0a80615"
OVERTURE_RELEASE = "2026-08-19.0"      # read from Overture's own S3 listing (seed.ts); `categories.primary` still present
OVERTURE_BUCKET = "s3://overturemaps-us-west-2"
SAMPLE_SEED = 20260930
PER_CITY = {"food": 170, "activity": 170}   # ≈ 1,020 hosts across three cities
MAX_PAGES_PER_HOST = 5                       # home + up to 4 same-host reservation/booking/contact pages
HOSTS_IN_PARALLEL = 10
PER_HOST_DELAY_S = 1.0
TIMEOUT_S = 15.0
MAX_BYTES = 2_000_000
USER_AGENT = "SashaConcierge-Research/1.0 (+https://project.kanoe.ai; reads venues' own booking pages once, read only)"

CITIES = [  # (city, ISO country, the names it may carry in Overture divisions)
    ("Madrid", "ES", ("Madrid",)),
    ("Lisbon", "PT", ("Lisboa", "Lisbon")),
    ("Berlin", "DE", ("Berlin",)),
]
#: ⚠ The first run found no LOCALITY named "Lisboa" in 2026-08-19.0. A city may be filed as a municipality (localadmin)
#: or a county instead. Candidates at these levels are all read; the most specific level wins, and every candidate is
#: recorded in the run's `seeding`, so the box's provenance is visible, never chosen silently.
SUBTYPE_RANK = ("locality", "localadmin", "county")
FOOD_CATEGORIES = ("restaurant", "cafe", "bar", "bakery")   # seed.ts FOOD_CATEGORIES, unchanged
#: Activities: matched by pattern on the category string (Overture's taxonomy is not published as a list we can pin)
ACTIVITY_PATTERN = (r"museum|gallery|tour|sightseeing|attraction|experience|excursion|cooking_school|culinary|"
                    r"class|workshop|school_of|escape_room|wine_tasting|winery|boat|kayak|surf|climbing|"
                    r"dance_school|art_school|pottery|yoga_studio|bike_rental|segway|theme_park|zoo|aquarium")

#: ⛔ Never fetched: restaurant AND activity booking platforms, plus the social/aggregator hosts seed.ts drops.
PLATFORM_HOSTS = sorted(set(PLATFORMS) | {
    "covermanager", "spotlinker", "dish.co", "letsumai", "umai", "tock", "sevenrooms", "resdiary",
    "fareharbor", "getyourguide", "viator", "tiqets", "bokun", "checkfront", "rezdy", "peek.com", "eventbrite",
    "klook", "civitatis", "musement", "headout", "trekksoft", "regiondo", "ticketmaster", "feverup", "airbnb",
    "booking.com", "expedia",
})
NOT_A_VENUE_HOST = ("instagram.com", "facebook.com", "linktr.ee", "sites.google.com", "just-eat.", "ubereats.com",
                    "glovoapp.com", "zomato.com", "besttables.com", "tripadvisor.", "google.", "wa.me", "youtube.com",
                    "tiktok.com", "x.com", "twitter.com", "linkedin.com")
_LINK = re.compile(r"reserv|reserva|book|booking|contact|contacto|contato|kontakt|tisch|termin|tickets?|entradas|bilhetes|clases|workshop", re.I)


class Refused(Exception):
    pass


# ── the venue list ────────────────────────────────────────────────────────────────────────────

def host_of(url: str) -> Optional[str]:
    try:
        u = urlsplit(url if "://" in url else f"https://{url}")
    except ValueError:
        return None
    h = (u.hostname or "").lower()
    return h or None


def registrable(host: str) -> str:
    """eTLD+1, closely enough for de-duplicating chains (co.uk / com.pt / com.es kept whole)."""
    parts = host.removeprefix("www.").split(".")
    if len(parts) >= 3 and parts[-2] in ("co", "com", "org", "net", "gov", "edu"):
        return ".".join(parts[-3:])
    return ".".join(parts[-2:])


def classify_host(host: str) -> Optional[str]:
    """None when it is a venue's own host; otherwise why it is not fetched."""
    if any(p in host for p in PLATFORM_HOSTS):
        return "a booking platform's domain — never fetched"
    if any(h in host for h in NOT_A_VENUE_HOST):
        return "a social, aggregator or link-hub host — not the venue's own"
    return None


def box_sql(release: str, names: tuple, country: str) -> str:
    ns = ", ".join(f"'{n}'" for n in names)
    subs = ", ".join(f"'{s}'" for s in SUBTYPE_RANK)
    return (f"INSTALL httpfs; LOAD httpfs; SET s3_region='us-west-2';\n"
            f"SELECT id, names.primary AS name, subtype, bbox FROM read_parquet('{OVERTURE_BUCKET}/release/{release}/theme=divisions/type=division_area/*.parquet')\n"
            f"WHERE country = '{country}' AND subtype IN ({subs}) AND names.primary IN ({ns});")


def pick_box(rows: list) -> Tuple[Optional[dict], List[dict]]:
    """(chosen, every candidate). The most specific level wins (locality, then localadmin, then county); within a
    level, the largest area — one city's main polygon rather than an exclave."""
    cands = [{"id": r[0], "name": r[1], "subtype": r[2], "bbox": dict(r[3])} for r in rows]
    area = lambda c: (c["bbox"]["xmax"] - c["bbox"]["xmin"]) * (c["bbox"]["ymax"] - c["bbox"]["ymin"])
    for sub in SUBTYPE_RANK:
        level = [c for c in cands if c["subtype"] == sub]
        if level:
            return max(level, key=area), cands
    return None, cands


def places_sql(release: str, b: dict) -> str:
    cats = ", ".join(f"'{c}'" for c in FOOD_CATEGORIES)
    return (f"SELECT id, names.primary AS name, categories.primary AS cat, websites\n"
            f"FROM read_parquet('{OVERTURE_BUCKET}/release/{release}/theme=places/type=place/*.parquet')\n"
            f"WHERE bbox.xmin BETWEEN {b['xmin']} AND {b['xmax']} AND bbox.ymin BETWEEN {b['ymin']} AND {b['ymax']}\n"
            f"  AND categories.primary IS NOT NULL AND websites IS NOT NULL AND len(websites) > 0\n"
            f"  AND (categories.primary IN ({cats}) OR regexp_matches(categories.primary, '{ACTIVITY_PATTERN}'));")


@dataclass
class Venue:
    city: str
    country: str
    kind: str          # food | activity
    overture_id: str
    name: str
    category: str
    website: str
    host: str


def draw(rows: List[dict], city: str, country: str, rng: random.Random) -> Tuple[List[Venue], Dict[str, int]]:
    """Own hosts only, one per registrable domain, then a seeded random draw of PER_CITY per kind."""
    counts = {"rows": len(rows), "not_own_host": 0, "duplicate_domain": 0}
    by_kind: Dict[str, List[Venue]] = {"food": [], "activity": []}
    seen = set()
    for r in sorted(rows, key=lambda r: r["id"]):             # a stable order, so the draw is reproducible
        site = next((w for w in (r.get("websites") or []) if isinstance(w, str) and w.strip()), None)
        h = host_of(site) if site else None
        if not h or classify_host(h):
            counts["not_own_host"] += 1
            continue
        d = registrable(h)
        if d in seen:
            counts["duplicate_domain"] += 1
            continue
        seen.add(d)
        kind = "food" if r["cat"] in FOOD_CATEGORIES else "activity"
        by_kind[kind].append(Venue(city, country, kind, r["id"], r.get("name") or "", r["cat"], site, h))
    out = []
    for kind, n in PER_CITY.items():
        pool = by_kind[kind]
        counts[f"{kind}_pool"] = len(pool)
        out += rng.sample(pool, min(n, len(pool)))
    return out, counts


# ── reading one venue's own site ──────────────────────────────────────────────────────────────

def fragments(html: str) -> dict:
    """What the frozen scorer needs, and nothing more: forms, labels, frame/script hosts, calendar markers."""
    forms = re.findall(r"<form\b[\s\S]*?</form>", html, re.I)[:20]
    labels = re.findall(r"<label\b[^>]*>[\s\S]*?</label>", html, re.I)[:400]
    srcs = sorted({host_of(s) or "" for s in re.findall(r"<(?:iframe|script)\b[^>]*\bsrc\s*=\s*[\"']([^\"']+)", html, re.I)} - {""})
    return {
        "forms": forms, "labels": labels, "frame_script_hosts": srcs,
        "booked_calendar": bool(re.search(r"wp-content/plugins/booked/|booked-calendar", html, re.I)),
        "date_cells": len(re.findall(r"data-date\s*=\s*[\"']\d{4}-\d{2}-\d{2}[\"']", html, re.I)),
        "platforms_seen": sorted({p for p in PLATFORM_HOSTS if p in " ".join(srcs) or re.search(re.escape(p), html[:MAX_BYTES], re.I)}),
    }


async def read_host(http, v: Venue, resolve) -> Tuple[dict, List[dict]]:
    """robots first → home → up to 4 same-host booking/contact pages. Never another host, never a platform."""
    log = {"host": v.host, "robots": None, "result": None}
    pages: List[dict] = []
    base = v.website if "://" in v.website else f"https://{v.website}"
    try:
        public_url(base, resolve)
    except Exception as e:
        log["result"] = f"not fetched — {e}"
        return log, pages
    rp = RobotFileParser()
    try:
        r = await http("GET", urljoin(base, "/robots.txt"))
        if r.status_code >= 500:
            log.update(robots=f"HTTP {r.status_code}", result="not fetched — robots.txt unreadable (server error)")
            return log, pages
        rp.parse(r.text.splitlines() if r.status_code == 200 else [])
        log["robots"] = f"HTTP {r.status_code}"
    except Exception as e:
        log.update(robots=type(e).__name__, result="not fetched — robots.txt unreachable")
        return log, pages
    queue, done = [base], []
    while queue and len(done) < MAX_PAGES_PER_HOST:
        url = queue.pop(0)
        if url in done:
            continue
        done.append(url)
        if not rp.can_fetch(USER_AGENT, url):
            pages.append({"url": url, "status": None, "note": "robots.txt disallows — not fetched"})
            continue
        try:
            final, resp = await _get_same_host(http, url, v.host, resolve)
        except Exception as e:
            pages.append({"url": url, "status": None, "note": f"not fetched — {e}"})
            continue
        await asyncio.sleep(PER_HOST_DELAY_S)
        html = (resp.text or "")[:MAX_BYTES] if "html" in resp.headers.get("content-type", "") else ""
        entry = {"url": final, "status": resp.status_code, "bytes": len(html),
                 "sha256": hashlib.sha256(html.encode("utf-8", "replace")).hexdigest() if html else None,
                 "fetched_at": datetime.now(timezone.utc).isoformat()}
        if resp.status_code == 200 and html:
            entry["fragments_gz"] = gzip.compress(json.dumps(fragments(html)).encode())
            if url == base:
                for href in re.findall(r"<a\b[^>]*\bhref\s*=\s*[\"']([^\"'#]+)", html, re.I):
                    u = urljoin(final, href)
                    if host_of(u) == host_of(final) and _LINK.search(href) and u not in queue and u not in done and len(queue) < MAX_PAGES_PER_HOST - 1:
                        queue.append(u)
        pages.append(entry)
    log["result"] = f"{sum(1 for p in pages if p.get('status') == 200)} page(s) read"
    return log, pages


async def _get_same_host(http, url: str, venue_host: str, resolve):
    for _ in range(4):
        public_url(url, resolve)
        h = host_of(url) or ""
        if classify_host(h):
            raise Refused(f"{h}: {classify_host(h)}")
        if registrable(h) != registrable(venue_host):
            raise Refused(f"{h} is not the venue's own domain — never followed")
        r = await http("GET", url)
        if r.status_code in (301, 302, 303, 307, 308) and r.headers.get("location"):
            url = urljoin(url, r.headers["location"])
            continue
        return url, r
    raise Refused("more than three redirects")


# ── the run ───────────────────────────────────────────────────────────────────────────────────

def must_be_on_railway(env=os.environ, platform: str = sys.platform) -> None:
    """⚠ `railway run` injects the service's variables into a LOCAL process, so a Railway variable proves nothing on
    its own. Three checks together: the explicit switch, a Linux host (the founder's Mac is darwin), and the replica id
    Railway sets only inside a running deployment."""
    if env.get("MEASURE_FORMS_RUN") != "1":
        raise Refused("MEASURE_FORMS_RUN is not 1 — the run starts only when it is set on its own one-off service")
    if platform == "darwin":
        raise Refused("this is a Mac — the founder's machine and home network; this job never runs here")
    if not env.get("RAILWAY_REPLICA_ID") or not env.get("RAILWAY_DEPLOYMENT_ID"):
        raise Refused("no RAILWAY_REPLICA_ID / RAILWAY_DEPLOYMENT_ID — not a running Railway deployment (`railway run` is local)")
    if not env.get("DATABASE_URL"):
        raise Refused("DATABASE_URL is not set on the service, so nothing could be stored")


async def run() -> None:
    must_be_on_railway()      # ⛔ FIRST — before any import that could open a connection
    import asyncpg
    import duckdb
    import httpx
    from .venue_read import _resolve

    run_id = str(uuid.uuid4())
    started = datetime.now(timezone.utc)
    con = duckdb.connect()
    rng = random.Random(SAMPLE_SEED)
    venues: List[Venue] = []
    seeding: Dict[str, Any] = {}
    for city, country, names in CITIES:
        chosen, cands = pick_box(con.execute(box_sql(OVERTURE_RELEASE, names, country)).fetchall())
        print(f"[measure] {city}: division candidates {[(c['subtype'], c['name'], c['id']) for c in cands]}", flush=True)
        if chosen is None:
            raise Refused(f"no {'/'.join(SUBTYPE_RANK)} named {' or '.join(names)} in {country} in Overture divisions {OVERTURE_RELEASE} — no box, so no seed for {city}")
        b = chosen["bbox"]
        rows = [dict(zip(("id", "name", "cat", "websites"), r)) for r in con.execute(places_sql(OVERTURE_RELEASE, b)).fetchall()]
        picked, counts = draw(rows, city, country, rng)
        venues += picked
        seeding[city] = {"box": b, "box_from": f"Overture divisions {OVERTURE_RELEASE}, division_area {chosen['subtype']} '{chosen['name']}' ({chosen['id']})",
                         "candidates": cands, **counts, "drawn": len(picked)}
        print(f"[measure] {city}: {counts} → drew {len(picked)}", flush=True)

    db = await asyncpg.connect(os.environ["DATABASE_URL"].replace("postgresql+asyncpg://", "postgresql://", 1), statement_cache_size=0)
    await db.execute("insert into measure_runs (run_id, started_at, scorer_commit, overture_release, sample_seed, params, seeding) "
                     "values ($1,$2,$3,$4,$5,$6::jsonb,$7::jsonb)", uuid.UUID(run_id), started, SCORER_COMMIT, OVERTURE_RELEASE,
                     SAMPLE_SEED, json.dumps({"per_city": PER_CITY, "max_pages": MAX_PAGES_PER_HOST, "user_agent": USER_AGENT}), json.dumps(seeding))
    sem = asyncio.Semaphore(HOSTS_IN_PARALLEL)
    async with httpx.AsyncClient(timeout=httpx.Timeout(TIMEOUT_S), follow_redirects=False, headers={"user-agent": USER_AGENT}) as client:
        async def http(method, url):
            return await client.request(method, url)

        async def one(v: Venue):
            async with sem:
                log, pages = await read_host(http, v, _resolve)
            hid = await db.fetchval(
                "insert into measure_hosts (run_id, city, country, kind, overture_id, name, category, website, host, robots, result) "
                "values ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11) returning host_id",
                uuid.UUID(run_id), v.city, v.country, v.kind, v.overture_id, v.name, v.category, v.website, v.host, log["robots"], log["result"])
            for p in pages:
                await db.execute("insert into measure_pages (host_id, url, status, bytes, sha256, fetched_at, note, fragments_gz) "
                                 "values ($1,$2,$3,$4,$5,$6,$7,$8)", hid, p["url"], p.get("status"), p.get("bytes"), p.get("sha256"),
                                 datetime.fromisoformat(p["fetched_at"]) if p.get("fetched_at") else None, p.get("note"), p.get("fragments_gz"))
        await asyncio.gather(*(one(v) for v in venues))
    await db.execute("update measure_runs set finished_at = $2, hosts = $3 where run_id = $1", uuid.UUID(run_id), datetime.now(timezone.utc), len(venues))
    await db.close()
    print(f"[measure] run {run_id}: {len(venues)} hosts read", flush=True)


async def export(path: str, run_id: Optional[str]) -> None:
    """Read-only: one run's hosts and pages from the database into a gzip'd JSON file for the offline scorer. Fetches
    no web page — it may run anywhere DATABASE_URL is set (the founder sets it; its value is never printed)."""
    import asyncpg
    url = os.getenv("DATABASE_URL", "")
    if not url:
        raise Refused("DATABASE_URL is not set")
    db = await asyncpg.connect(url.replace("postgresql+asyncpg://", "postgresql://", 1), statement_cache_size=0)
    try:
        run_row = await (db.fetchrow("select * from measure_runs where run_id = $1", uuid.UUID(run_id)) if run_id
                         else db.fetchrow("select * from measure_runs where finished_at is not null order by started_at desc limit 1"))
        if run_row is None:
            raise Refused("no finished run to export")
        hosts = await db.fetch("select * from measure_hosts where run_id = $1 order by host_id", run_row["run_id"])
        pages = await db.fetch("select p.* from measure_pages p join measure_hosts h on h.host_id = p.host_id where h.run_id = $1 order by page_id", run_row["run_id"])
    finally:
        await db.close()
    out = {"run": {k: (str(v) if isinstance(v, (uuid.UUID, datetime)) else v) for k, v in dict(run_row).items()},
           "hosts": [{k: v for k, v in dict(h).items() if k != "run_id"} for h in hosts],
           "pages": [{**{k: (v.isoformat() if isinstance(v, datetime) else v) for k, v in dict(p).items() if k != "fragments_gz"},
                      "fragments": json.loads(gzip.decompress(p["fragments_gz"])) if p["fragments_gz"] else None} for p in pages]}
    for k in ("params", "seeding"):
        if isinstance(out["run"].get(k), str):
            out["run"][k] = json.loads(out["run"][k])
    with gzip.open(path, "wt") as f:
        json.dump(out, f)
    print(f"[measure] exported run {out['run']['run_id']}: {len(hosts)} hosts, {len(pages)} pages → {path}")


def plan() -> str:
    lines = [f"S-40 form measurement — scorer frozen at Applied Diligence {SCORER_COMMIT}; Overture {OVERTURE_RELEASE}; seed {SAMPLE_SEED}",
             f"per city: {PER_CITY} ≈ {len(CITIES) * sum(PER_CITY.values())} hosts; ≤{MAX_PAGES_PER_HOST} pages each; {HOSTS_IN_PARALLEL} hosts at once; {PER_HOST_DELAY_S}s between a host's pages",
             f"never fetched: {len(PLATFORM_HOSTS)} booking-platform patterns + {len(NOT_A_VENUE_HOST)} social/aggregator hosts; robots first; own registrable domain only; served markup only", ""]
    for city, country, names in CITIES:
        lines += [f"-- {city}", box_sql(OVERTURE_RELEASE, names, country), "-- then, with that box:", places_sql(OVERTURE_RELEASE, {"xmin": "<xmin>", "xmax": "<xmax>", "ymin": "<ymin>", "ymax": "<ymax>"}), ""]
    return "\n".join(lines)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan", action="store_true")
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--export", metavar="PATH")
    ap.add_argument("--run-id")
    a = ap.parse_args()
    if a.export:
        try:
            asyncio.run(export(a.export, a.run_id))
        except Refused as e:
            print(f"[measure] REFUSED: {e}", file=sys.stderr)
            sys.exit(2)
    elif a.run:
        try:
            asyncio.run(run())
        except Refused as e:
            print(f"[measure] REFUSED: {e}", file=sys.stderr)
            sys.exit(2)
    else:
        print(plan())
