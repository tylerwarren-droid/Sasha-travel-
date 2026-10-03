"""CR 1 · the Slate reader — each school's visit calendar, read from the school's OWN domain, read-only.

How a read is done (S-38's rules, the TheFork lesson):
  · robots.txt is read first, per host, and obeyed for our User-Agent token (KanoeCampusMe) and for *;
  · ≤ one request per PACE seconds per host; a read is cached for CACHE_S, so a family asking twice costs nothing;
  · an honest User-Agent naming Kanoe and a contact;
  · every read is kept as a receipt: url, HTTP status, sha256 of the body, when — a session card cites its own read.
Nothing here POSTs a registration. The one POST is Slate's own capacity read (/register/form?cmd=counts), which the
school's page makes itself to grey out full sessions; it writes nothing.

Endpoints (found 3 Oct 2026 in the schools' own scripts; docs/campusme/READS.md):
  widget:   {service}&cmd=event_dates&dtstart=&dtend=  → {"dates": [["2026-10-14","0"], …]}   ("0" = available)
            {service}&cmd=event_list&date=&query=      → HTML: "<strong>Campus Tour</strong> 9:00 AM–10:00 AM | Visitor
                                                         Center | Spaces Available: 51", one /register/?id= form link
  register: {page}?cmd=getDates&dtstart=&dtend=        → the same JSON
            {page}?cmd=getEvents&date=&query=          → HTML: one "?id=<event>" link per event that day
            {page}?id=<event>                          → the form: each session an input[data-event] with its summary
            /register/form?cmd=counts&id=<event>       → {"results":{"results":[{"id":…,"exceed":"0"|"1"}]}}
"""
from __future__ import annotations

import asyncio
import hashlib
import html as H
import logging
import re
import time
import urllib.parse
import urllib.robotparser
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

log = logging.getLogger("products.campus.slate")

UA = "KanoeCampusMe/0.1 (+https://project.kanoe.ai; read-only campus-visit reader; tyler@kanoe.ai)"
UA_TOKEN = "KanoeCampusMe"
PACE = 4.0            # seconds between requests to one host
CACHE_S = 15 * 60
NOW = lambda: datetime.now(timezone.utc)


class ReadRefused(Exception):
    """robots.txt disallows us, or robots couldn't be read: the host stays unread (S-77 §1's rule)."""


@dataclass
class Read:
    url: str
    status: int
    sha256: str
    at: str
    body: str = field(repr=False, default="")

    def receipt(self) -> dict:
        return {"url": self.url, "status": self.status, "sha256": self.sha256, "at": self.at}


@dataclass
class Session:
    school: str                 # key in schools.SCHOOLS
    day: str                    # YYYY-MM-DD, the school's local date
    start: str                  # "09:00" local
    end: Optional[str]
    title: str
    location: Optional[str]
    status: str                 # "open" | "full"
    spaces: Optional[int]       # only where the school publishes it (Yale); Penn says only open/full
    form_url: str               # the school's own registration page for this session
    event_id: Optional[str]     # Slate's event id where the form selects one (Penn)
    read: dict                  # the receipt of the read this came from

    def as_dict(self) -> dict:
        return asdict(self)


Fetch = Callable[[str, str, Optional[dict]], "asyncio.Future"]   # (method, url, form) → (status, text)


async def _httpx_fetch(method: str, url: str, form: Optional[dict]) -> Tuple[int, str]:
    import httpx
    async with httpx.AsyncClient(timeout=httpx.Timeout(20.0), follow_redirects=False,
                                 headers={"user-agent": UA, "accept-language": "en"}) as c:
        r = await (c.post(url, data=form) if method == "POST" else c.get(url))
    return r.status_code, r.text


class Reader:
    def __init__(self, fetch: Optional[Callable] = None, pace: float = PACE) -> None:
        self._fetch = fetch or _httpx_fetch
        self.pace = pace
        self._last: Dict[str, float] = {}
        self._locks: Dict[str, asyncio.Lock] = {}
        self._robots: Dict[str, Tuple[float, Optional[urllib.robotparser.RobotFileParser]]] = {}
        self._cache: Dict[str, Tuple[float, Read]] = {}
        self.reads: List[dict] = []          # every receipt, in order (tests and READS.md read it)

    async def _paced(self, host: str, method: str, url: str, form: Optional[dict]) -> Tuple[int, str]:
        lock = self._locks.setdefault(host, asyncio.Lock())
        async with lock:
            wait = self._last.get(host, 0) + self.pace - time.monotonic()
            if wait > 0:
                await asyncio.sleep(wait)
            try:
                return await self._fetch(method, url, form)
            finally:
                self._last[host] = time.monotonic()

    async def allowed(self, url: str) -> bool:
        u = urllib.parse.urlsplit(url)
        hit = self._robots.get(u.netloc)
        if hit is None or time.monotonic() - hit[0] > 24 * 3600:
            status, text = await self._paced(u.netloc, "GET", f"{u.scheme}://{u.netloc}/robots.txt", None)
            rp = None
            if status == 200:
                rp = urllib.robotparser.RobotFileParser()
                rp.parse(text.splitlines())
            self.reads.append({"url": f"{u.scheme}://{u.netloc}/robots.txt", "status": status,
                               "sha256": hashlib.sha256(text.encode()).hexdigest(), "at": NOW().isoformat()})
            if status == 404:                # no file: no directive (S-77 §1)
                rp = urllib.robotparser.RobotFileParser()
                rp.parse([])
            hit = self._robots[u.netloc] = (time.monotonic(), rp)
        rp = hit[1]
        if rp is None:
            raise ReadRefused(f"{u.netloc}'s robots.txt couldn't be read, so it stays unread")
        return rp.can_fetch(UA_TOKEN, url) and rp.can_fetch("*", url)

    async def read(self, url: str, method: str = "GET", form: Optional[dict] = None) -> Read:
        ck = method + " " + url + " " + urllib.parse.urlencode(sorted((form or {}).items()))
        hit = self._cache.get(ck)
        if hit and time.monotonic() - hit[0] < CACHE_S:
            return hit[1]
        if not await self.allowed(url):
            raise ReadRefused(f"robots.txt on {urllib.parse.urlsplit(url).netloc} disallows this page")
        status, text = await self._paced(urllib.parse.urlsplit(url).netloc, method, url, form)
        r = Read(url=url, status=status, sha256=hashlib.sha256(text.encode()).hexdigest(), at=NOW().isoformat(), body=text)
        self.reads.append(r.receipt())
        if status == 200:
            self._cache[ck] = (time.monotonic(), r)
        return r


READER = Reader()


# ── dates ────────────────────────────────────────────────────────────────────────────────────────────────────────────

def _base(s: dict) -> str:
    return f"https://{s['host']}"


def dates_url(s: dict, start: date, end: date) -> str:
    q = f"dtstart={start.isoformat()}&dtend={end.isoformat()}"
    if s["variant"] == "widget":
        return f"{_base(s)}{s['service']}&cmd=event_dates&{q}"
    return f"{_base(s)}{s['service']}?cmd=getDates&{q}"


def parse_dates(body: str) -> List[Tuple[str, bool]]:
    import json
    d = json.loads(body or "{}").get("dates") or []
    return [(str(x[0]), str(x[1]) == "0") for x in d if isinstance(x, list) and x]


async def dates(s: dict, start: date, end: date, reader: Optional[Reader] = None) -> Tuple[List[Tuple[str, bool]], dict]:
    r = await (reader or READER).read(dates_url(s, start, end))
    if r.status != 200:
        raise ReadRefused(f"{s['name']}'s calendar answered HTTP {r.status}")
    return parse_dates(r.body), r.receipt()


# ── sessions ─────────────────────────────────────────────────────────────────────────────────────────────────────────

_TIME = r"(\d{1,2}:\d{2}\s*[AaPp]\.?[Mm]\.?)"


def to24(t: str) -> str:
    t = re.sub(r"[\s.]", "", t).upper()
    hh, mm = t[:-2].split(":")
    h = int(hh) % 12 + (12 if t.endswith("PM") else 0)
    return f"{h:02d}:{int(mm):02d}"


def _text(fragment: str) -> str:
    t = re.sub(r"<(style|script)\b.*?</\1>", " ", fragment, flags=re.S | re.I)
    t = re.sub(r"<br\s*/?>|</p>|</li>|</div>", "\n", t, flags=re.I)
    return H.unescape(re.sub(r"<[^>]+>", " ", t))


def parse_widget_list(s: dict, day: str, body: str, receipt: dict) -> List[Session]:
    """Yale: each session is one line — "Campus Tour 9:00 AM–10:00 AM | Visitor Center | Spaces Available: 51"."""
    form = re.search(r'href="(/register/\?id=[0-9a-f-]{36})"', body)
    form_url = f"{_base(s)}{H.unescape(form.group(1))}" if form else s["visit_page"]
    out = []
    for line in _text(body).split("\n"):
        line = re.sub(r"\s+", " ", line).strip()
        m = re.match(rf"(?P<title>.+?)\s+{_TIME}\s*[–—-]\s*{_TIME}\s*\|\s*(?P<loc>[^|]+?)\s*\|\s*Spaces Available:\s*(?P<n>\d+)", line)
        if not m:
            continue
        n = int(m.group("n"))
        out.append(Session(school=s["key"], day=day, start=to24(m.group(2)), end=to24(m.group(3)), title=m.group("title").strip(),
                           location=m.group("loc").strip(), status="open" if n > 0 else "full", spaces=n,
                           form_url=form_url, event_id=None, read=receipt))
    return out


def parse_register_events(body: str) -> List[str]:
    """Penn's day list: one "?id=<event>" link per event (the event's own registration form)."""
    return list(dict.fromkeys(re.findall(r'href="\?id=([0-9a-f-]{36})"', body)))


def parse_register_sessions(s: dict, day: str, event_id: str, body: str, receipt: dict) -> List[Session]:
    """The event's form: every session is an input[data-event] whose value carries its own summary
    ("Wednesday, October 14 at 10:15 AM - Morning Tour"), under a legend naming the kind ("Campus Tours (1 hr 30 mins)")."""
    out = []
    for q in re.finditer(r'data-type="plugin:event"[^>]*>(.*?)</fieldset>', body, re.S):
        legend = re.search(r"<legend>(.*?)</legend>", q.group(1), re.S)
        kind = re.sub(r"\s*;?\s*select\s+one\s*:?", "", re.sub(r"\s+", " ", _text(legend.group(1))).strip(), flags=re.I).rstrip(":") if legend else ""
        for inp in re.finditer(r'<input[^>]*data-event="([0-9a-f-]{36})"[^>]*value="([^"]*)"', q.group(1)):
            summary = urllib.parse.parse_qs(H.unescape(inp.group(2))).get("summary", [""])[0]
            m = re.search(rf"at\s+{_TIME}\s*-\s*(.+)$", summary)
            if not m:
                continue
            out.append(Session(school=s["key"], day=day, start=to24(m.group(1)), end=None,
                               title=m.group(2).strip() + (f" · {kind}" if kind else ""), location=None, status="open",
                               spaces=None, form_url=f"{_base(s)}{s['service']}?id={event_id}", event_id=inp.group(1),
                               read=receipt))
    loc = re.search(r"Undergraduate Admissions Visitor Center", body)
    for x in out:
        x.location = "Undergraduate Admissions Visitor Center" if loc else None
    return out


def counts_url(s: dict, form_event: str) -> str:
    return f"{_base(s)}/register/form?cmd=counts&id={form_event}"


def apply_counts(sessions: List[Session], body: str) -> None:
    import json
    try:
        rows = ((json.loads(body or "{}").get("results") or {}).get("results")) or []
    except ValueError:
        rows = []
    full = {r.get("id") for r in rows if str(r.get("exceed")) == "1"}
    seen = {r.get("id") for r in rows}
    for x in sessions:
        if x.event_id in full:
            x.status = "full"
        elif x.event_id not in seen:
            x.status = "unknown"


async def sessions(s: dict, day: str, attendees: int = 2, reader: Optional[Reader] = None) -> List[Session]:
    """Every session the school's own calendar shows on that day, with open/full as the school's own page decides it."""
    rd = reader or READER
    if s["variant"] == "widget":
        r = await rd.read(f"{_base(s)}{s['service']}&cmd=event_list&date={day}&query=")
        if r.status != 200:
            raise ReadRefused(f"{s['name']}'s calendar answered HTTP {r.status}")
        return parse_widget_list(s, day, r.body, r.receipt())
    if s["variant"] != "register":
        raise ReadRefused(f"{s['name']} isn't read by CampusMe yet")
    r = await rd.read(f"{_base(s)}{s['service']}?cmd=getEvents&date={day}&query=")
    if r.status != 200:
        raise ReadRefused(f"{s['name']}'s calendar answered HTTP {r.status}")
    out: List[Session] = []
    for ev in parse_register_events(r.body):
        page = await rd.read(f"{_base(s)}{s['service']}?id={ev}")
        if page.status != 200:
            continue
        found = parse_register_sessions(s, day, ev, page.body, page.receipt())
        if found:
            c = await rd.read(counts_url(s, ev), "POST", {"cmd": "fetch", "ids": ",".join(x.event_id for x in found),
                                                           "attendees": str(attendees), "registrants": "1"})
            apply_counts(found, c.body if c.status == 200 else "")
        out.extend(found)
    return sorted(out, key=lambda x: (x.start, x.title))


# ── the form, read for the hand-over (never submitted) ───────────────────────────────────────────────────────────────

@dataclass
class Question:
    id: str
    type: str
    export: Optional[str]
    label: str
    required: bool
    options: List[str]


def parse_form(body: str) -> List[Question]:
    out = []
    last_p = ""   # an unlabelled checkbox ("By submitting this form, you understand…") is labelled by the paragraph above it
    for m in re.finditer(r'<div class="form_question[^"]*"[^>]*?data-id="([^"]+)"[^>]*?data-type="([^"]+)"([^>]*)>', body):
        seg = body[m.end():m.end() + 6000]
        nxt = seg.find('<div class="form_question')
        seg = seg[:nxt] if nxt > 0 else seg
        if m.group(2) in ("header", "h2", "p", "hidden"):
            if m.group(2) == "p":
                last_p = re.sub(r"\s+", " ", _text(seg)).strip()[:300]
            continue
        lab = re.search(r'class="form_label"[^>]*>(.*?)</(?:label|div)>', seg, re.S)
        label = re.sub(r"\s+", " ", _text(lab.group(1))).strip().rstrip("*").strip() if lab else ""
        if not label and m.group(2) == "checkbox":
            label = last_p
        exp = re.search(r'data-export="([^"]*)"', m.group(3))
        opts = [re.sub(r"\s+", " ", _text(o)).strip() for o in re.findall(r"<option[^>]*>(.*?)</option>", seg, re.S)]
        opts += [re.sub(r"\s+", " ", _text(o)).strip() for o in re.findall(r'<label for="form_[^"]+_\d+"[^>]*>(.*?)</label>', seg, re.S)]
        out.append(Question(id=m.group(1), type=m.group(2), export=exp.group(1) if exp else None, label=label,
                            required='data-required="1"' in m.group(3), options=[o for o in opts if o]))
    return out


_CHALLENGE = re.compile(r"recaptcha|hcaptcha|turnstile|cf-chl|g-recaptcha", re.I)


async def form(url: str, reader: Optional[Reader] = None) -> Tuple[List[Question], bool, dict, int]:
    """(questions, a CAPTCHA marker is in the served page, the read's receipt, page count)."""
    r = await (reader or READER).read(url)
    if r.status != 200:
        raise ReadRefused(f"the registration page answered HTTP {r.status}")
    pages = re.search(r'data-page-count="(\d+)"', r.body)
    return parse_form(r.body), bool(_CHALLENGE.search(r.body)), r.receipt(), int(pages.group(1)) if pages else 1
