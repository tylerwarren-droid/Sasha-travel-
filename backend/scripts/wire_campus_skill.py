"""CR 54 · WIRE CAMPUSME INTO SASHA'S AGENT — docs/sasha/campus-skill-wiring.md, applied in one step (run on a founder ticket,
after Sasha 211; the Sasha tab merges). Every anchor must be found exactly once, or NOTHING is written and it says which.

    cd backend && python -m scripts.wire_campus_skill            # writes app/agent/sasha.py and tests/test_agapi_guards.py
    cd backend && python -m scripts.wire_campus_skill --check    # only checks the anchors (writes nothing)
Idempotent: a file already wired is left as it is.
"""
from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
AGENT = ROOT / "app" / "agent" / "sasha.py"
GUARD_TEST = ROOT / "tests" / "test_agapi_guards.py"
MARK = "CR 54 · campus skill"

# (anchor, replacement) — each anchor must occur exactly once
AGENT_HUNKS = [
    # 1 · import
    ("from agapi import v0 as API\n",
     "from agapi import v0 as API\nfrom agapi import skills as SK   # CR 54 · campus skill: the open skill (strict spaces in code) and its tools\n"),
    # 2 · renderers
    ("KINDS = {",
     "RENDER.update({\"find_schools\": \"inline\", \"find_visit_sessions\": \"inline\", \"plan_tour\": \"trip\", \"save_student\": \"inline\",\n"
     "               \"prepare_registration\": \"inline\", \"check_confirmation\": \"inline\", \"get_campus\": \"trip\"})   # CR 54 · campus skill\n"
     "KINDS = {"),
    # 3 · turn() takes the skill
    ("               voice: Optional[dict] = None) -> AsyncIterator[dict]:\n    \"\"\"One turn:",
     "               voice: Optional[dict] = None, skill: Optional[str] = None) -> AsyncIterator[dict]:\n    \"\"\"One turn:"),
    # 4 · the tool list
    ("    tools = tools_for_model()\n",
     "    tools = SK.tools(skill)          # CR 54 · campus skill: inside a skill ONLY its tools; in Sasha her travel tools\n"),
    # 5 · the skill card
    ("        return [{\"type\": \"text\", \"text\": P.AGENT_SYSTEM, \"cache_control\": {\"type\": \"ephemeral\"}}, {\"type\": \"text\", \"text\": extra}]\n",
     "        if skill == \"campus\":   # CR 54 · campus skill\n"
     "            extra += (\"\\n\\nYou're in CampusMe (the person opened it). One step per message, about four lines, one next step. \"\n"
     "                      \"Times, spaces and drives only from the tools. Never say a visit is registered unless get_campus says so. \"\n"
     "                      \"The school's statement box and Submit are always theirs, on their phone. They leave with “sasha”.\")\n"
     "        return [{\"type\": \"text\", \"text\": P.AGENT_SYSTEM, \"cache_control\": {\"type\": \"ephemeral\"}}, {\"type\": \"text\", \"text\": extra}]\n"),
    # 6 · the dispatch (a tool outside the open skill is refused, never run)
    ("            t = API.BY_NAME.get(u.name)\n",
     "            _mod = SK._module(skill)   # CR 54 · campus skill\n            t = (_mod.BY_NAME if _mod else API.BY_NAME).get(u.name)\n"),
    ("            r = await API.call(ctx, u.name, args)\n",
     "            r = await SK.call(ctx, skill, u.name, args)   # CR 54 · campus skill\n            tool_results.append(r)\n"),
    ("    turn_key = hashlib.sha256(",
     "    tool_results: List[dict] = []   # CR 54 · campus skill: what the tools gave, for the skill's figure guard\n    turn_key = hashlib.sha256("),
    # 7 · the guard (the final check and the rewrite's; speakable's per-sentence check too)
    ("            if guard_check(x, allowed, bool(booked_now)):\n",
     "            if guard_check(x, allowed, bool(booked_now)) or await _skill_bad(ctx, skill, x, tool_results):   # CR 54\n"),
    ("    bad = guard_check(\"\".join(raw), allowed, await _anything_booked(ctx))\n",
     "    bad = guard_check(\"\".join(raw), allowed, await _anything_booked(ctx)) + await _skill_bad(ctx, skill, \"\".join(raw), tool_results)   # CR 54\n"),
    ("        bad2 = guard_check(new, allowed, await _anything_booked(ctx))\n",
     "        bad2 = guard_check(new, allowed, await _anything_booked(ctx)) + await _skill_bad(ctx, skill, new, tool_results)   # CR 54\n"),
    ("async def _anything_booked(ctx: API.Ctx) -> bool:\n",
     "async def _skill_bad(ctx: API.Ctx, skill: Optional[str], text: str, results: List[dict]) -> List[str]:\n"
     "    \"\"\"CR 54 · campus skill: 'registered' only once recorded; times, prices, spaces and drives only from its tools.\"\"\"\n"
     "    if skill != \"campus\":\n"
     "        return []\n"
     "    from agapi import campus as CAMPUS\n"
     "    g = await CAMPUS.call(ctx, \"get_campus\", {})\n"
     "    return CAMPUS.guard_check(text, results, (g.get(\"result\") or {}).get(\"visits\") or [])\n\n\n"
     "async def _anything_booked(ctx: API.Ctx) -> bool:\n"),
    ("        elif _EUR.search(s) and any(b.startswith(\"price\") for b in bad):\n",
     "        elif any(b.startswith(\"figure\") for b in bad) and re.search(r\"[$€£]|\\d\", s):   # CR 54 · campus skill\n"
     "            out.append(\"The tour card shows the times.\")\n"
     "        elif _EUR.search(s) and any(b.startswith(\"price\") for b in bad):\n"),
    # 9 · the space shown
    ("    yield {\"type\": \"done\", \"text\": text, \"guard\": guard_log, \"tools\": ctx.calls, \"ms\": ms}\n",
     "    yield {\"type\": \"done\", \"text\": text, \"guard\": guard_log, \"tools\": ctx.calls, \"ms\": ms, \"skill\": skill}   # CR 54\n"),
    # 8 · the route and the quiver carry the skill
    ("async def turn_with_quiver(account: str, message: str, history: List[dict], session: Optional[str]) -> AsyncIterator[dict]:\n",
     "async def turn_with_quiver(account: str, message: str, history: List[dict], session: Optional[str],\n"
     "                          skill: Optional[str] = None) -> AsyncIterator[dict]:   # CR 54 · campus skill\n"),
    ("            async for ev in turn(account, message, history, session, voice):\n",
     "            async for ev in turn(account, message, history, session, voice, skill=skill):   # CR 54\n"),
    ("    if not message:\n        return JSONResponse({\"ok\": False, \"rule\": \"empty\"}, status_code=400)\n",
     "    tap = str(body.get(\"tap\") or \"\")[:40] or None   # CR 54 · campus skill: a skill button (\"skill:campus\" / \"skill:sasha\")\n"
     "    if not message and not tap:\n        return JSONResponse({\"ok\": False, \"rule\": \"empty\"}, status_code=400)\n"
     "    sk = await SK.resolve(account, message, tap)\n"
     "    if sk.consumed and sk.said:   # \"campus\" → \"Let's plan your campus tour.\" (said once)\n"
     "        async def opened():\n"
     "            yield f\"data: {json.dumps({'type': 'done', 'text': sk.said, 'skill': sk.skill, 'guard': [], 'ms': {}})}\\n\\n\"\n"
     "        return StreamingResponse(opened(), media_type=\"text/event-stream\", headers={\"Cache-Control\": \"no-cache\", \"X-Accel-Buffering\": \"no\"})\n"),
    ("            async for ev in turn_with_quiver(account, message, body.get(\"history\") or [], str(body.get(\"session_id\") or \"\")[:64] or None):\n",
     "            async for ev in turn_with_quiver(account, message, body.get(\"history\") or [], str(body.get(\"session_id\") or \"\")[:64] or None,\n"
     "                                             skill=sk.skill):   # CR 54\n"),
]
GUARD_HUNKS = [
    ("        self.assertEqual(set(AG.RENDER), set(API.BY_NAME) - {n for n in API.BY_NAME if n.startswith(\"_t_\")}, \"a tool without a renderer\")\n",
     "        from agapi import campus as CAMPUS   # CR 54 · campus skill: its tools need renderers too\n"
     "        self.assertEqual(set(AG.RENDER), (set(API.BY_NAME) | set(CAMPUS.BY_NAME)) - {n for n in API.BY_NAME if n.startswith(\"_t_\")}, \"a tool without a renderer\")\n"),
]


def plan(path: pathlib.Path, hunks) -> tuple:
    s = path.read_text()
    if MARK in s:
        return s, [], True
    bad = [a.strip().splitlines()[0][:90] for a, _ in hunks if s.count(a) != 1]
    if bad:
        return s, bad, False
    for a, b in hunks:
        s = s.replace(a, b, 1)
    return s, [], False


def main(check: bool) -> int:
    out, refused = [], False
    for path, hunks in ((AGENT, AGENT_HUNKS), (GUARD_TEST, GUARD_HUNKS)):
        s, bad, done = plan(path, hunks)
        rel = path.relative_to(ROOT)
        if done:
            print(f"{rel}: already wired")
        elif bad:
            refused = True
            print(f"⛔ {rel}: {len(bad)} anchor(s) moved — NOTHING written. Place by hand (docs/sasha/campus-skill-wiring.md):")
            for b in bad:
                print(f"     · {b}")
        else:
            out.append((path, s))
            print(f"{rel}: {len(hunks)} hunk(s) ready")
    if refused or check:
        return 1 if refused else 0
    for path, s in out:
        path.write_text(s)
        print(f"wrote {path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main("--check" in sys.argv))
