"""Sasha 201 · DERIVE HER WORDS from the one source, docs/sasha/sasha-persona.md (the charter, rule 1).

    python3 scripts/derive_persona.py          writes the two derived files
    python3 scripts/derive_persona.py --check  exits 1 if either is stale (backend/tests/test_persona_derived.py runs this)

Writes, each stamped with the persona's sha256 and "GENERATED — do not edit":
    backend/app/services/persona.py    the guided script's lines, the quiver, the server prompts' voice rules, the
                                       watchdog's forbidden words
    frontend/lib/avatar-context.mjs    the LiveAvatar context: its opening text and prompt (checked live by
                                       backend/scripts/check_avatar_context.py, set by /api/heygen/context)
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SOURCE = os.path.join(ROOT, "docs", "sasha", "sasha-persona.md")
PY = os.path.join(ROOT, "backend", "app", "services", "persona.py")
MJS = os.path.join(ROOT, "frontend", "lib", "avatar-context.mjs")
CONTEXT_ID = "10b5933f-d54a-4305-9f88-333b628a1d09"   # the LiveAvatar context the token route opens


def load(path: str = SOURCE):
    raw = open(path, encoding="utf-8").read()
    m = re.search(r"```json\n(.*?)\n```", raw, re.S)
    if not m:
        raise SystemExit("sasha-persona.md has no ```json block")
    return json.loads(m[1]), hashlib.sha256(raw.encode()).hexdigest()


def avatar_prompt(p: dict) -> str:
    quiver = " · ".join(f"“{q}”" for q in p["quiver"])
    return "\n".join(line.replace("{QUIVER}", quiver) for line in p["avatar_prompt"])


def render_py(p: dict, sha: str) -> str:
    return f'''"""GENERATED from docs/sasha/sasha-persona.md (sha256 {sha}) by scripts/derive_persona.py — do not edit.
Sasha 201 · the charter, rule 1: her voice and script have ONE source; this file is derived from it."""

PERSONA_SHA256 = {sha!r}
AVATAR_OPENING = {p["avatar_opening"]!r}
QUIVER = {tuple(p["quiver"])!r}
AVATAR_PROMPT = {avatar_prompt(p)!r}
FORBIDDEN_AI = {tuple(p["forbidden_ai"])!r}
SERVER_VOICE_RULES = {(chr(10).join(p["server_voice_rules"]))!r}
LINES = {json.dumps(p["lines"], ensure_ascii=False, indent=4)}
'''


def render_mjs(p: dict, sha: str) -> str:
    return f'''// GENERATED from docs/sasha/sasha-persona.md (sha256 {sha}) by scripts/derive_persona.py — do not edit.
// Sasha 201 · the charter, rule 1: the LiveAvatar context (its opening and prompt) is derived from her one source. Applied
// and checked by app/api/heygen/context/route.ts; the token route opens CONTEXT_ID.
export const PERSONA_SHA256 = {json.dumps(sha)}
export const CONTEXT_ID = {json.dumps(CONTEXT_ID)}
export const OPENING_TEXT = {json.dumps(p["avatar_opening"], ensure_ascii=False)}
export const QUIVER = {json.dumps(p["quiver"], ensure_ascii=False)}
export const PROMPT = {json.dumps(avatar_prompt(p), ensure_ascii=False)}
'''


def main() -> int:
    p, sha = load()
    want = {PY: render_py(p, sha), MJS: render_mjs(p, sha)}
    if "--check" in sys.argv:
        stale = [os.path.relpath(f, ROOT) for f, t in want.items() if not os.path.exists(f) or open(f, encoding="utf-8").read() != t]
        print("persona: derived files are " + (f"STALE: {stale} — run scripts/derive_persona.py" if stale else "current"))
        return 1 if stale else 0
    for f, t in want.items():
        open(f, "w", encoding="utf-8").write(t)
        print("wrote", os.path.relpath(f, ROOT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
