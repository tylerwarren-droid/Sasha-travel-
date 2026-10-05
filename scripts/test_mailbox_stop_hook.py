"""Sasha 157 · the mailbox Stop hook blocks a labelled turn with no readout, twice, then lets it end with a warning.

    python3 scripts/test_mailbox_stop_hook.py -v
"""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))
import mailbox_stop_hook as H  # noqa: E402


def _t(rows):
    f = tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False)
    for r in rows:
        f.write(json.dumps(r) + "\n")
    f.close()
    return f.name


def prompt(text, ts="2026-10-05T20:00:00Z"):
    return {"type": "user", "timestamp": ts, "message": {"role": "user", "content": text}}


def insert(label, tid="t1", tab="SASHA", error=False):
    q = f"insert into public.tab_messages (tab, direction, body) values ('{tab}','report', $b${label} readout …$b$)"
    return [{"type": "assistant", "message": {"content": [{"type": "tool_use", "id": tid, "name": "mcp__claude_ai_Supabase__execute_sql",
                                                         "input": {"project_id": "x", "query": q}}]}},
            {"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": tid,
                                                      "content": [{"type": "text", "text": '{"error": "denied"}' if error else '{"result": "[]"}'}]}]}}]


class Hook(unittest.TestCase):
    def setUp(self):
        H.STATE = Path(tempfile.mkdtemp())

    def run_hook(self, rows, session="s1"):
        return H.decide({"session_id": session, "transcript_path": _t(rows), "stop_hook_active": False})

    def test_blocks_twice_then_warns(self):
        rows = [prompt('<pasted_content id="a">\nSasha 157: do things')]
        self.assertEqual(self.run_hook(rows)["decision"], "block")
        self.assertEqual(self.run_hook(rows)["decision"], "block")
        out = self.run_hook(rows)
        self.assertNotIn("decision", out)
        self.assertIn("WITHOUT ITS READOUT", out["systemMessage"])

    def test_the_readout_lets_it_end(self):
        self.assertEqual(self.run_hook([prompt("Sasha 157: x")] + insert("Sasha 157")), {})
        self.assertEqual(self.run_hook([prompt("CR 31 — y")] + insert("CR 31", tab="CR")), {})

    def test_wrong_label_failed_insert_or_before_the_prompt_do_not_count(self):
        self.assertEqual(self.run_hook([prompt("Sasha 157: x", "T1")] + insert("Sasha 156"))["decision"], "block")
        self.assertEqual(self.run_hook([prompt("Sasha 158: x", "T2")] + insert("Sasha 158", error=True))["decision"], "block")
        self.assertEqual(self.run_hook(insert("Sasha 159") + [prompt("Sasha 159: x", "T3")])["decision"], "block")

    def test_other_tabs_and_unlabelled_prompts_pass(self):
        for p in ("P803cq — the US tab's work", "EU 160: docs", "Quick, before anything else: read X"):
            self.assertEqual(self.run_hook([prompt(p)]), {}, p)

    def test_reminders_and_peer_messages_are_not_the_prompt(self):
        rows = [prompt("Sasha 160: x"), prompt("<system-reminder>noise</system-reminder>"),
                prompt('<cross-session-message from="x">CR → Sasha</cross-session-message>')]
        self.assertEqual(self.run_hook(rows)["decision"], "block")
        self.assertEqual(self.run_hook(rows + insert("Sasha 160")), {})

    def test_the_hook_never_traps_on_its_own_failure(self):
        self.assertEqual(H.decide({"transcript_path": "/nope"}), {})


if __name__ == "__main__":
    unittest.main()
