"""CR 61 · SASHA'S AgAPI v1.0 CONFORMANCE (EU 03-conformance.md §5) — loads EU's FROZEN vector files where they live (never a copy) and
runs them against Sasha's own code:

    canonical.json      15   agapi.v1.canonical / sha256 (10 byte-exact + 5 refusals)
    explicit-yes.json   38   agapi.v0.explicit_yes(said, lang)  — Sasha's live yes, on the lists in approval-language.json
    approval.json       17   agapi.v1.decide — the first failing rule in Part 3 §3's order
    outage.json          7   agapi.v1.classify — an upstream failure is never "no results"

It also checks that Sasha's pinned agapi/spec/approval-language.json is byte-for-byte EU's frozen file. Prints "<file> <passed>/<total>"
and the sha256 of every file it ran on; exits 1 on any failure.

    cd backend && AGAPI_V1_DIR="<path to the AD repo>/docs/agapi/v1" python -m scripts.agapi_v1_conformance
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
DEFAULT = Path.home() / "Developer" / "Applied Diligence" / "docs" / "agapi" / "v1"


def main() -> int:
    root = Path(os.getenv("AGAPI_V1_DIR") or DEFAULT)
    vec = root / "vectors"
    if not (vec / "canonical.json").exists():
        print(f"✗ EU's frozen v1.0 files aren't at {root} — set AGAPI_V1_DIR", flush=True)
        return 2
    from agapi import v0, v1
    readme = (root / "README.md").read_text(encoding="utf-8") if (root / "README.md").exists() else ""
    print(f"AgAPI v1.1 conformance — Sasha (backend/agapi) against {root}" + ("  [README: v1.0 FINAL]" if "v1.0 FINAL" in readme else ""))
    results, fails = [], []

    def file(name):
        raw = (vec / f"{name}.json").read_bytes()
        d = json.loads(raw.decode("utf-8"))
        return d, hashlib.sha256(raw).hexdigest()

    # pinned language file == EU's
    eu_lang = (vec / "approval-language.json").read_bytes()
    pinned = v1.LANGUAGE_FILE.read_bytes()
    same = eu_lang == pinned
    results.append(("approval-language.json (pinned copy == frozen file)", int(same), 1, hashlib.sha256(eu_lang).hexdigest()))
    if not same:
        fails.append("approval-language.json: Sasha's pinned copy differs from EU's frozen file")
    eu_acts = (vec / "approval-language-acts.json").read_bytes()   # 1.1
    same = eu_acts == (v1.SPEC / "approval-language-acts.json").read_bytes()
    results.append(("approval-language-acts.json (pinned copy == 1.1 file)", int(same), 1, hashlib.sha256(eu_acts).hexdigest()))
    if not same:
        fails.append("approval-language-acts.json: Sasha's pinned copy differs from EU's 1.1 file")

    d, h = file("canonical")
    ok = 0
    for c in d["cases"]:
        try:
            if c.get("expect") == "refused":
                try:
                    v1.canonical(json.loads(c["input_json"]))
                    fails.append(f"canonical {c['id']}: accepted, must be refused")
                except v1.Refused:
                    ok += 1
            else:
                val = json.loads(c["input_json"]) if "input_json" in c else c["input"]
                if v1.canonical(val) == c["canonical"] and v1.sha256(val) == c["sha256"]:
                    ok += 1
                else:
                    fails.append(f"canonical {c['id']}: bytes or sha256 differ")
        except Exception as e:
            fails.append(f"canonical {c['id']}: {type(e).__name__}: {e}")
    results.append(("canonical.json", ok, len(d["cases"]), h))

    d, h = file("explicit-yes")
    ok = 0
    for c in d["cases"]:
        got = v0.explicit_yes(c["said"], c["lang"], c.get("act_kind"))   # 1.1: act_kind
        ok += got == c["explicit_yes"]
        if got != c["explicit_yes"]:
            fails.append(f"explicit-yes [{c['lang']}] {c['said']!r}: {got}, expected {c['explicit_yes']}")
    results.append(("explicit-yes.json", ok, len(d["cases"]), h))

    d, h = file("approval")
    ok = 0
    for c in d["cases"]:
        got, want = v1.decide(c), (c["expect"]["decision"], c["expect"]["void_reason"])
        ok += got == want
        if got != want:
            fails.append(f"approval {c['id']}: {got}, expected {want}")
    results.append(("approval.json", ok, len(d["cases"]), h))

    d, h = file("outage")
    ok = 0
    for c in d["cases"]:
        got, e = v1.classify(c["sources"]), c["expect"]
        good = (got[0] == "ok" and e["ok"] and got[1] == e["coverage"] and got[2] == e["item_count"]) or \
               (got[0] == "error" and not e["ok"] and got[1] == e["code"])
        ok += good
        if not good:
            fails.append(f"outage {c['id']}: {got}, expected {e}")
    results.append(("outage.json", ok, len(d["cases"]), h))

    for name, ok, total, h in results:
        print(f"  {'✓' if ok == total else '✗'} {name} {ok}/{total}   sha256:{h[:16]}…")
    for f in fails:
        print(f"    FAIL · {f}")
    passed = sum(r[1] for r in results[1:])
    total = sum(r[2] for r in results[1:])
    print(f"\nSasha AgAPI v1.1 conformance: {passed}/{total} vectors" + (" — PASS" if not fails else f" — FAIL ({len(fails)})"))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
