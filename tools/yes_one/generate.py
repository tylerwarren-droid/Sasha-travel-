#!/usr/bin/env python3
"""CR 76 · generate THE ONE YES RULE from the AgAPI contract — one module, two languages, one conformance set.

    python3 tools/yes_one/generate.py [--contract <dir with operations.json + vectors/>]

Default contract: EU's published AgAPI contract in the AD repo (docs/agapi/v1). The contract files used are snapshotted under
tools/yes_one/contract/ (byte for byte), and everything in tools/yes_one/dist/ is generated — never edited by hand:
  yes_one.py          the module (stdlib only) — vendored into AgAPI and Sasha (S2)
  yes_one.ts          the same rules for AD (Node, no dependencies)
  conformance.json    ONE test set: the contract's approval / explicit-yes / canonical / idempotency vectors + the flow cases
  test_yes_one.py     the conformance runner for the Python module (runs next to yes_one.py)
  yes_one.test.ts     the conformance runner for the TypeScript module (node:test)
  MANIFEST.json       the contract version, each source file's sha256, each output's sha256 (the "module sha")"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT = Path("/Users/tylerwarren/Developer/Applied Diligence/docs/agapi/v1")
FILES = ["operations.json", "vectors/approval-language.json", "vectors/approval-language-acts.json", "vectors/approval.json",
         "vectors/explicit-yes.json", "vectors/canonical.json", "vectors/idempotency.json"]

# the flow every runtime walks: read-back (turn 1) → the person's words (a later turn) → the act (re-derived now)
FLOW = [
    {"id": "F-1", "says": "a yes in a later turn, the same payload → valid", "said": "Yes, book it.", "approved_turn": "t2", "approved_at": "2026-10-10T10:02:00Z",
     "act_at": "2026-10-10T10:03:00Z", "expect": ["valid", None]},
    {"id": "F-2", "says": "the yes in the SAME turn as the read-back → approval_same_turn", "said": "Yes, book it.", "approved_turn": "t1",
     "approved_at": "2026-10-10T10:00:30Z", "act_at": "2026-10-10T10:01:00Z", "expect": ["approval_same_turn", None]},
    {"id": "F-3", "says": "a question is not a yes", "said": "Yes, but what's the refund?", "approved_turn": "t2", "approved_at": "2026-10-10T10:02:00Z",
     "act_at": "2026-10-10T10:03:00Z", "expect": ["no_explicit_yes", None]},
    {"id": "F-4", "says": "the price changed after the yes → void", "said": "Yes, book it.", "approved_turn": "t2", "approved_at": "2026-10-10T10:02:00Z",
     "act_at": "2026-10-10T10:03:00Z", "act_payload": {"total_minor": 99000, "currency": "EUR", "offer": "off_1"}, "expect": ["approval_void", "payload_changed"]},
    {"id": "F-5", "says": "'Yes, cancel it' approves a cancellation", "operation": "trip.cancel", "said": "Yes, cancel it.", "approved_turn": "t2",
     "approved_at": "2026-10-10T10:02:00Z", "act_at": "2026-10-10T10:03:00Z", "expect": ["valid", None]},
    {"id": "F-6", "says": "… but never a booking", "said": "Yes, cancel it.", "approved_turn": "t2", "approved_at": "2026-10-10T10:02:00Z",
     "act_at": "2026-10-10T10:03:00Z", "expect": ["no_explicit_yes", None]},
    {"id": "F-7", "says": "the act 16 minutes after the yes → expired", "said": "Yes, book it.", "approved_turn": "t2", "approved_at": "2026-10-10T10:02:00Z",
     "act_at": "2026-10-10T10:18:30Z", "expect": ["approval_expired", None]},
    {"id": "F-8", "says": "a Spanish yes with no language given", "said": "Sí, adelante.", "lang": None, "approved_turn": "t2", "approved_at": "2026-10-10T10:02:00Z",
     "act_at": "2026-10-10T10:03:00Z", "expect": ["valid", None]},
    {"id": "F-9", "says": "someone else's yes → untrusted", "said": "Yes, book it.", "approved_by": "usr_other", "approved_turn": "t2",
     "approved_at": "2026-10-10T10:02:00Z", "act_at": "2026-10-10T10:03:00Z", "expect": ["approval_untrusted_origin", None]},
    {"id": "F-10", "says": "a used approval → consumed", "said": "Yes, book it.", "consumed": True, "approved_turn": "t2", "approved_at": "2026-10-10T10:02:00Z",
     "act_at": "2026-10-10T10:03:00Z", "expect": ["approval_consumed", None]},
    {"id": "F-11", "says": "a tap on the person's own link (no words) → valid", "said": None, "channel": "link", "approved_turn": "t2",
     "approved_at": "2026-10-10T10:02:00Z", "act_at": "2026-10-10T10:03:00Z", "expect": ["valid", None]},
    {"id": "F-12", "says": "an email read-back: the wording changed after the yes → void", "operation": "messages.send_email", "said": "Yes, send it.",
     "approved_turn": "t2", "approved_at": "2026-10-10T10:02:00Z", "act_at": "2026-10-10T10:03:00Z", "act_lines": ["Email jon@kanoe.ai: a different text"],
     "expect": ["approval_void", "read_back_changed"]},
]


def sha_file(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--contract", default=str(DEFAULT))
    src = Path(ap.parse_args().contract)
    snap = HERE / "contract"
    if src.resolve() != snap.resolve():          # CI regenerates from the committed snapshot itself
        if snap.exists():
            shutil.rmtree(snap)
        for f in FILES:
            (snap / f).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src / f, snap / f)
    ops = json.loads((snap / "operations.json").read_text())
    version = ops["version"]
    lang = json.loads((snap / "vectors/approval-language.json").read_text())
    acts = json.loads((snap / "vectors/approval-language-acts.json").read_text())
    apv = json.loads((snap / "vectors/approval.json").read_text())
    contract = {"version": version, "order": apv["order"], "languages": lang["languages"], "acts": acts["acts"],
                "language_rule_version": lang["version"], "acts_rule_version": acts["version"],
                "approval_operations": [o["operation"] for o in ops["operations"] if o.get("requires_approval")]}
    cjson = json.dumps(contract, ensure_ascii=False, sort_keys=True)
    assert "'''" not in cjson and "`" not in cjson and "${" not in cjson
    sources = {f: sha_file(snap / f) for f in FILES}
    header = "contract: AgAPI " + version + " (EU) — " + ", ".join(f"{f} {s[:12]}" for f, s in sources.items())
    dist = HERE / "dist"
    dist.mkdir(exist_ok=True)
    py = (HERE / "templates/yes_one.py.tmpl").read_text().replace("__VERSION__", version).replace("__HEADER__", header).replace("__CONTRACT_JSON__", cjson)
    ts = (HERE / "templates/yes_one.ts.tmpl").read_text().replace("__VERSION__", version).replace("__HEADER_TS__", " * " + header).replace("__CONTRACT_JSON__", cjson)
    (dist / "yes_one.py").write_text(py)
    (dist / "yes_one.ts").write_text(ts)
    conf = {"contract_version": version, "note": "ONE conformance set for yes_one.py and yes_one.ts — the contract's own vectors + the flow cases.",
            "approval": apv["cases"], "explicit_yes": json.loads((snap / "vectors/explicit-yes.json").read_text())["cases"],
            "canonical": json.loads((snap / "vectors/canonical.json").read_text())["cases"],
            "idempotency": json.loads((snap / "vectors/idempotency.json").read_text())["cases"], "flow": FLOW}
    (dist / "conformance.json").write_text(json.dumps(conf, ensure_ascii=False, indent=1) + "\n")
    for name in ("test_yes_one.py", "yes_one.test.ts"):
        shutil.copyfile(HERE / "templates" / (name + ".tmpl"), dist / name)
    manifest = {"contract_version": version, "contract_sources": sources,
                "outputs": {f: sha_file(dist / f) for f in ("yes_one.py", "yes_one.ts", "conformance.json", "test_yes_one.py", "yes_one.test.ts")}}
    (dist / "MANIFEST.json").write_text(json.dumps(manifest, indent=1) + "\n")
    print(json.dumps(manifest["outputs"], indent=1))


if __name__ == "__main__":
    main()
