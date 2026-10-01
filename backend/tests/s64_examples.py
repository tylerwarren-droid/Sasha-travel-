"""S-64 §6 · the four worked examples as reservation/1 objects, rendered to EVERY channel (step 13's proof).
`render_all()` is what tests/test_s64_examples.py freezes in tests/fixtures/s64_examples_golden.json — run this file to
regenerate it after a DELIBERATE wording change, and review the diff:  python -m tests.s64_examples > /dev/null
"""
from __future__ import annotations

import json
import pathlib
from datetime import datetime, timezone

from booking_signer import calls as C, formfill as FF, render as R, reservation as RS

NOW = datetime(2026, 9, 30, 12, 0, tzinfo=timezone.utc)
ACCT = "00000000-0000-4000-8000-000000000001"
WHO = {"name": "Tyler Warren", "account_id": ACCT, "contact": {"email": "tyler@example.test", "mobile_e164": "+34608445715"}}
GOLDEN = pathlib.Path(__file__).parent / "fixtures" / "s64_examples_golden.json"

EXAMPLES = {
    # 6.1 La Contra, Madrid — lunch, a table, 4 people (es)
    "6.1_la_contra": ({"what": {"activity": "lunch", "activity_venue_lang": "una mesa para comer", "category": "restaurant"},
                       "where": {"venue_name": "La Contra", "timezone": "Europe/Madrid", "venue_ids": []},
                       "when": {"mode": "at", "at": "2026-10-02T13:00"}, "how_many": {"count": 4, "unit": "people"}, "flow": "book"},
                      "es", "ES", "+34910536740"),
    # 6.2 King Ink, Nairobi — quote first (en)…
    "6.2a_king_ink_quote": ({"what": {"activity": "a fine-line tattoo on the forearm, about 10 cm", "activity_venue_lang": "a fine-line tattoo on the forearm, about 10 cm",
                                      "category": "beauty", "spec": "fine-line, forearm, about 10 cm", "photos": ["asset:1", "asset:2"]},
                             "where": {"venue_name": "King Ink Tattoos", "timezone": "Africa/Nairobi", "venue_ids": []},
                             "when": {"mode": "venue_proposes"}, "how_many": {"count": 1, "unit": "pieces"}, "flow": "quote_first"},
                            "en", "KE", "+254725909800"),
    # …then the booking the guest chose: Thursday 15:00, one session
    "6.2b_king_ink_book": ({"what": {"activity": "a tattoo session", "activity_venue_lang": "a tattoo session", "category": "beauty"},
                            "where": {"venue_name": "King Ink Tattoos", "timezone": "Africa/Nairobi", "venue_ids": []},
                            "when": {"mode": "at", "at": "2026-10-08T15:00", "duration_min": 120}, "how_many": {"count": 1, "unit": "sessions"}, "flow": "book"},
                           "en", "KE", "+254725909800"),
    # 6.3 A Lisbon kayak tour, fixed start, 3 hours, 2 people (pt) — illustrative
    "6.3_lisbon_kayak": ({"what": {"activity": "a 3-hour kayak tour", "activity_venue_lang": "um passeio de caiaque", "category": "experience"},
                          "where": {"venue_name": "Kayak Lisboa", "timezone": "Europe/Lisbon", "venue_ids": []},
                          "when": {"mode": "at", "at": "2026-10-03T09:30", "fixed_start": True, "duration_min": 180},
                          "how_many": {"count": 2, "unit": "people"}, "flow": "book"},
                         "pt", "PT", "+351910000000"),
    # 6.4 A Madrid spa, a window, 60 minutes, 1 person (es) — illustrative
    "6.4_madrid_spa": ({"what": {"activity": "a 60-minute relaxing massage", "activity_venue_lang": "un masaje relajante", "category": "beauty",
                                 "service": "Masaje relajante 60 min"},
                        "where": {"venue_name": "Spa Madrid", "timezone": "Europe/Madrid", "venue_ids": []},
                        "when": {"mode": "window", "window": {"earliest": "2026-10-03T10:00", "latest": "2026-10-03T13:00"}, "duration_min": 60},
                        "how_many": {"count": 1, "unit": "people"}, "flow": "book"},
                       "es", "ES", "+34910000000"),
}
FORM = [{"name": "date", "role": "date", "required": True}, {"name": "time", "role": "time", "required": True},
        {"name": "party", "role": "party_size"}, {"name": "name", "role": "person_name", "required": True},
        {"name": "email", "role": "email", "required": True}, {"name": "notes", "role": "free_text"}, {"name": "terms", "role": "consent"}]


def obj(parts):
    return RS.validate({"schema": RS.SCHEMA, "who": WHO, **parts})


def _try(f):
    try:
        return f()
    except (RS.ReservationRefused, FF.Stop) as e:
        return {"refused": getattr(e, "rule", None), "why": str(e).split(": ", 1)[-1]}


def render_all() -> dict:
    out = {}
    for key, (parts, lang, country, number) in EXAMPLES.items():
        o = obj(parts)
        v = C.CallVenue(key=f"read:{key}", name=o["where"]["venue_name"], number_env="", language=lang,
                        timezone=o["where"]["timezone"], number=number, source="their Google listing")
        call = _try(lambda: R.call_for(o, v, NOW, number))
        out[key] = {
            "request_sha256": RS.sha256(o),
            "call": call if "refused" in call else {"first_sentence": call["brief"]["first_sentence"], "recap": call["brief"]["recap"],
                                                     "purpose": call["brief"]["purpose"], "read_back": call["read_back_lines"],
                                                     "task_chars": len(call["brief"]["task"])},
            "email": _try(lambda: {k: m for k, m in R.email(o, lang, "venue@example.test", "e-golden").items() if k in ("subject", "text")}),
            "whatsapp": _try(lambda: R.whatsapp(o, country)),
            "form": _try(lambda: FF.fill(o, FORM)),
        }
    return out


if __name__ == "__main__":
    GOLDEN.write_text(json.dumps(render_all(), ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {GOLDEN}")
