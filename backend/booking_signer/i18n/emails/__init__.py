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


__all__ = ["LANGS", "KINDS", "REVIEWED", "usable", "reviewed", "is_test_address", "count", "core", "request", "cancel",
           "followup", "back_translation", "mod"]
