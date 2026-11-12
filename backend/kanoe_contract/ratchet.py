"""GENERATED from AgAPI's spec/ by tools/contract/generate.py (CR 186) — DO NOT EDIT. Change spec/, regenerate, bump the release.
THE RATCHET for a Python repo (Sasha): fails on any HAND-WRITTEN copy of the contract — an AgAPI operation name or an AgAPI error code
written as a string instead of kanoe_contract.OP / ERR. An operation name counts anywhere. An error code counts where it is the contract's:
compared with something named `code` (== / != / in), or in a collection made only of AgAPI's error codes (RESEND = ("…", "…")).
A generated file (its first lines say DO NOT EDIT) is not a hand-written copy.

    python3 -m kanoe_contract.ratchet backend/ [--exclude path ...]   → exit 1, with file:line for each copy
"""
from __future__ import annotations

import ast
import pathlib
import sys

from . import ERROR_CODES, OPERATIONS


def _names_code(node) -> bool:
    return any(isinstance(n, ast.Name) and "code" in n.id.lower() or isinstance(n, ast.Attribute) and "code" in n.attr.lower()
               or isinstance(n, ast.Constant) and n.value == "code" for n in ast.walk(node))


def _copies(path: pathlib.Path):
    src = path.read_text(errors="replace")
    if "DO NOT EDIT" in src[:600]:
        return
    try:
        tree = ast.parse(src, str(path))
    except SyntaxError:
        return
    for n in ast.walk(tree):
        if isinstance(n, ast.Constant) and isinstance(n.value, str) and n.value in OPERATIONS:
            yield n.lineno, "operation", n.value
        elif isinstance(n, ast.Compare):
            sides = [n.left] + list(n.comparators)
            for s in sides:
                if isinstance(s, ast.Constant) and s.value in ERROR_CODES and any(_names_code(o) for o in sides if o is not s):
                    yield s.lineno, "error code", s.value
                elif isinstance(s, (ast.Tuple, ast.List, ast.Set)) and any(_names_code(o) for o in sides if o is not s):
                    for e in s.elts:
                        if isinstance(e, ast.Constant) and e.value in ERROR_CODES:
                            yield e.lineno, "error code", e.value
        elif isinstance(n, (ast.Tuple, ast.List, ast.Set)) and n.elts and all(isinstance(e, ast.Constant) and e.value in ERROR_CODES for e in n.elts):
            for e in n.elts:
                yield e.lineno, "error code", e.value


def main(argv) -> int:
    roots, skip = [], []
    it = iter(argv)
    for a in it:
        if a == "--exclude":
            skip.append(pathlib.Path(next(it)).resolve())
        else:
            roots.append(pathlib.Path(a))
    bad = 0
    for root in roots or [pathlib.Path(".")]:
        for f in sorted(root.rglob("*.py")):
            r = f.resolve()
            if "kanoe_contract" in r.parts or any(r == s or s in r.parents for s in skip):
                continue
            for line, what, v in sorted(set(_copies(f))):
                print(f"{f}:{line}: a hand-written {what} {v!r} — use kanoe_contract")
                bad += 1
    print(f"kanoe-contract ratchet: {bad} hand-written cop{'y' if bad == 1 else 'ies'}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
