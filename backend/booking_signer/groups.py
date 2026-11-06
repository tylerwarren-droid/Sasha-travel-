"""Sasha 332 · GROUP MOVEMENT v1 (Tyler 3 Nov 20:30–20:55: a company moves 20 workers to Madrid). docs/sasha/S-332-group-movement.md.

THE ONE RECORD per worker is their trip (trips + its trip_basket_items — the planned flights and hotel, exactly as anyone's trip holds
them today — and trip_items once booked). The group's MASTER LIST is computed from those trips each time it is read (view()), never
stored. The group's rules (price limits) live in ONE place: group_movements.rules.

  read_rows(text | csv | xlsx | photo)  the organiser's list → rows (a spreadsheet, a photo of one, pasted or typed text)
  members_from(rows, movement)          rows → (members, unclear): a row we can't read for sure is never guessed — unclear
  batch_question(unclear)               ONE question listing every unclear row (never one per row)
  limit_for(rules, member)              the member's limits: their own, else their grade's — from the ONE place
  plan(account, movement_id)            one by one: each worker's trip, their flights out and back and the hotel near the area, within
                                        their limit (over → flagged, not booked). Planning only (booking: CR 163)
  view(account, movement_id)            THE MASTER LIST: one row per worker — transport, hotel, price, limit, status — from their trip now
  summary(view)                         the master list in a few lines (WhatsApp)
"""
from __future__ import annotations

import csv
import io
import json
import logging
import re
import uuid
import zipfile
from datetime import date, datetime
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple
from xml.etree import ElementTree as ET

log = logging.getLogger("booking_signer.groups")

STATUSES = ("not planned", "planned", "needs vault", "over limit", "booked", "cancelled")

# ── 1 · reading the list ───────────────────────────────────────────────────────────────────────────────────────────────────

#: the list's columns, by the words organisers use for them (English and Spanish)
COLUMNS = {
    "name": ("name", "full name", "worker", "employee", "nombre", "nombre completo", "trabajador", "empleado"),
    "home_city": ("home city", "home", "city", "from", "origin", "ciudad", "ciudad de origen", "origen", "lives in"),
    "out_date": ("out", "out date", "outbound", "arrive", "arrival", "start", "ida", "fecha ida", "llegada", "departure"),
    "back_date": ("back", "back date", "return", "return date", "end", "vuelta", "fecha vuelta", "regreso"),
    "grade": ("grade", "role", "level", "category", "categoria", "categoría", "puesto", "rank"),
    "email": ("email", "e-mail", "mail", "correo", "email address"),   # Sasha 333 · where their vault invite goes
    "phone": ("phone", "mobile", "whatsapp", "teléfono", "telefono", "móvil", "movil"),
    "home_airport": ("home airport", "airport", "aeropuerto", "iata"),   # Sasha 351 · where they fly from (a city's word stays home_city)
}
ORDER = ("name", "home_city", "out_date", "back_date", "grade")   # a list with no header: in this order
_MONTHS = {m: i + 1 for i, m in enumerate(("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"))}
_MONTHS.update({"ene": 1, "abr": 4, "ago": 8, "dic": 12, "sept": 9})


def _norm(s: Any) -> str:
    return " ".join(str(s or "").strip().split())


def _col(h: str) -> Optional[str]:
    h = _norm(h).lower().rstrip(":")
    return next((k for k, words in COLUMNS.items() if h in words), None)


def _split(line: str) -> List[str]:
    for sep in ("\t", ";", "|", ","):
        if sep in line:
            return [_norm(x) for x in line.split(sep)]
    return [_norm(line)]


def _table(lines: List[List[str]]) -> List[Dict[str, str]]:
    lines = [l for l in lines if any(c for c in l)]
    if not lines:
        return []
    head = [_col(c) for c in lines[0]]
    if sum(1 for h in head if h) >= 2:   # a header row: its own column order
        keys, body = head, lines[1:]
    else:
        keys, body = list(ORDER), lines
    out = []
    for i, l in enumerate(body, 1):
        r = {k: _norm(v) for k, v in zip(keys, l) if k}
        r["_line"] = str(i)
        out.append(r)
    return out


def read_text(text: str) -> List[Dict[str, str]]:
    """Pasted or typed text: one worker per line, its columns split by tab, ; | or , (a header row, if there is one, names them)."""
    return _table([_split(l) for l in (text or "").splitlines() if l.strip()])


def read_csv(data: bytes) -> List[Dict[str, str]]:
    t = data.decode("utf-8-sig", errors="replace")
    try:
        dialect = csv.Sniffer().sniff(t.splitlines()[0] if t else ",", delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel
    return _table([[_norm(c) for c in row] for row in csv.reader(io.StringIO(t), dialect)])


_NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


def read_xlsx(data: bytes) -> List[Dict[str, str]]:
    """An .xlsx (a zip of XML): its first sheet's cells, read directly — no spreadsheet library, nothing executed."""
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        shared: List[str] = []
        if "xl/sharedStrings.xml" in z.namelist():
            for si in ET.fromstring(z.read("xl/sharedStrings.xml")).findall("m:si", _NS):
                shared.append("".join(t.text or "" for t in si.iter(f"{{{_NS['m']}}}t")))
        sheet = next((n for n in sorted(z.namelist()) if re.fullmatch(r"xl/worksheets/sheet\d+\.xml", n)), None)
        if not sheet:
            return []
        rows: List[List[str]] = []
        for row in ET.fromstring(z.read(sheet)).iter(f"{{{_NS['m']}}}row"):
            cells: Dict[int, str] = {}
            for c in row.findall("m:c", _NS):
                col = _col_index(c.get("r") or "")
                v = c.find("m:v", _NS)
                inline = c.find("m:is", _NS)
                if c.get("t") == "s" and v is not None:
                    val = shared[int(v.text or 0)]
                elif c.get("t") == "inlineStr" and inline is not None:
                    val = "".join(t.text or "" for t in inline.iter(f"{{{_NS['m']}}}t"))
                else:
                    val = v.text if v is not None else ""
                    if val and re.fullmatch(r"\d{5}(\.0+)?", val) and 30000 < float(val) < 60000:   # an Excel date serial
                        val = date.fromordinal(date(1899, 12, 30).toordinal() + int(float(val))).isoformat()
                cells[col] = val or ""
            if cells:
                rows.append([cells.get(i, "") for i in range(max(cells) + 1)])
        return _table(rows)


def _col_index(ref: str) -> int:
    letters = re.match(r"[A-Z]+", ref or "A")
    n = 0
    for ch in (letters.group(0) if letters else "A"):
        n = n * 26 + (ord(ch) - 64)
    return n - 1


READ_PHOTO: Optional[Callable[[bytes, str], Awaitable[str]]] = None   # tests replace it


async def read_photo(image: bytes, media_type: str) -> List[Dict[str, str]]:
    """A photo of the list: the model copies the table as it is (one line per row, columns split by " | "), never adding or guessing —
    then the same reader as pasted text (a cell it can't read is left empty, and that row is asked about)."""
    if READ_PHOTO is not None:
        return read_text(await READ_PHOTO(image, media_type))
    import base64
    import os
    import app.services.llm as LLM
    r = await LLM.client.messages.create(
        model=os.getenv("SASHA_GROUP_SCAN_MODEL", "claude-opus-5-5"), max_tokens=4000,
        messages=[{"role": "user", "content": [
            {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": base64.b64encode(image).decode()}},
            {"type": "text", "text": "This is a photo of a list of workers. Copy the table exactly as written: the header row first, then one line "
                                     "per row, its cells separated by \" | \". A cell you can't read for sure: leave it EMPTY. Never guess, "
                                     "never add a row. Reply with the table only."}]}])
    return read_text("".join(b.text for b in r.content if getattr(b, "type", "") == "text"))


def _date(v: str, year: int) -> Optional[str]:
    v = _norm(v).lower().rstrip(".")
    if not v:
        return None
    m = re.fullmatch(r"(\d{4})-(\d{1,2})-(\d{1,2})", v)
    try:
        if m:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3))).isoformat()
        m = re.fullmatch(r"(\d{1,2})[/.-](\d{1,2})(?:[/.-](\d{2,4}))?", v)
        if m:
            y = int(m.group(3)) if m.group(3) else year
            return date(y + 2000 if y < 100 else y, int(m.group(2)), int(m.group(1))).isoformat()   # day first (Europe)
        m = re.fullmatch(r"(\d{1,2})(?:st|nd|rd|th)?\s+(?:de\s+)?([a-z]{3,9})\.?(?:\s+(?:de\s+)?(\d{4}))?", v)
        if m and m.group(2)[:4] in _MONTHS or (m and m.group(2)[:3] in _MONTHS):
            mon = _MONTHS.get(m.group(2)[:4]) or _MONTHS[m.group(2)[:3]]
            return date(int(m.group(3) or year), mon, int(m.group(1))).isoformat()
        m = re.fullmatch(r"([a-z]{3,9})\.?\s+(\d{1,2})(?:st|nd|rd|th)?(?:,?\s+(\d{4}))?", v)
        if m and m.group(1)[:3] in _MONTHS:
            return date(int(m.group(3) or year), _MONTHS[m.group(1)[:3]], int(m.group(2))).isoformat()
    except ValueError:
        return None
    return None


def members_from(rows: List[Dict[str, str]], movement: Dict[str, Any], grades: Optional[List[str]] = None) -> Tuple[List[dict], List[dict]]:
    """Rows → (members, unclear). A row is unclear — never guessed — when its name, home city, out or back date can't be read, back comes
    before out, or its grade isn't one the group's limits know (when they're set). A missing date takes the movement's own date."""
    year = int(str(movement.get("starts_on") or date.today().isoformat())[:4])
    known = {g.lower() for g in grades or []}
    good, unclear, seen = [], [], set()
    for r in rows:
        why = []
        name = _norm(r.get("name"))
        if not name or len(name) < 3 or re.search(r"\d", name):
            why.append("the name")
        city = _norm(r.get("home_city"))
        airport = _norm(r.get("home_airport")).upper() or None
        if airport and not re.fullmatch(r"[A-Z]{3}", airport):
            why.append(f"the home airport (“{r.get('home_airport')}” — three letters, like MAD)")
            airport = None
        if (not city or re.fullmatch(r"[\d\W]+", city)) and not airport:
            why.append("the home city")
        out = _date(r.get("out_date") or "", year) if r.get("out_date") else movement.get("starts_on")
        back = _date(r.get("back_date") or "", year) if r.get("back_date") else movement.get("ends_on")
        if r.get("out_date") and not out:
            why.append(f"the out date (“{r['out_date']}”)")
        if r.get("back_date") and not back:
            why.append(f"the back date (“{r['back_date']}”)")
        if not out or not back:
            why.append("the dates") if "the dates" not in why and not any(w.startswith("the out") or w.startswith("the back") for w in why) else None
        elif back < out:
            why.append("the dates (back is before out)")
        grade = _norm(r.get("grade")).lower() or None
        if known and (not grade or grade not in known):
            why.append(f"the grade (“{r.get('grade') or 'none'}” — the limits know {', '.join(sorted(known))})")
        if name and name.lower() in seen:
            why.append("the name (listed twice)")
        if why:
            unclear.append({"line": r.get("_line"), "row": {k: v for k, v in r.items() if not k.startswith("_")}, "why": why})
            continue
        seen.add(name.lower())
        email = _norm(r.get("email")).lower() or None
        phone = re.sub(r"[^\d+]", "", _norm(r.get("phone"))) or None
        good.append({"name": name, "home_city": city or None, "out_date": out, "back_date": back, "grade": grade,
                     **({"home_airport": airport} if airport else {}),
                     **({"email": email} if email and re.fullmatch(r"[^@\s]+@[^@\s]+\.[a-z]{2,}", email) else {}),
                     **({"phone": phone} if phone and re.fullmatch(r"\+\d{8,15}", phone) else {})})
    return good, unclear


def batch_question(unclear: List[dict]) -> Optional[str]:
    """ONE question for every unclear row together — never one per row."""
    if not unclear:
        return None
    lines = [f"• Row {u['line']} ({u['row'].get('name') or 'no name'}): {', '.join(u['why'])}" for u in unclear]
    n = len(unclear)
    return (f"{n} row{'s' if n != 1 else ''} I couldn't read for sure — can you send {'them' if n != 1 else 'it'} again, corrected?\n"
            + "\n".join(lines))


# ── 2 · the store (Postgres; tests use MemStore) ──────────────────────────────────────────────────────────────────────────────

#: Sasha 351 · THE ROSTER (053): a person's own details, kept ONCE under the company — every trip reads them from here
PERSON = ("name", "grade", "home_airport", "home_city", "email", "phone")
_MEMBER_Q = ("select gm.id, gm.movement_id, gm.person_id, gm.out_date, gm.back_date, gm.trip_id, gm.created_at, "
             "p.name, p.grade, p.home_airport, p.home_city, p.email, p.phone "
             "from group_members gm join group_people p on p.id = gm.person_id ")


class PgStore:
    """Sasha 351 · a company (groups) has ONE roster (group_people: each worker once, owning their vault); a trip (group_movements) is a
    SELECTION from it — group_members is the link (person, movement, dates, the worker's trip) and copies nothing about the person."""

    def __init__(self, run):
        self._run = run

    async def new_movement(self, owner: str, company: str, destination: str, starts_on, ends_on, hotel_area) -> str:
        async def go(c):
            gid = await c.fetchval("select id from groups where owner_id = $1 and name = $2 limit 1", uuid.UUID(owner), company)
            if gid is None:
                gid = await c.fetchval("insert into groups (owner_id, name) values ($1,$2) returning id", uuid.UUID(owner), company)
            return str(await c.fetchval("insert into group_movements (group_id, destination, starts_on, ends_on, hotel_area) values "
                                        "($1,$2,$3,$4,$5) returning id", gid, destination, _d(starts_on), _d(ends_on), hotel_area))
        return await self._run(go)

    async def movement(self, owner: str, movement_id: Optional[str] = None) -> Optional[dict]:
        async def go(c):
            q = ("select m.*, g.name as company, g.owner_id from group_movements m join groups g on g.id = m.group_id where g.owner_id = $1 "
                 + ("and m.id = $2 " if movement_id else "") + "order by m.opened_at desc, m.created_at desc limit 1")   # Sasha 351 · the OPEN trip
            r = await c.fetchrow(q, uuid.UUID(owner), *([uuid.UUID(movement_id)] if movement_id else []))
            return _row(r) if r else None
        return await self._run(go)

    async def open(self, owner: str, movement_id: str) -> bool:
        """Sasha 351 · the organiser's CURRENT trip is the one they opened last (sql/056 opened_at) — never just the newest made."""
        r = await self._run(lambda c: c.execute("update group_movements m set opened_at = now() from groups g where g.id = m.group_id "
                                                "and g.owner_id = $1 and m.id = $2", uuid.UUID(owner), uuid.UUID(movement_id)))
        return str(r).split()[-1] != "0"

    async def trips(self, owner: str) -> List[dict]:
        async def go(c):
            rows = await c.fetch("select m.id, g.name as company, m.destination, m.starts_on, m.ends_on, m.opened_at, "
                                 "(select count(*) from group_members gm where gm.movement_id = m.id) as people from group_movements m "
                                 "join groups g on g.id = m.group_id where g.owner_id = $1 order by m.opened_at desc, m.created_at desc limit 50",
                                 uuid.UUID(owner))
            return [_row(r) for r in rows]
        return await self._run(go)

    async def set_rules(self, owner: str, movement_id: str, rules: dict) -> None:
        async def go(c):
            await c.execute("update group_movements m set rules = $3::text::jsonb from groups g where g.id = m.group_id and g.owner_id = $1 "
                            "and m.id = $2",   # Sasha 345 · an OBJECT (the pool's codec already JSON-encodes: ::jsonb stored a string)
                            uuid.UUID(owner), uuid.UUID(movement_id), json.dumps(rules))
        await self._run(go)

    # ── the company and its roster ──
    async def company(self, owner: str, name: Optional[str] = None, create: bool = False) -> Optional[dict]:
        """The organiser's company by its name (made when `create`), else the one of their OPEN trip, else their latest company."""
        async def go(c):
            if name:
                r = await c.fetchrow("select * from groups where owner_id = $1 and lower(name) = lower($2) order by created_at desc limit 1",
                                     uuid.UUID(owner), name)
                if r is None and create:
                    r = await c.fetchrow("insert into groups (owner_id, name) values ($1,$2) returning *", uuid.UUID(owner), name[:200])
                return _row(r) if r else None
            r = await c.fetchrow("select g.* from group_movements m join groups g on g.id = m.group_id where g.owner_id = $1 "
                                 "order by m.opened_at desc, m.created_at desc limit 1", uuid.UUID(owner))   # the OPEN trip's company
            r = r or await c.fetchrow("select * from groups where owner_id = $1 order by created_at desc limit 1", uuid.UUID(owner))
            return _row(r) if r else None
        return await self._run(go)

    async def people(self, group_id: str) -> List[dict]:
        async def go(c):
            return [_row(r) for r in await c.fetch("select * from group_people where group_id = $1 order by name", uuid.UUID(group_id))]
        return await self._run(go)

    async def add_person(self, group_id: str, person: dict) -> str:
        async def go(c):
            return str(await c.fetchval(
                "insert into group_people (group_id, name, grade, home_airport, home_city, email, phone) values ($1,$2,$3,$4,$5,$6,$7) returning id",
                uuid.UUID(group_id), person["name"], person.get("grade"), person.get("home_airport"), person.get("home_city"),
                person.get("email"), person.get("phone")))
        return await self._run(go)

    async def update_person(self, group_id: str, person_id: str, fields: dict) -> Optional[dict]:
        sets = {k: v for k, v in fields.items() if k in PERSON}
        if not sets:
            return None

        async def go(c):
            cols = ", ".join(f"{k} = ${i + 3}" for i, k in enumerate(sets))
            r = await c.fetchrow(f"update group_people set {cols}, updated_at = now() where group_id = $1 and id = $2 returning *",
                                 uuid.UUID(group_id), uuid.UUID(person_id), *sets.values())
            return _row(r) if r else None
        return await self._run(go)

    # ── a trip: the people selected from the roster ──
    async def select(self, movement_id: str, person_ids: List[str], out_date=None, back_date=None) -> int:
        async def go(c):
            n = 0
            for pid in person_ids:
                n += 1 if await c.fetchval(
                    "insert into group_members (movement_id, person_id, out_date, back_date) select $1, $2, coalesce($3, m.starts_on), "
                    "coalesce($4, m.ends_on) from group_movements m join group_people p on p.group_id = m.group_id and p.id = $2 "
                    "where m.id = $1 on conflict (movement_id, person_id) where person_id is not null do nothing returning id",
                    uuid.UUID(movement_id), uuid.UUID(pid), _d(out_date), _d(back_date)) else 0
            return n
        return await self._run(go)

    async def remove_member(self, movement_id: str, member_id: str) -> None:
        """Sasha 346 · a swap before anything is booked: who leaves comes off THIS trip (the person stays on the roster)."""
        async def go(c):
            await c.execute("delete from group_members where movement_id = $1 and id = $2", uuid.UUID(movement_id), uuid.UUID(member_id))
        await self._run(go)

    async def members(self, movement_id: str) -> List[dict]:
        async def go(c):
            return [_row(r) for r in await c.fetch(_MEMBER_Q + "where gm.movement_id = $1 order by gm.created_at, p.name", uuid.UUID(movement_id))]
        return await self._run(go)

    async def members_by_phone(self, number: str) -> List[dict]:
        async def go(c):
            return [_row(r) for r in await c.fetch(_MEMBER_Q + "where p.phone = $1", number)]
        return await self._run(go)

    async def trip_of(self, owner: str, member: dict, title: str) -> str:
        """The worker's ONE trip for this movement (made once, kept on their link)."""
        if member.get("trip_id"):
            return member["trip_id"]

        async def go(c):
            tid = await c.fetchval("insert into trips (owner_id, title, status, depart_date, return_date) values ($1,$2,'draft',$3,$4) returning id",
                                   uuid.UUID(owner), title[:200], _d(member.get("out_date")), _d(member.get("back_date")))
            await c.execute("update group_members set trip_id = $2 where id = $1", uuid.UUID(member["id"]), tid)
            return str(tid)
        return await self._run(go)


class MemStore:
    """The same store in memory (tests and the offline proof)."""

    def __init__(self):
        self.movements: Dict[str, dict] = {}
        self.rows: Dict[str, List[dict]] = {}       # movement → its links {id, person_id, out_date, back_date, trip_id}
        self.groups: Dict[str, dict] = {}           # group → {id, owner_id, name}
        self.persons: Dict[str, dict] = {}          # person → {id, group_id, name, grade, home_airport, home_city, email, phone}

    def _group(self, owner, name, create=True):
        g = next((x for x in self.groups.values() if x["owner_id"] == owner and x["name"].lower() == str(name).lower()), None)
        if not g and create:
            g = {"id": str(uuid.uuid4()), "owner_id": owner, "name": name}
            self.groups[g["id"]] = g
        return g

    async def new_movement(self, owner, company, destination, starts_on, ends_on, hotel_area):
        g = self._group(owner, company)
        mid = str(uuid.uuid4())
        self._opened = getattr(self, "_opened", 0) + 1
        self.movements[mid] = {"id": mid, "owner_id": owner, "company": company, "group_id": g["id"], "destination": destination,
                               "starts_on": starts_on, "ends_on": ends_on, "hotel_area": hotel_area, "rules": {}, "opened": self._opened}
        self.rows[mid] = []
        return mid

    async def movement(self, owner, movement_id=None):
        ms = sorted((m for m in self.movements.values() if m["owner_id"] == owner and (not movement_id or m["id"] == movement_id)),
                    key=lambda m: m["opened"])
        return dict(ms[-1]) if ms else None

    async def open(self, owner, movement_id):
        m = self.movements.get(movement_id)
        if not m or m["owner_id"] != owner:
            return False
        self._opened += 1
        m["opened"] = self._opened
        return True

    async def trips(self, owner):
        ms = sorted((m for m in self.movements.values() if m["owner_id"] == owner), key=lambda m: -m["opened"])
        return [{k: m.get(k) for k in ("id", "company", "destination", "starts_on", "ends_on")} | {"people": len(self.rows[m["id"]])} for m in ms]

    async def set_rules(self, owner, movement_id, rules):
        self.movements[movement_id]["rules"] = json.loads(json.dumps(rules))

    async def company(self, owner, name=None, create=False):
        if name:
            g = self._group(owner, name, create)
            return dict(g) if g else None
        ms = sorted((m for m in self.movements.values() if m["owner_id"] == owner), key=lambda m: m["opened"])
        if ms:
            return dict(self.groups[ms[-1]["group_id"]])
        gs = [g for g in self.groups.values() if g["owner_id"] == owner]
        return dict(gs[-1]) if gs else None

    async def people(self, group_id):
        return sorted((dict(p) for p in self.persons.values() if p["group_id"] == group_id), key=lambda p: p["name"])

    async def add_person(self, group_id, person):
        pid = str(uuid.uuid4())
        self.persons[pid] = {"id": pid, "group_id": group_id, **{k: person.get(k) for k in PERSON}}
        return pid

    async def update_person(self, group_id, person_id, fields):
        p = self.persons.get(person_id)
        if not p or p["group_id"] != group_id:
            return None
        p.update({k: v for k, v in fields.items() if k in PERSON})
        return dict(p)

    async def select(self, movement_id, person_ids, out_date=None, back_date=None):
        mv, n = self.movements[movement_id], 0
        for pid in person_ids:
            p = self.persons.get(pid)
            if not p or p["group_id"] != mv["group_id"] or any(x["person_id"] == pid for x in self.rows[movement_id]):
                continue
            self.rows[movement_id].append({"id": str(uuid.uuid4()), "movement_id": movement_id, "person_id": pid, "trip_id": None,
                                           "out_date": out_date or mv["starts_on"], "back_date": back_date or mv["ends_on"]})
            n += 1
        return n

    async def remove_member(self, movement_id, member_id):
        self.rows[movement_id] = [x for x in self.rows[movement_id] if x["id"] != member_id]

    def _joined(self, link):
        p = self.persons[link["person_id"]]
        return {**link, **{k: p.get(k) for k in PERSON}}

    async def members(self, movement_id):
        return [self._joined(x) for x in self.rows[movement_id]]

    async def members_by_phone(self, number):
        return [self._joined(x) for rows in self.rows.values() for x in rows if self.persons[x["person_id"]].get("phone") == number]

    async def trip_of(self, owner, member, title):
        row = next(x for rows in self.rows.values() for x in rows if x["id"] == member["id"])
        if not row.get("trip_id"):
            row["trip_id"] = str(uuid.uuid4())
        return row["trip_id"]


def _d(v):
    if not v or isinstance(v, date):
        return v
    return date.fromisoformat(str(v)[:10])


def _row(r) -> dict:
    d = dict(r)
    for k, v in list(d.items()):
        if isinstance(v, uuid.UUID):
            d[k] = str(v)
        elif isinstance(v, (date, datetime)):
            d[k] = v.isoformat()[:10] if isinstance(v, date) and not isinstance(v, datetime) else v.isoformat()
        elif k == "rules" and isinstance(v, str):
            d[k] = json.loads(v)
    return d


STORE: Any = None


def store():
    global STORE
    if STORE is None:
        from . import plan_store as PS
        run = PS._run()
        if run is None:
            raise RuntimeError("no database")
        STORE = PgStore(run)
    return STORE


# ── 3 · the group's rules: THE ONE PLACE (group_movements.rules) ──────────────────────────────────────────────────────────────

LIMIT_KEYS = ("flight_return_eur", "hotel_night_eur")


def limit_for(rules: dict, member: dict) -> Dict[str, float]:
    """The member's limits: their own (by_member), else their grade's (by_grade) — key by key. {} when none is set."""
    lim = (rules or {}).get("limits") or {}
    out = dict(((lim.get("by_grade") or {}).get(str(member.get("grade") or "").lower())) or {})
    out.update(((lim.get("by_member") or {}).get(str(member.get("id")))) or {})
    return {k: float(v) for k, v in out.items() if k in LIMIT_KEYS and v is not None}


def with_limits(rules: dict, by_grade: Optional[dict] = None, by_member: Optional[dict] = None) -> dict:
    lim = {**((rules or {}).get("limits") or {})}
    for key, add in (("by_grade", by_grade), ("by_member", by_member)):
        if add:
            cur = {**(lim.get(key) or {})}
            for who, vals in add.items():
                k = str(who).lower() if key == "by_grade" else str(who)
                cur[k] = {**(cur.get(k) or {}), **{x: float(y) for x, y in vals.items() if x in LIMIT_KEYS and y is not None}}
            lim[key] = cur
    return {**(rules or {}), "limits": lim}


# ── 4 · planning, one by one (booking is CR 163) ──────────────────────────────────────────────────────────────────────────────

async def _quote(member: dict, movement: dict) -> Dict[str, Any]:
    """The worker's cheapest flight out and back (Duffel TEST) and the cheapest hotel near the area (an ESTIMATE per night)."""
    from . import travel as T
    home = member.get("home_airport") or member["home_city"]   # Sasha 351 · their home AIRPORT when the roster has it, else their city
    out = await T.search(home, movement["destination"], member["out_date"], limit=1)
    back = await T.search(movement["destination"], home, member["back_date"], limit=1)
    hotel = None
    try:
        from app.services.world_itinerary import hotels_in
        hs = await hotels_in(movement.get("owner_id") or "", movement.get("hotel_area") or movement["destination"], "Spain", "ES", "", strict=True)
        hotel = min(hs, key=lambda h: h.get("est_eur") or 1e9) if hs else None
    except Exception as e:
        log.warning("[groups] hotels not read: %s", type(e).__name__)
    return {"flights": [x["cards"][0] for x in (out, back) if x.get("cards")],
            "why": next((x["why"] for x in (out, back) if x.get("why")), None),
            "hotel": {"name": hotel["name"], "eur_per_night": hotel.get("est_eur"), "address": hotel.get("address")} if hotel else None}


QUOTE = _quote   # tests replace it


def flight_row(c: dict) -> dict:
    """A flight card (travel.card_of) as a row of the worker's trip (trip_basket_items), in euros (basket.ingest_flight's one rate)."""
    from . import basket as BK
    row = {"provider": "duffel", "provider_ref": c.get("id"), "day": str(c.get("departs") or "")[:10] or None, "starts_at": c.get("departs"),
           "ends_at": c.get("arrives"), "party": 1, "price_amount": float(c["amount"]) if c.get("amount") is not None else None,
           "price_currency": c.get("currency") or "EUR", "price_source": "quoted", "expires_at": c.get("expires_at"),
           "slice_key": f"{c.get('from')}-{c.get('to')} {str(c.get('departs') or '')[:10]}", "snapshot": dict(c)}
    return BK.ingest_flight(row) or row


async def _write(account: str, trip_id: str, member: dict, q: dict, lim: dict) -> None:
    """The plan on the worker's ONE trip: trip_basket_items, as any trip holds what was found (suggested — never booked here). A row over
    the worker's limit carries over_limit on its own snapshot (the master list reads it there)."""
    from . import basket as BK
    fl = [flight_row(c) for c in q.get("flights") or []]
    total = round(sum(float(r["price_amount"] or 0) for r in fl), 2) if fl else None
    over_f = bool(lim.get("flight_return_eur") is not None and total is not None and total > lim["flight_return_eur"])
    for r in fl:
        if over_f:
            r["snapshot"] = {**r["snapshot"], "over_limit": True, "limit_eur": lim["flight_return_eur"], "return_eur": total}
        await BK.suggest(account, trip_id, "flight", [r], slice_key=r["slice_key"], replace=True)
    h = q.get("hotel")
    if h:
        nights = (_d(member["back_date"]) - _d(member["out_date"])).days if member.get("back_date") and member.get("out_date") else 1
        per = float(h["eur_per_night"]) if h.get("eur_per_night") is not None else None
        over_h = bool(lim.get("hotel_night_eur") is not None and per is not None and per > lim["hotel_night_eur"])
        await BK.suggest(account, trip_id, "stay", [{
            "provider": "estimate", "day": member.get("out_date"), "party": 1, "price_source": "estimate",
            "price_amount": round(per * max(1, nights), 2) if per is not None else None, "price_currency": "EUR",
            "snapshot": {"name": h["name"], "address": h.get("address"), "nights": max(1, nights), "eur_per_night": per,
                         **({"over_limit": True, "limit_eur": lim["hotel_night_eur"]} if over_h else {})}}], slice_key=None, replace=True)


async def plan(account: str, movement_id: Optional[str] = None, only: Optional[List[str]] = None) -> Dict[str, Any]:
    """Sasha works through the list ONE BY ONE: each worker's trip gets their flights and hotel, within their limit (over → flagged on
    the trip's own rows, never booked). → {planned, failed: [{name, why}]}."""
    st = store()
    mv = await st.movement(account, movement_id)
    if not mv:
        return {"why": "there's no group movement yet — start one first"}
    done, failed = 0, []
    for m in await st.members(mv["id"]):
        if only and m["id"] not in only and m["name"] not in only:
            continue
        try:
            tid = await st.trip_of(account, m, f"{mv['company']} — {m['name']} to {mv['destination']}")
            q = await QUOTE(m, mv)
            if not q.get("flights") and not q.get("hotel"):
                failed.append({"name": m["name"], "why": q.get("why") or "nothing found"})
                continue
            await _write(account, tid, m, q, limit_for(mv.get("rules") or {}, m))
            done += 1
            if q.get("why"):
                failed.append({"name": m["name"], "why": q["why"]})
        except Exception as e:
            log.warning("[groups] %s not planned: %s", m["name"], type(e).__name__)
            failed.append({"name": m["name"], "why": type(e).__name__})
    return {"planned": done, "failed": failed, "movement_id": mv["id"]}


# ── 5 · THE MASTER LIST: a view over each worker's trip, read now ─────────────────────────────────────────────────────────────

ITEMS: Optional[Callable[[str, str], Awaitable[List[dict]]]] = None   # tests replace it (else basket.items)
VAULT: Optional[Callable[[dict], Awaitable[bool]]] = None             # tests replace it (else traveller_vault.has_passport — Sasha 333)


async def _items(account: str, trip_id: str) -> List[dict]:
    if ITEMS is not None:
        return await ITEMS(account, trip_id)
    from . import basket as BK
    return await BK.items(account, trip_id, ("suggested", "chosen", "pending_payment", "booked", "failed", "cancelled"))


async def _has_documents(member: dict) -> bool:
    """Sasha 333 · the member's passport is in THEIR vault (the Keep, under their member id) — known as ✓ / missing, never a number."""
    if VAULT is not None:
        return bool(await VAULT(member))
    from . import traveller_vault as TV
    return await TV.has_passport(member)


def status_of(rows: List[dict], lim: dict, documents: bool) -> str:
    live = [r for r in rows if r.get("state") != "superseded" and not (r.get("snapshot") or {}).get("superseded")]
    if not live:
        return "not planned"
    if all(r.get("state") == "cancelled" for r in live):
        return "cancelled"
    if all(r.get("state") == "booked" for r in live):
        return "booked"
    if any((r.get("snapshot") or {}).get("over_limit") for r in live):
        return "over limit"
    if any(r.get("kind") == "flight" for r in live) and not documents:
        return "needs vault"   # a flight needs the passport details; the vault (333) holds them
    return "planned"


def _transport(rows: List[dict]) -> Optional[str]:
    fl = [r for r in rows if r.get("kind") == "flight"]
    if not fl:
        return None
    return " · ".join(f"{(r.get('snapshot') or {}).get('owner') or 'Flight'} {(r.get('snapshot') or {}).get('from') or ''}→"
                      f"{(r.get('snapshot') or {}).get('to') or ''} {str(r.get('day') or '')[:10]}".strip() for r in fl)


async def _vault_marks(m: dict) -> Dict[str, Any]:
    """Sasha 333 · what the organiser sees of a member's vault: ✓ / missing and a programme's name — never a number."""
    if VAULT is not None:
        return {"vault": {"passport": bool(await VAULT(m)), "loyalty": []}}
    try:
        from . import traveller_vault as TV
        v = await TV.vault_view(m)
        return {"vault": {"passport": v["passport"], "loyalty": v["loyalty"]}}
    except Exception:
        return {"vault": {"passport": False, "loyalty": []}}


async def view(account: str, movement_id: Optional[str] = None) -> Dict[str, Any]:
    """THE MASTER LIST, computed from each worker's ONE trip as it is now — never stored."""
    st = store()
    mv = await st.movement(account, movement_id)
    if not mv:
        return {"rows": [], "why": "there's no group movement yet"}
    out = []
    members = await st.members(mv["id"])
    recorded: Dict[str, str] = {}
    booked_rec: Dict[str, Dict[str, Any]] = {}   # Sasha 340 · a booked worker's price and references, from AgAPI's record
    try:   # Sasha 339 (Tyler) · every read: AgAPI's ONE booking record first — the trips follow it, the status IS it
        from . import group_book as GB
        recorded = await GB.reconcile(account, members, booked=booked_rec)
    except Exception as e:
        log.warning("[groups] the list not reconciled with AgAPI's record: %s", type(e).__name__)
    from . import basket as BK
    for m in members:
        rows = [r for r in (await _items(account, m["trip_id"]) if m.get("trip_id") else []) if not BK.superseded(r)]
        if recorded.get(m["id"]) == "booked" and any(r.get("state") == "booked" for r in rows):
            rows = [r for r in rows if r.get("state") == "booked"]   # what was booked, not an older plan beside it
        lim = limit_for(mv.get("rules") or {}, m)
        fl = [r for r in rows if r.get("kind") == "flight"]
        stay = next((r for r in rows if r.get("kind") == "stay"), None)
        f_eur = round(sum(float(r.get("price_amount") or 0) for r in fl), 2) if fl else None
        h_eur = (stay.get("snapshot") or {}).get("eur_per_night") if stay else None
        price = round((f_eur or 0) + float((stay or {}).get("price_amount") or 0), 2) if (fl or stay) else None
        out.append({"member_id": m["id"], "person_id": m.get("person_id"), "name": m["name"], "grade": m.get("grade"),
                    "home_city": m.get("home_city"), "home_airport": m.get("home_airport"),
                    "out": m.get("out_date"), "back": m.get("back_date"), "trip_id": m.get("trip_id"),
                    "transport": _transport(rows), "hotel": (stay.get("snapshot") or {}).get("name") if stay else None,
                    "flight_eur": f_eur, "hotel_eur_per_night": h_eur, "price_eur": price, "limit": lim,
                    **(await _vault_marks(m)),
                    "status": recorded.get(m["id"]) or status_of(rows, lim, await _has_documents(m)),
                    **({"price_eur": booked_rec[m["id"]]["price_eur"], "references": booked_rec[m["id"]]["references"],
                        "transport": _transport(rows) or "Booked · " + " · ".join(booked_rec[m["id"]]["references"])}
                       if m["id"] in booked_rec else {})})
    counts = {s: sum(1 for r in out if r["status"] == s) for s in STATUSES if any(r["status"] == s for r in out)}
    return {"movement": {k: mv.get(k) for k in ("id", "company", "destination", "starts_on", "ends_on", "hotel_area")},
            "limits": (mv.get("rules") or {}).get("limits") or {}, "rows": out, "counts": counts}


def summary(v: Dict[str, Any], top: int = 25) -> str:
    """The master list in a few lines (WhatsApp)."""
    mv = v.get("movement") or {}
    if not v.get("rows"):
        return v.get("why") or "No one on the list yet."
    head = f"{mv.get('company')} → {mv.get('destination')}: {len(v['rows'])} people — " + ", ".join(f"{n} {s}" for s, n in v["counts"].items()) + "."
    lines = [f"• {r['name']} ({r.get('grade') or '—'}): {r['status']}" + (f" · €{r['price_eur']:.0f}" if r.get("price_eur") else "")
             for r in v["rows"][:top]]
    return "\n".join([head] + lines + ([f"…and {len(v['rows']) - top} more on the master list."] if len(v["rows"]) > top else []))


# ── the organiser's steps (the agent's tools and the S2 page call these) ──────────────────────────────────────────────────────

async def start(account: str, company: str, destination: str, starts_on: Optional[str], ends_on: Optional[str], hotel_area: Optional[str]) -> dict:
    """Sasha 345 · ONE movement per trip: the same company, destination and dates as their latest movement → THAT one (found live, 5 Nov:
    six "Jean Incorporated → London" movements in four minutes — the limits were set on one, the list read from another)."""
    last = await store().movement(account)
    same = lambda a, b: str(a or "").strip().lower()[:10] == str(b or "").strip().lower()[:10]
    if last and str(last.get("company") or "").strip().lower() == company.strip().lower() and same(last.get("destination"), destination) \
            and same(last.get("starts_on"), starts_on) and same(last.get("ends_on"), ends_on):
        return {"movement_id": last["id"], "reused": True}
    for t in await store().trips(account):   # Sasha 351 · the same trip, made before and not the open one → THAT one, opened again
        if str(t.get("company") or "").strip().lower() == company.strip().lower() and same(t.get("destination"), destination) \
                and same(t.get("starts_on"), starts_on) and same(t.get("ends_on"), ends_on):
            await store().open(account, t["id"])
            return {"movement_id": t["id"], "reused": True}
    mid = await store().new_movement(account, company.strip()[:200], destination.strip()[:120], starts_on, ends_on, (hotel_area or "").strip()[:200] or None)
    return {"movement_id": mid}


async def upload(account: str, rows: List[Dict[str, str]], movement_id: Optional[str] = None) -> Dict[str, Any]:
    """The list read → members added (or updated by name) → ONE batch question for every row that wasn't clear."""
    st = store()
    mv = await st.movement(account, movement_id)
    if not mv:
        return {"why": "there's no group movement yet — tell me the company, where, when and the hotel area first"}
    grades = list(((mv.get("rules") or {}).get("limits") or {}).get("by_grade") or {})
    good, unclear = members_from(rows, mv, grades)
    # Sasha 351 · the list's people are the company's ROSTER (each once, their vault theirs); this trip SELECTS them — nothing copied
    found, new, unclear2 = await _on_roster(st, mv["group_id"], good)
    n = 0
    for row, pid in found:
        n += await st.select(mv["id"], [pid], row.get("out_date"), row.get("back_date"))
    unclear += unclear2
    return {"added": n, "new_people": new, "unclear": unclear, "ask": batch_question(unclear), "movement_id": mv["id"]}


async def _on_roster(st, group_id: str, rows: List[dict]) -> Tuple[List[tuple], int, List[dict]]:
    """Sasha 351 · each row → the roster's person the organiser NAMES (their own name for them on their own list), its details updated
    with what this row gives; or a new person. Two people with that name → asked, never guessed. → ([(row, person_id)], new, unclear)."""
    roster = await st.people(group_id)
    found, unclear, new = [], [], 0
    for r in rows:
        same = [p for p in roster if p["name"].strip().lower() == r["name"].strip().lower()]
        fields = {k: r[k] for k in PERSON if r.get(k)}
        if len(same) > 1:
            unclear.append({"line": None, "row": {"name": r["name"]}, "why": [f"which {r['name']} — {len(same)} people on your roster have that name "
                                                                             "(tick the one on the People list)"]})
            continue
        if same:
            await st.update_person(group_id, same[0]["id"], {k: v for k, v in fields.items() if k != "name"})
            found.append((r, same[0]["id"]))
        else:
            pid = await st.add_person(group_id, fields)
            roster.append({"id": pid, **fields})
            found.append((r, pid))
            new += 1
    return found, new, unclear


# ── Sasha 351 · THE ROSTER: the company's people, each once — profiles, documents (their own vault), home airport ──────────────

async def roster(account: str) -> Dict[str, Any]:
    """The company's people (the organiser's latest company), each with their vault marks (✓ / missing, never a number)."""
    st = store()
    grp = await st.company(account)
    if not grp:
        return {"company": None, "people": [], "why": "no company yet — tell me its name, or start a trip for it"}
    people = []
    for p in await st.people(grp["id"]):
        people.append({**p, **(await _vault_marks({**p, "person_id": p["id"]}))})
    return {"company": {"id": grp["id"], "name": grp["name"]}, "people": people}


def _person_fields(f: Dict[str, Any]) -> Tuple[Dict[str, Any], List[str]]:
    """What a profile may hold, read as given — a field that can't be read is said (never stored half-right)."""
    out, bad = {}, []
    for k in PERSON:
        if k not in f:
            continue
        v = _norm(f.get(k)) or None
        if k == "home_airport" and v:
            v = v.upper()
            if not re.fullmatch(r"[A-Z]{3}", v):
                bad.append("the home airport (three letters, like MAD)"); continue
        if k == "email" and v:
            v = v.lower()
            if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[a-z]{2,}", v):
                bad.append("the email"); continue
        if k == "phone" and v:
            v = re.sub(r"[^\d+]", "", v)
            if not re.fullmatch(r"\+\d{8,15}", v):
                bad.append("the phone (with its country code, like +34…)"); continue
        if k == "grade" and v:
            v = v.lower()
        out[k] = v
    if "name" in out and (not out["name"] or len(out["name"]) < 2):
        bad.append("the name"); out.pop("name")
    return out, bad


async def add_people(account: str, rows: List[Dict[str, Any]], company: Optional[str] = None) -> Dict[str, Any]:
    """People onto the company's roster (from the People page, a pasted list, or the chat). Each row: name and at least a home city or
    airport; the same name as a roster person is THAT person (their profile updated) — two with that name: asked."""
    st = store()
    grp = await st.company(account, company, create=bool(company))
    if not grp:
        return {"why": "tell me the company's name first (\"my company is …\"), and I'll keep its people there"}
    good, unclear = [], []
    for i, r in enumerate(rows, 1):
        f, bad = _person_fields(r)
        if not f.get("name") or not (f.get("home_city") or f.get("home_airport")):
            bad = bad or ["a name, and a home city or airport"]
        if bad:
            unclear.append({"line": str(i), "row": {"name": r.get("name")}, "why": bad}); continue
        good.append(f)
    found, new, more = await _on_roster(st, grp["id"], good)
    unclear += more
    return {"company": grp["name"], "added": new, "updated": len(found) - new, "people": [pid for _, pid in found], "unclear": unclear,
            "ask": batch_question(unclear)}


async def edit_person(account: str, person_id: str, fields: Dict[str, Any]) -> Dict[str, Any]:
    st = store()
    grp = await st.company(account)
    if not grp:
        return {"why": "no company yet"}
    f, bad = _person_fields(fields)
    if bad:
        return {"why": "these couldn't be read: " + ", ".join(bad), "missing": bad}
    p = await st.update_person(grp["id"], person_id, f)
    return {"person": p} if p else {"why": "that person isn't on your roster"}


async def choose(account: str, who: List[str], movement_id: Optional[str] = None) -> Dict[str, Any]:
    """Sasha 351 · THE TICK: roster people (by id, or the name the organiser calls them) onto a trip — a link each, nothing copied."""
    st = store()
    mv = await st.movement(account, movement_id)
    if not mv:
        return {"why": "there's no trip yet — tell me where, when and the hotel area first"}
    roster_ = await st.people(mv["group_id"])
    ids, unknown, twice = [], [], []
    for w in who or []:
        w = str(w).strip()
        p = [x for x in roster_ if x["id"] == w] or [x for x in roster_ if x["name"].strip().lower() == w.lower()]
        if len(p) == 1:
            ids.append(p[0]["id"])
        elif p:
            twice.append(w)
        else:
            unknown.append(w)
    n = await st.select(mv["id"], ids)
    links = [m["id"] for m in await st.members(mv["id"]) if m["person_id"] in ids]
    return {"selected": n, "on_trip": len(links), "links": links, "unknown": unknown, "twice": twice, "movement_id": mv["id"]}


async def trips(account: str) -> Dict[str, Any]:
    """Sasha 351 · the organiser's trips (newest opened first) — the first is the OPEN one: everything on /group and in the chat is about it."""
    ts = await store().trips(account)
    return {"trips": [{**t, "open": i == 0} for i, t in enumerate(ts)]}


async def open_trip(account: str, which: str) -> Dict[str, Any]:
    """Open a trip by its id, or by its destination as the organiser says it ("Lisbon") — two trips there: asked, never guessed."""
    w = str(which or "").strip()
    ts = await store().trips(account)
    hit = [t for t in ts if t["id"] == w] or [t for t in ts if str(t.get("destination") or "").strip().lower() == w.lower()]
    if len(hit) != 1:
        return {"why": (f"Which {w} trip? " + "; ".join(f"{t['destination']} {str(t.get('starts_on') or '')[:10]}" for t in hit)) if hit
                else f"There's no {w} trip — your trips: " + (", ".join(t["destination"] for t in ts) or "none yet"), "trips": ts}
    await store().open(account, hit[0]["id"])
    return {"trip": hit[0]}


async def set_limits(account: str, by_grade: Optional[dict] = None, by_member: Optional[dict] = None, movement_id: Optional[str] = None) -> dict:
    st = store()
    mv = await st.movement(account, movement_id)
    if not mv:
        return {"why": "there's no group movement yet"}
    rules = with_limits(mv.get("rules") or {}, by_grade, by_member)
    await st.set_rules(account, mv["id"], rules)
    return {"limits": rules["limits"]}


def _eur(v: Any) -> str:
    v = float(v)
    return f"€{v:,.0f}" if v.is_integer() else f"€{v:,.2f}"


def _limit_words(l: Dict[str, Any]) -> str:
    parts = ([f"{_eur(l['hotel_night_eur'])} a night"] if l.get("hotel_night_eur") is not None else []) + \
            ([f"{_eur(l['flight_return_eur'])} for the return flight"] if l.get("flight_return_eur") is not None else [])
    return " and ".join(parts) or "no limit"


async def limits_said(account: str, movement_id: Optional[str] = None) -> Optional[str]:
    """Sasha 345 · the limits AS STORED, read back from group_movements.rules (the ONE place) — in euros, per grade and per person by name.
    Never the figures the request carried: what was saved is what she says."""
    st = store()
    mv = await st.movement(account, movement_id)
    if not mv:
        return None
    lim = (mv.get("rules") or {}).get("limits") or {}
    names = {m["id"]: m["name"] for m in await st.members(mv["id"])}
    said = [f"{g}: {_limit_words(v)}" for g, v in (lim.get("by_grade") or {}).items()]
    said += [f"{names.get(i, 'someone no longer on the list')}: {_limit_words(v)}" for i, v in (lim.get("by_member") or {}).items()]
    return "; ".join(said) if said else None


async def card(account: str, movement_id: Optional[str] = None) -> Dict[str, Any]:
    """Sasha 345 · THE MASTER LIST as a card (S2 and the chat): each row from the record (Sasha 340: AgAPI's for the booked), the link to
    /group, and — when nobody is planned yet — that, said plainly. Never "here's the list" without the list."""
    v = await view(account, movement_id)
    mv = v.get("movement") or {}
    rows = [{"name": r["name"], "grade": r.get("grade"), "status": r["status"], "price_eur": r.get("price_eur")} for r in v.get("rows") or []]
    planned = [r for r in rows if r["status"] not in ("not planned",)]
    if not mv:
        empty = "There's no group movement yet."
    elif not rows:
        empty = "Nobody is on this trip yet — name who's going, or tick them on the People list."   # Sasha 351 · chosen from the roster
    elif not planned:
        empty = f"Nobody is planned yet — {len(rows)} on the list, not planned."
    else:
        empty = None
    title = f"{mv.get('company')} → {mv.get('destination')}" if mv else "Group movement"
    counts = ", ".join(f"{n} {s}" for s, n in (v.get("counts") or {}).items())
    return {"title": title, "rows": rows, "counts": counts, "link": "/group", "empty": empty,
            "say": empty or f"The master list: {counts}. It's on the card, and the full list is on the Group page."}


__all__ = ["read_text", "read_csv", "read_xlsx", "read_photo", "members_from", "batch_question", "limit_for", "with_limits", "plan", "view",
           "summary", "start", "upload", "set_limits", "limits_said", "card", "status_of", "flight_row", "MemStore", "PgStore", "STATUSES"]
