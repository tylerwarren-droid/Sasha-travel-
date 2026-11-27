"""Sasha 423 · FP-4 · NO REFUNDABILITY WITHOUT A FACT (KANOE 26 Nov 11:08: "anything shown about a booking the person is making or has
made reads only from facts.answer"; HAZARD: ItineraryItem.is_refundable defaulted to TRUE and drew a "Refundable" badge).

THE RATCHET: Sasha holds no FIELD of its own about a booking's terms — refundability, a cancellation policy, a cancel/refund deadline or
fee. Such a field, stored or defaulted, is a second copy of what AgAPI's fine-print record (fine_print_facts, read through facts.answer)
governs, and a default asserts a fact nobody read. Any one of these fails the suite:
  · a Python class attribute            `is_refundable: bool = True`
  · a Python dict literal's key         `"cancellation_policy": "48 hours notice required"`
  · a TypeScript interface/type member  `is_refundable: boolean`
  · a SQL column that is still standing after every file in booking_signer/sql/ has run (created and not dropped)
A field NAME is a term field when it matches TERM_FIELD below. Words in sentences, a status ("cancelled"), an action ("booking_cancel",
"cancel_venue") and AgAPI's own response keys read in place (`c.get("refund")`) are not fields of Sasha's, and are not matched.
Its scope is the whole repo's code (backend, frontend), not a list of files: a new file is covered the day it lands. CTO drops overwrite
backend/app and frontend/app, so this is what catches the field coming back (CLAUDE.md, Stage B).
"""
from __future__ import annotations

import ast
import pathlib
import re
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
BACKEND, FRONTEND = ROOT / "backend", ROOT / "frontend"
SKIP_DIRS = {"node_modules", ".next", "venv", ".venv", "__pycache__", "kanoe_contract", ".vercel"}

#: refundable / non_refundable / is_refundable / refundable_until · cancellation, cancellation_policy · cancel_policy, cancel_until,
#: cancel_deadline, cancel_fee, cancel_terms, cancel_window · free_cancel, free_cancellation · refund_policy, refund_until, refund_deadline
TERM_FIELD = re.compile(r"(?i)^(?:is_|has_)?(?:non_?)?refundab\w*$|^cancellation(?:_(?:polic(?:y|ies)|terms?|until|deadline|fees?|window|rules?|charge))?$|^(?:free_)?cancel(?:_\w*)?_?(?:polic(?:y|ies)|until|"
                        r"deadline|fee|fees|terms|window|charge)\w*$|^free_?cancel\w*$|^refund_?(?:polic(?:y|ies)|until|deadline)\w*$")


#: THE ONE NAMED DEBT (shrink-only). Sasha 301's venue terms: agapi/booking_terms.py composes a deposit / cancellation / no-show / time
#: limit, with a "by <date>" deadline, from the venue's own reply AT VIEW TIME (no store) — read by the Trip tab (itinerary.with_terms),
#: booking_fine_print (/s2, voice, WhatsApp) and the cancel_by reminder (proactive). It is a term about a booking not read through
#: facts.answer. Its writer is AgAPI's `venue_words` facts (FP-4 venue words), ON ICE with venue booking (KANOE 26 Nov 12:07); the
#: question of switching it off meanwhile is Tyler's (Sasha 423's report). When it reads facts.answer, this line goes.
KNOWN_DEBT = ("backend/agapi/booking_terms.py:19 cancellation",)

def _files(base: pathlib.Path, exts):
    for p in base.rglob("*"):
        if p.suffix in exts and p.is_file() and not (set(p.relative_to(ROOT).parts) & SKIP_DIRS) and "/tests/" not in str(p):
            yield p


def python_fields(src: str):
    """(line, name) of every class attribute and every dict literal string key in one module."""
    out = []
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.ClassDef):
            for b in node.body:
                if isinstance(b, ast.AnnAssign) and isinstance(b.target, ast.Name):
                    out.append((b.lineno, b.target.id))
                elif isinstance(b, ast.Assign):
                    out += [(b.lineno, t.id) for t in b.targets if isinstance(t, ast.Name)]
        elif isinstance(node, ast.Dict):
            out += [(k.lineno, k.value) for k in node.keys if isinstance(k, ast.Constant) and isinstance(k.value, str)]
    return out


_TS_MEMBER = re.compile(r"^\s*(?:readonly\s+)?['\"]?([A-Za-z_]\w*)['\"]?\??\s*:\s*[^=]", re.M)


def ts_fields(src: str):
    """(line, name) of every member inside an `interface X {…}` or `type X = {…}` block."""
    out = []
    for m in re.finditer(r"\b(?:interface\s+\w+[^{]*|type\s+\w+\s*=\s*)\{", src):
        depth, i = 1, m.end()
        while i < len(src) and depth:
            depth += {"{": 1, "}": -1}.get(src[i], 0)
            i += 1
        body = src[m.end():i]
        line0 = src.count("\n", 0, m.end()) + 1
        out += [(line0 + body.count("\n", 0, mm.start(1)), mm.group(1)) for mm in _TS_MEMBER.finditer(body)]
    return out


def sql_standing_columns(files):
    """{(table, column): file} still standing once every file has run in order: created / added, minus dropped."""
    standing = {}
    for f in sorted(files):
        s = re.sub(r"--[^\n]*", "", f.read_text())
        for t, body in re.findall(r"(?is)create\s+table\s+(?:if\s+not\s+exists\s+)?(?:public\.)?(\w+)\s*\((.*?)\);", s):
            depth, start = 0, 0
            for i, ch in enumerate(body + ","):
                depth += {"(": 1, ")": -1}.get(ch, 0)
                if ch == "," and depth == 0:
                    col = body[start:i].strip().split()
                    if col and col[0].lower() not in ("primary", "unique", "check", "constraint", "foreign", "exclude"):
                        standing[(t.lower(), col[0].strip('"').lower())] = f.name
                    start = i + 1
        for t, col in re.findall(r"(?is)alter\s+table\s+(?:if\s+exists\s+)?(?:only\s+)?(?:public\.)?(\w+)\s+add\s+column\s+(?:if\s+not\s+exists\s+)?\"?(\w+)", s):
            standing[(t.lower(), col.lower())] = f.name
        for t, col in re.findall(r"(?is)alter\s+table\s+(?:if\s+exists\s+)?(?:only\s+)?(?:public\.)?(\w+)\s+drop\s+column\s+(?:if\s+exists\s+)?\"?(\w+)", s):
            standing.pop((t.lower(), col.lower()), None)
    return standing


def term_fields():
    hits = []
    for p in list(_files(BACKEND, {".py"})):
        try:
            fields = python_fields(p.read_text())
        except SyntaxError:
            continue
        hits += [f"{p.relative_to(ROOT)}:{n} {name}" for n, name in fields if TERM_FIELD.match(name)]
    for p in _files(FRONTEND, {".ts", ".tsx"}):
        hits += [f"{p.relative_to(ROOT)}:{n} {name}" for n, name in ts_fields(p.read_text()) if TERM_FIELD.match(name)]
    sql = list((BACKEND / "booking_signer" / "sql").glob("*.sql")) + list((BACKEND / "sql").glob("*.sql") if (BACKEND / "sql").is_dir() else [])
    hits += [f"sql {t}.{c} (from {f})" for (t, c), f in sql_standing_columns(sql).items() if TERM_FIELD.match(c)]
    return sorted(hits)



class NoTermWithoutAFact(unittest.TestCase):
    def test_the_name_rule_catches_the_class_and_nothing_else(self):
        for name in ("is_refundable", "refundable", "non_refundable", "refundable_until", "cancellation_policy", "cancellation",
                     "cancel_policy", "cancel_until", "cancel_deadline", "free_cancellation", "free_cancel", "refund_policy", "cancel_fee"):
            assert TERM_FIELD.match(name), name
        for name in ("cancelled", "cancelled_at", "booking_cancel", "cancel_venue", "cancel_by", "status", "refund", "refunded",
                     "refund_due", "can_cancel", "cancellation_id"):
            assert not TERM_FIELD.match(name), name


    def test_each_reader_sees_a_field(self):
        assert ("is_refundable" in dict((n, l) for l, n in python_fields("class A:\n    is_refundable: bool = True\n")))
        assert [n for _, n in python_fields('X = {"cancellation_policy": "48 hours"}')] == ["cancellation_policy"]
        assert [n for _, n in ts_fields("export interface I {\n  id?: string\n  is_refundable: boolean\n}")] == ["id", "is_refundable"]


    def test_a_dropped_column_is_not_standing(self):
        tmp_path = pathlib.Path(tempfile.mkdtemp())
        (tmp_path / "001_a.sql").write_text("create table t (\n  id uuid primary key,\n  refundable_until timestamptz,\n  n numeric(10, 2)\n);")
        assert ("t", "refundable_until") in sql_standing_columns(tmp_path.glob("*.sql"))
        (tmp_path / "002_b.sql").write_text("alter table t drop column if exists refundable_until;")
        assert ("t", "refundable_until") not in sql_standing_columns(tmp_path.glob("*.sql"))


    def test_sasha_holds_no_term_field_of_its_own(self):
        """THE RATCHET. A term about a booking is AgAPI's fact (facts.answer) or it is not said; Sasha never stores or defaults one.
        KNOWN_DEBT may only shrink: a new hit fails, and so does a debt that has gone (delete its line)."""
        found = term_fields()
        new = [h for h in found if h not in KNOWN_DEBT]
        gone = [h for h in KNOWN_DEBT if h not in found]
        assert new == [], "Sasha holds a booking-terms field of its own (Sasha 423): " + "; ".join(new)
        assert gone == [], "a Sasha 423 debt is paid — delete its line from KNOWN_DEBT: " + "; ".join(gone)


    def test_no_screen_draws_refundable_from_sasha(self):
        """No component says "Refundable" / "Non-refundable" / "Free cancellation" from a field of Sasha's: those words appear only where a
        fact's own words are drawn (none today: the facts.answer reader arrives with the contract, Sasha 420 / CR 235)."""
        bad = [f"{p.relative_to(ROOT)}" for p in _files(FRONTEND, {".tsx", ".ts"})
               if re.search(r"['\"`>]\s*(?:Non-)?[Rr]efundable\s*['\"`<]|\bis_refundable\b", p.read_text())]
        assert bad == [], bad


if __name__ == "__main__":
    unittest.main()
