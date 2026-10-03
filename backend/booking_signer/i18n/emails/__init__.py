"""CR 7 · venue EMAILS in 12 more languages: zh ja ko ar hi ru tr nl pl id sv (the other Bland languages) and vi.

Five emails each, the same five the six original languages have (emailing.py, render.py, cancel_routes.py, followup.py):
  request_table · request_generic · cancel · confirm (after a call's yes) · ask (could you confirm it in writing?)
Every one: the AI disclosure FIRST; on behalf of the guest by name; what / date / time / party; a polite request to
answer IN WRITING by replying (the reply-to header is Sasha's act-{id}@ address — emailing.act_address); signed by Sasha.

⚠ AI-WRITTEN, NOT NATIVE-REVIEWED. Each language file carries STATUS = "ai_unreviewed", an English back-translation of
every text, and a generated review sheet (docs/sasha/i18n/emails/{lang}-review.md: accept / fix per sentence).

⛔ THE GATE — `usable(lang, to)`: an unreviewed language is used ONLY for our own test addresses (SASHA_I18N_TEST_TO,
comma-separated, and the test venue's host). For a real venue nothing changes until a reviewer signs off: the email is
written in English, as today (Sasha 130: "said before the yes"). Sign-off is ONE LINE: in REVIEWED below, the
language's False becomes ("Reviewer Name", "YYYY-MM-DD").
"""
from __future__ import annotations

import importlib
import os
from typing import Callable, Dict, Optional, Tuple, Union

LANGS = ("zh", "ja", "ko", "ar", "hi", "ru", "tr", "nl", "pl", "id", "sv", "vi")
KINDS = ("request_table", "request_generic", "cancel", "confirm", "ask")

#: ⛔ the one-line sign-off per language: False → ("Reviewer Name", "YYYY-MM-DD"), after the review sheet is signed
REVIEWED: Dict[str, Union[bool, Tuple[str, str]]] = {
    "zh": False, "ja": False, "ko": False, "ar": False, "hi": False, "ru": False,
    "tr": False, "nl": False, "pl": False, "id": False, "sv": False, "vi": False,
}

TEST_VENUE_HOST = "sasha.test"   # the test venue's own pages and addresses (form_rung test venue)


def mod(lang: str):
    return importlib.import_module(f"{__name__}.{lang}")


def reviewed(lang: str) -> bool:
    r = REVIEWED.get(lang)
    return isinstance(r, tuple) and len(r) == 2 and all(isinstance(x, str) and x.strip() for x in r)


def test_addresses() -> set:
    return {a.strip().lower() for a in os.getenv("SASHA_I18N_TEST_TO", "").split(",") if a.strip()}


def is_test_address(to: str) -> bool:
    t = (to or "").strip().lower()
    return bool(t) and (t in test_addresses() or t.endswith("@" + TEST_VENUE_HOST) or t.endswith("." + TEST_VENUE_HOST))


def usable(lang: str, to: str) -> bool:
    """⛔ The gate. A language of ours, and either signed off by a native reviewer or going to OUR test address."""
    return lang in LANGS and (reviewed(lang) or is_test_address(to))


def count(lang: str, n: int) -> str:
    """'4 people' in that language — each file's own plural rule (ru/pl by the number's ending, ar by its form)."""
    return mod(lang).count(int(n))


def _fill(lang: str, kind: str, **v) -> Tuple[str, str]:
    m = mod(lang)
    subj, body = m.T[kind]
    v = {**v, "disclosure": m.DISCLOSURE}
    return subj.format(**v), body.format(**v)


def core(lang: str, *, what: Optional[str], d: str, t: str, n: int, name: str) -> str:
    """The booking, in one line, in THAT language — never assembled from English pieces."""
    m = mod(lang)
    s = m.CORE.format(what=what or m.TABLE, d=d, t=t, n=count(lang, n), name=name)
    return s[:1].upper() + s[1:]          # as followup.restatement: the line opens with a capital (no-op in CJK/ar/hi)


def request(lang: str, *, table: bool, what: Optional[str], d: str, t: str, n: int, name: str) -> Tuple[str, str]:
    """(subject, body) of a booking request. `what`: the activity as the venue would say it (generic only)."""
    kind = "request_table" if table else "request_generic"
    return _fill(lang, kind, who=name, guest_short=name, what=what or mod(lang).TABLE, d=d, t=t, n=count(lang, n))


def cancel(lang: str, *, core_text: str, name: str) -> Tuple[str, str]:
    return _fill(lang, "cancel", name=name, core=core_text)


def followup(kind: str, lang: str, *, core_text: str, name: str, me: str) -> Tuple[str, str]:
    if kind not in ("confirm", "ask"):
        raise ValueError(kind)
    return _fill(lang, kind, name=name, core=core_text, me=me, guest_short=name)


def back_translation(lang: str, kind: str) -> Tuple[str, str]:
    return mod(lang).BACK[kind]


# ── the hooks' helpers: each returns exactly the shape the code it stands in for returns ─────────────────────────────

def venue_lang(read) -> Optional[str]:
    """The venue's language by its country (venue_read.COUNTRIES — the Sasha tab's mapping), or None."""
    from booking_signer import venue_read as V
    c = (read or {}).get("country")
    return V.COUNTRIES[c][2] if c in V.COUNTRIES else None


def _particulars(o) -> dict:
    from booking_signer import render as R
    at = o["when"]["at"]
    what = None if R.is_table(o) else (o["what"].get("activity_venue_lang") or o["what"].get("activity"))
    return {"table": what is None, "what": what, "d": at[:10], "t": at[11:16], "n": int(o["how_many"]["count"]),
            "name": o["who"]["name"]}


def object_core(lang: str, o) -> str:
    x = _particulars(o)
    return core(lang, what=x["what"], d=x["d"], t=x["t"], n=x["n"], name=x["name"])


def _headers(venue_email: str, bcc: Optional[str], email_id: str) -> dict:
    from booking_signer import emailing as E
    h = {"from": E._env("SASHA_EMAIL_FROM"), "to": venue_email, "reply_to": E.act_address(email_id)}
    if bcc:
        h["bcc"] = bcc
    return h


def table_email(lang: str, venue_email: str, p, email_id: str) -> dict:
    """emailing.compose's email, in `lang` (p: emailing.EmailParticulars)."""
    subj, body = request(lang, table=True, what=None, d=p.on.isoformat(), t=p.at.strftime("%H:%M"), n=p.party, name=p.name)
    return {**_headers(venue_email, p.guest_email, email_id), "subject": subj, "text": body}


def object_email(lang: str, o, venue_email: str, email_id: str) -> dict:
    """render.email's email for a booking that isn't a table, in `lang`."""
    x = _particulars(o)
    guest = ((o["who"].get("contact") or {}).get("email") or "").lower() or None
    subj, body = request(lang, table=x["table"], what=x["what"], d=x["d"], t=x["t"], n=x["n"], name=x["name"])
    return {**_headers(venue_email, guest, email_id), "subject": subj, "text": body}


def followup_email(kind: str, lang: str, o, to: str, bcc: Optional[str], email_id: str, me: str,
                   own_ref: Optional[str] = None) -> dict:
    """followup.compose's email, in `lang`."""
    c = object_core(lang, o) + (f" (Ref. {own_ref})" if own_ref else "")
    subj, body = followup(kind, lang, core_text=c, name=o["who"]["name"], me=me)
    return {**_headers(to, bcc, email_id), "subject": subj + (f" · Ref. {own_ref}" if own_ref else ""), "text": body}


def cancel_texts(lang: str, o, name: str) -> Tuple[str, str]:
    """cancel_routes' (subject, text), in `lang`."""
    return cancel(lang, core_text=object_core(lang, o) if o.get("what") else name, name=name)


def read_back_line(lang: str, to: str) -> Optional[str]:
    """What the guest is told before the yes — never "in English" when it isn't (Sasha tab, CR 7 amendment 2)."""
    if not usable(lang, to):
        return None
    name = mod(lang).NAME
    if reviewed(lang):
        who, when = REVIEWED[lang]
        return f"I'll write in {name} (reviewed by {who}, {when})."
    return f"I'll write in {name} — an unreviewed draft, to our own test address only."


__all__ = ["LANGS", "KINDS", "REVIEWED", "usable", "reviewed", "is_test_address", "count", "core", "request", "cancel",
           "followup", "back_translation", "mod", "venue_lang", "object_core", "table_email",
           "object_email", "followup_email", "cancel_texts", "read_back_line"]
