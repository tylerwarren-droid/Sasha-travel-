"""The schools CampusMe can read, each from its OWN visit calendar.

Every entry was found by reading the school's page, never composed: Yale's widget ids are in its /portal/visit page
(AD docs/replies/2026-10-01-yale-portal-visit.html, L275–291); Penn's calendar is the /portal/campus-visit page
(read 3 Oct 2026, docs/campusme/reads/). `proven` means a live read of dates AND sessions succeeded here; anything
else is configured, unproven, and CampusMe says so instead of showing it.

Two Slate variants (docs/campusme/READS.md):
  · "widget":   /portal/widget/event?portal_id=…&part=…  cmd=event_dates (JSON) · cmd=event_list (HTML, spaces shown)
  · "register": <page>?cmd=getDates (JSON) · cmd=getEvents (HTML: one link per event) · the event's own form page
                (its sessions) · /register/form?cmd=counts (exceed "1" = full for that many attendees; no counts shown)
"""
from __future__ import annotations

import re
import unicodedata
from typing import Dict, List, Optional

SCHOOLS: Dict[str, dict] = {
    "yale": {
        "key": "yale", "name": "Yale", "full_name": "Yale University", "city": "New Haven, CT",
        "tz": "America/New_York", "host": "apps.admissions.yale.edu", "variant": "widget",
        "visit_page": "https://apps.admissions.yale.edu/portal/visit",
        "service": "/portal/widget/event?portal_id=bfe33c8d-b195-4ea8-b1a8-3237a37d5d78&part=53cf9c11-9729-42f4-9792-1e81e2a310f3",
        "aliases": ["yale", "yale university"],
        # the school's own words, quoted where a family needs them (read 3 Oct 2026)
        "rules": ["Registered students may have up to three guests join the tour.",
                  "If a day does not appear, tours are either not offered that day or registration has reached capacity."],
        "max_guests": 3, "proven": True,
    },
    "penn": {
        "key": "penn", "name": "Penn", "full_name": "University of Pennsylvania", "city": "Philadelphia, PA",
        "tz": "America/New_York", "host": "key.admissions.upenn.edu", "variant": "register",
        "visit_page": "https://key.admissions.upenn.edu/portal/campus-visit",
        "service": "/portal/campus-visit",
        "aliases": ["penn", "upenn", "u penn", "university of pennsylvania"],
        "rules": ["All prospective students (grades 9-12) should individually register for a visit.",
                  "Campus tours directly follow each information session; guests are encouraged to attend both."],
        "max_attendees": 5, "proven": True,
    },
    # Configured from AD's scout (P807on), NOT proven here: shown as "not read yet", never as sessions.
    "williams": {
        "key": "williams", "name": "Williams", "full_name": "Williams College", "city": "Williamstown, MA",
        "tz": "America/New_York", "host": "myadmission.williams.edu", "variant": "unproven",
        "visit_page": "https://myadmission.williams.edu/portal/visit", "aliases": ["williams", "williams college"],
        "rules": ["Walk-ins will be welcome, and tours will not have a registration cap."], "proven": False,
    },
    "pomona": {
        "key": "pomona", "name": "Pomona", "full_name": "Pomona College", "city": "Claremont, CA",
        "tz": "America/Los_Angeles", "host": "admissions.pomona.edu", "variant": "unproven",
        "visit_page": "https://admissions.pomona.edu/portal/visit-campus", "aliases": ["pomona", "pomona college"],
        "rules": ["Each registration may include one prospective student and a maximum of two guests."], "proven": False,
    },
}

# Named in AD's scout but not on Slate, or never readable (P807on L16–27): CampusMe says why, and reads nothing.
NOT_READABLE = {
    "harvard": "Harvard's visit page answered 503 when it was scouted, and its terms prohibit automated access — I'll prepare, you register",
    "amherst": "Amherst's robots file couldn't be read, so its pages stay unread",
    "berkeley": "Berkeley's tours run on its own system, not one CampusMe reads yet",
    "ohio state": "Ohio State's visit system isn't one CampusMe reads yet",
    "michigan": "Michigan isn't read by CampusMe yet",
    "ut austin": "UT Austin's visit page answered 503 when it was scouted",
}


def _fold(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s or "") if unicodedata.category(c) != "Mn").lower()


def find_schools(text: str) -> List[dict]:
    """The schools named in a message, in the order named. ("Yale and Penn" → [yale, penn])"""
    t = " " + re.sub(r"[^a-z0-9 ]", " ", _fold(text)) + " "
    hits = []
    for s in SCHOOLS.values():
        pos = [t.find(f" {a} ") for a in s["aliases"] if f" {a} " in t]
        if pos:
            hits.append((min(pos), s))
    return [s for _, s in sorted(hits, key=lambda h: h[0])]


def unreadable_named(text: str) -> List[str]:
    t = " " + re.sub(r"[^a-z0-9 ]", " ", _fold(text)) + " "
    return [why for name, why in NOT_READABLE.items() if f" {name} " in t]


def school(key: str) -> Optional[dict]:
    return SCHOOLS.get(key)
