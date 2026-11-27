"""Sasha 424 · WHAT IS VENDORED, derived, never listed by hand: a directory under backend/ that carries its writer's own SHA256SUMS
(EU's agapi/spec/v1, AgAPI's agapi/booking_rules) is that writer's code, byte-identical and sum-checked — not Sasha's. Sasha's code
ratchets (hand-written contract copies, default passenger facts) scan Sasha's code, so they leave these out. A new vendored set is
covered the day it lands with its SHA256SUMS; a file a set's SUMS doesn't list is still scanned."""
from __future__ import annotations

import pathlib
from typing import List, Set

BACKEND = pathlib.Path(__file__).resolve().parents[1]


def dirs() -> List[pathlib.Path]:
    return sorted(p.parent for p in BACKEND.rglob("SHA256SUMS") if "node_modules" not in p.parts)


def files() -> Set[pathlib.Path]:
    out: Set[pathlib.Path] = set()
    for d in dirs():
        for line in (d / "SHA256SUMS").read_text().splitlines():
            if line.strip():
                out.add((d / line.split(None, 1)[1].strip().removeprefix("./")).resolve())
    return out


def excludes() -> List[str]:
    """kanoe_contract.ratchet's --exclude arguments: every file a vendored set's own SUMS lists."""
    return [a for f in sorted(files()) for a in ("--exclude", str(f))]
