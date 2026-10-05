#!/usr/bin/env python3
"""Sasha 157 · THE MAILBOX STOP HOOK: a Sasha/CR turn cannot end until its readout is in AD's public.tab_messages.

Registered as a Claude Code `Stop` hook. It reads the hook's JSON on stdin ({session_id, transcript_path, stop_hook_active})
and the turn's transcript:

  · the prompt: the founder's latest message. Only a prompt LABELLED "Sasha <n>" or "CR <n>" (at its start, a pasted
    ticket included) needs a readout; any other prompt (the US and EU tabs' P-/EU-series, a quick question) passes;
  · the readout: an `insert into public.tab_messages … values ('SASHA'|'CR', 'report', '<label>…')` made AFTER that prompt
    whose result was not an error. Checked from the transcript, which needs no database credential. When AD_MAILBOX_URL
    and AD_MAILBOX_KEY (a read-only key) are in the environment, the row is ALSO looked up in the table itself;
  · no readout: the stop is BLOCKED with the reason, at most twice per prompt; the third time it is allowed, with a loud
    warning to the founder. A hook that fails for its own reasons never blocks (it warns instead).

Nothing here prints or stores a secret. State (the block count per prompt) lives in ~/.claude/mailbox-hook/.
"""
from __future__ import annotations

import json
import os
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Optional, Tuple

MAX_BLOCKS = 2
STATE = Path.home() / ".claude" / "mailbox-hook"
LABEL = re.compile(r"^\s*(?:<pasted_content[^>]*>\s*)?(Sasha|CR)\s+(\d+[A-Za-z]?)\b")
NOT_A_PROMPT = ("<system-reminder>", "<cross-session-message", "<task-notification", "[SYSTEM NOTIFICATION", "Caveat:",
                "<command-", "<local-command", "This session is being continued")


def _text(content) -> Optional[str]:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        if any(isinstance(x, dict) and x.get("type") == "tool_result" for x in content):
            return None
        parts = [x.get("text", "") for x in content if isinstance(x, dict) and x.get("type") == "text"]
        return "\n".join(parts) if parts else None
    return None


def last_prompt(rows: list) -> Tuple[Optional[int], Optional[str], Optional[str]]:
    """(index, timestamp, text) of the founder's latest message — not a tool result, a reminder or a peer's message."""
    for i in range(len(rows) - 1, -1, -1):
        r = rows[i]
        if r.get("type") != "user" or r.get("isMeta") or r.get("isCompactSummary"):
            continue
        t = _text((r.get("message") or {}).get("content"))
        if t is None or not t.strip() or t.lstrip().startswith(NOT_A_PROMPT):
            continue
        return i, r.get("timestamp"), t
    return None, None, None


def label_of(prompt: str) -> Optional[str]:
    m = LABEL.match(prompt or "")
    return f"{m[1]} {m[2]}" if m else None


def readout_in_transcript(rows: list, start: int, label: str) -> bool:
    """A successful tab_messages insert for this label, after the prompt."""
    body = re.compile(r"insert\s+into\s+public\.tab_messages.*?values\s*\(\s*'(?:SASHA|CR)'\s*,\s*'report'\s*,\s*"
                      r"(?:\$\w*\$|')\s*" + re.escape(label) + r"\b", re.I | re.S)
    calls = {}
    for r in rows[start + 1:]:
        c = (r.get("message") or {}).get("content")
        if not isinstance(c, list):
            continue
        for x in c:
            if not isinstance(x, dict):
                continue
            if x.get("type") == "tool_use" and str(x.get("name", "")).endswith("execute_sql") \
                    and body.search(str((x.get("input") or {}).get("query", ""))):
                calls[x.get("id")] = True
            elif x.get("type") == "tool_result" and x.get("tool_use_id") in calls and not x.get("is_error"):
                out = json.dumps(x.get("content"))[:400]
                if '\\"error\\"' not in out and '"error"' not in out[:60]:
                    return True
    return False


def readout_in_table(label: str, since: str) -> Optional[bool]:
    """When a read-only key is configured: is the row really there? None when not configured or not reachable."""
    url, key = os.getenv("AD_MAILBOX_URL", "").rstrip("/"), os.getenv("AD_MAILBOX_KEY", "")
    if not url or not key:
        return None
    q = urllib.parse.urlencode({"select": "id", "tab": "in.(SASHA,CR)", "body": f"like.{label}*", "created_at": f"gt.{since}",
                                "limit": "1"})
    try:
        req = urllib.request.Request(f"{url}/rest/v1/tab_messages?{q}", headers={"apikey": key, "Authorization": f"Bearer {key}"})
        with urllib.request.urlopen(req, timeout=8) as r:
            return bool(json.loads(r.read() or b"[]"))
    except Exception:
        return None


def _count(session: str, since: str) -> Path:
    STATE.mkdir(parents=True, exist_ok=True)
    return STATE / (re.sub(r"[^A-Za-z0-9_-]", "_", f"{session}-{since}") + ".count")


def decide(hook: dict) -> dict:
    """{} to allow quietly; {"decision": "block", "reason": …} to block; {"systemMessage": …} to allow with a warning."""
    path = hook.get("transcript_path")
    if not path or not os.path.exists(path):
        return {}
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            try:
                rows.append(json.loads(line))
            except ValueError:
                continue
    i, since, prompt = last_prompt(rows)
    label = label_of(prompt or "")
    if i is None or label is None:
        return {}                                   # not a Sasha/CR ticket: nothing is required
    found = readout_in_transcript(rows, i, label)
    in_table = readout_in_table(label, since or "") if found else None
    if found and in_table is not False:
        return {}
    counter = _count(str(hook.get("session_id") or "s"), since or "t")
    n = int(counter.read_text() or 0) if counter.exists() else 0
    why = (f"the insert for '{label}' was made but the row is NOT in public.tab_messages" if found
           else f"no readout for '{label}' has been posted to public.tab_messages since the prompt")
    if n >= MAX_BLOCKS:
        return {"systemMessage": f"⚠️⚠️ MAILBOX HOOK: {label} ENDED WITHOUT ITS READOUT — {why}. Blocked {n} times; "
                                 "allowed now so the session isn't stuck. The founder has NOT been told this turn's result."}
    counter.write_text(str(n + 1))
    return {"decision": "block",
            "reason": f"Mailbox hook ({n + 1}/{MAX_BLOCKS}): {why}. Before ending, insert this turn's readout: "
                      f"insert into public.tab_messages (tab, direction, body) values ('SASHA','report', '{label} …') "
                      "on project xzmybjgzffgadaeuundq."}


def main() -> int:
    try:
        hook = json.load(sys.stdin)
        out = decide(hook)
    except Exception as e:   # the hook's own failure never traps a session
        out = {"systemMessage": f"⚠️ mailbox hook failed ({type(e).__name__}) — the readout was NOT checked this turn."}
    if out:
        print(json.dumps(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
