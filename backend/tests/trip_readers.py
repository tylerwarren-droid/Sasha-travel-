"""Sasha 403 · the ONE detector of trip readers (tests/test_s403_one_trip_reader and test_s398 use it): what in a module ASSEMBLES a trip
or PICKS which trip is meant — by CALL and by SQL (398's ratchet saw calls only, so journeys' own SQL over trips was invisible)."""
from __future__ import annotations

import pathlib
import re
from typing import Dict, List

BACKEND = pathlib.Path(__file__).resolve().parents[1]
DIRS = ("agapi", "app", "booking_signer", "products")
#: the ONE reader
READER = "booking_signer/trip_record.py"
#: T's own writers / stores — they hold its rows (assembling is theirs); never a PICK
WRITERS = {"booking_signer/plan_store.py", "booking_signer/basket.py", "booking_signer/groups.py"}
#: named, with the reason: not "which trip is meant"
NOT_A_TRIP_PICK = {
    ("booking_signer/groups.py", "company_limits"): "a company's limits as it LAST SET them, on any of its trips — a company setting",
    ("booking_signer/plan_store.py", "latest"): "the store's own newest-touched read: trip_record.plan_now is its ONLY caller (any other "
                                                "PS.latest call is a pick, below)",
}
CALL_READS = re.compile(r"\b(?:BK|basket)\.(?:items|live)\(|\b(?:PS|plan_store)\.(?:latest|by_id|plans)\(")
CALL_PICKS = re.compile(r"\b(?:PS|plan_store)\.latest\(")   # groups.movement(owner) with no id asks trip_record (asserted in the test)
TRIP_FROM = re.compile(r"\bfrom\s+(trips|group_movements)\b(?:\s+\w+)?", re.I)
CONTENT = re.compile(r"\b(?:\w+\.)?(title|destinations|depart_date|return_date|starts_on|ends_on|destination)\b")


def _sql(src: str) -> List[str]:
    """Every SQL string, adjacent literals joined."""
    out = []
    for m in re.finditer(r'"(?:[^"\\\n]|\\.)*"(?:\s*(?:\n\s*)?"(?:[^"\\\n]|\\.)*")*', src):
        s = re.sub(r'"\s*(?:\n\s*)?"', "", m.group(0))
        if re.search(r"\bselect\b", s, re.I):
            out.append(s)
    return out


def _funcs(src: str):
    """(function name, its body) — the module's top level counted as one."""
    parts = re.split(r"\n(?=(?:    )?(?:async )?def \w+)", src)   # module functions and class methods: a nested `go` is its function's
    for p in parts:
        m = re.match(r"(?:    )?(?:async )?def (\w+)", p)
        yield (m.group(1) if m else "<module>"), p


def findings(rel: str, src: str) -> Dict[str, List[str]]:
    """{"pick": […], "assemble": […]} — what this module does that only trip_record may."""
    out: Dict[str, List[str]] = {"pick": [], "assemble": []}
    if rel == READER:
        return out
    for name, body in _funcs(src):
        code = "\n".join(l.split("#", 1)[0] for l in body.splitlines())
        for s in _sql(code):
            first = re.search(r"\bfrom\s+(\w+)", s, re.I)
            on_trip = bool(first and first.group(1).lower() in ("trips", "group_movements"))
            if on_trip and re.search(r"order\s+by[^\"]*limit\s+1\b", s, re.I) and (rel, name) not in NOT_A_TRIP_PICK:
                out["pick"].append(f"{name}: {s[:90]}")
            sel = s[:s.lower().find(" from ")] if " from " in s.lower() else s
            if rel not in WRITERS and (on_trip or TRIP_FROM.search(s)) and CONTENT.search(sel) and \
                    (on_trip or re.search(r"\bt\.(title|destinations|depart_date|return_date)\b", sel)):
                out["assemble"].append(f"{name}: {s[:90]}")
        if CALL_PICKS.search(code):
            out["pick"].append(f"{name}: {CALL_PICKS.search(code).group(0)}")
        if rel not in WRITERS and CALL_READS.search(code):
            out["assemble"].append(f"{name}: {CALL_READS.search(code).group(0)}")
    return out


def readers() -> Dict[str, Dict[str, List[str]]]:
    hits = {}
    for d in DIRS:
        for p in sorted((BACKEND / d).rglob("*.py")):
            rel = p.relative_to(BACKEND).as_posix()
            f = findings(rel, p.read_text())
            if f["pick"] or f["assemble"]:
                hits[rel] = f
    return hits
