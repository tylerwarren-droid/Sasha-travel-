"""Sasha 203 · TEN CONVERSATIONS WITH THE /next AGENT, a second model playing the traveller — scratch guests, Duffel replayed,
Stripe TEST, cleaned up after. Not part of the deploy gate (two models talking is not deterministic); run it to judge her.

Checks per conversation:
  · no repetition — no reply of hers said twice, no question asked again after it was answered
  · the proposal has a flight and a total — propose_trip called, and her reply that turn names a flight and a € total
  · no claims without tool proof — every reply passes the guard (booked/paid/confirmed only from Pacioli; € only from tools);
    any reply the guard had to send back is counted
Writes docs/sasha/S203-agent-conversations.md (summary first, then the transcripts).
"""
from __future__ import annotations

import asyncio
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

TRAVELLER_MODEL = os.getenv("SASHA_TRAVELLER_MODEL", "claude-sonnet-5-5")
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "docs", "sasha", "S203-agent-conversations.md")

# each: (name, who the traveller is, the scripted lines they must say, in order — verbatim)
SCENARIOS = [
    ("1 · total, then book", "Tyler, 2 people, Vietnam for 8 nights from 15 November, beaches and culture, flying from London. Traveller details: "
     "Tyler Warren, Mr, 1 Feb 1980; Sam Warren, Ms, 3 Mar 1982.",
     ["I'd love to go to Vietnam.", "No. What's the total with the flight and lodging?", "Then book it.", "Yes."]),
    ("2 · the BA one", "Maria, 2 people, Vietnam, 7 nights from 20 November, food, from Madrid.",
     ["Hi! Thinking about Vietnam.", "Can I see other flights?", "the BA one", "What's the total now?"]),
    ("3 · make it 3 of us", "Jon, Vietnam, 10 nights from 1 December, culture and hiking, from Madrid; 2 people at first.",
     ["Hello, I want to plan a Vietnam trip.", "actually make it 3 of us", "What's the new total?"]),
    ("4 · change a hotel", "Priya, 2 people, Vietnam 8 nights from 12 November, beaches, from Madrid; wants Hoi An in the trip.",
     ["Hi Sasha, Vietnam please — with Hoi An in it.", "Can you change the hotel in Hoi An to something right on the beach?", "And the total?"]),
    ("5 · vague on dates", "Leo, travelling solo, Vietnam, from Madrid, street food; when first asked about dates say \"sometime in autumn?\", "
     "and when asked again say \"mid November, about a week\".",
     ["Hey, I fancy Vietnam.", "What happens on the first day?"]),
    ("6 · everything at once", "Ana. Traveller details: Ana Ruiz, Ms, 4 Apr 1990; Luis Ruiz, Mr, 9 Sep 1988.",
     ["Hi! I'm Ana, two of us, Vietnam from 10 to 18 November, beaches and food, flying from Madrid.", "Then book it.", "Yes.", "Is it booked?"]),
    ("7 · is it booked?", "Sam, 2 people, Vietnam 6 nights from 3 December, relaxing, from Madrid.",
     ["Hi, a relaxing Vietnam trip please.", "Is it booked already?", "What would it cost?"]),
    ("8 · rushes", "Kim, impatient: 2 people, 7 nights from 25 November, from Madrid, food. Answers in a few words.",
     ["Just book me something in Vietnam, now.", "Fine. What's the total?"]),
    ("9 · changes dates", "Omar, 2 people, Vietnam, 8 nights from 14 November, culture, from Madrid.",
     ["Hello! Vietnam for a cultural trip, please.", "Our dates have to move — start on 21 November instead.", "What's the new total?"]),
    ("10 · says no", "Eve, 2 people, Vietnam 7 nights from 5 December, honeymoon, from Madrid.",
     ["Hi! We're planning our honeymoon in Vietnam.", "What are the stays?", "No, not ready to book yet.", "Which flights are we on?"]),
]

TRAVELLER_SYSTEM = ("You are role-playing a traveller talking to Sasha, a travel concierge, in a web chat. Stay in character. "
                    "Reply with ONLY your next message — short and natural, like a real person typing.\n\nWho you are: ")


async def traveller_says(client, who: str, next_line: str, transcript: list) -> str:
    """Answer Sasha's question if she asked one the next scripted line doesn't answer; otherwise say the scripted line."""
    msgs = [{"role": "user" if m["role"] == "assistant" else "assistant", "content": m["content"] or "…"} for m in transcript]
    if not msgs or msgs[0]["role"] != "user":
        msgs.insert(0, {"role": "user", "content": "(The chat opens.)"})
    r = await client.messages.create(model=TRAVELLER_MODEL, max_tokens=150, system=TRAVELLER_SYSTEM + who + (
        f"\n\nYour next scripted line is: \"{next_line}\". If Sasha just asked you something that line doesn't answer, answer her "
        "briefly from who you are (it's not time for the line yet). Otherwise reply with EXACTLY the scripted line." if next_line else
        "\n\nYou've said everything you came to say: reply with exactly [END]."), messages=msgs)
    return "".join(b.text for b in r.content if b.type == "text").strip()


def _norm(t: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", (t or "").lower()).strip()


async def one(name: str, who: str, steps: list, max_turns: int = 18) -> dict:
    from booking_signer import guest_accounts as GA, ops
    from app.agent import sasha as AG
    from app.services.llm import client
    g, why = await GA.create_guest("agent-conv")
    a = g["account_id"]
    transcript, turns, guarded, proposal_ok, proposals = [], [], 0, None, 0
    t0 = time.time()
    try:
        todo = list(steps)
        for i in range(max_turns):
            said = todo[0] if i == 0 else await traveller_says(client, who, todo[0] if todo else "", transcript)
            if (said.startswith("[END]") or not said) and todo:
                said = todo[0]   # never end with scripted lines unsaid
            if said.startswith("[END]") or not said:
                break
            if todo and _norm(todo[0]) in _norm(said):
                todo.pop(0)
            text, tools, ms, guard = "", [], None, []
            async for ev in AG.turn(a, said, transcript, f"conv-{name[:2]}"):
                if ev["type"] == "tool":
                    tools.append(ev["name"] + ("" if ev["ok"] else f"!{ev.get('error')}"))
                elif ev["type"] == "done":
                    text, ms, guard = ev["text"], ev["ms"], ev["guard"]
            guarded += bool(guard)
            if "propose_trip" in tools:
                proposals += 1
                good = bool(re.search(r"€\s?\d", text)) and bool(re.search(r"(?i)flight", text))
                proposal_ok = good if proposal_ok is None else (proposal_ok and good)
            transcript += [{"role": "user", "content": said}, {"role": "assistant", "content": text}]
            turns.append({"user": said, "sasha": text, "tools": tools, "ms": ms, "guard": guard})
    finally:
        await ops.ADMIN("DELETE", f"/admin/users/{a}", {})
    replies = [_norm(t["sasha"]) for t in turns if t["sasha"]]
    repeated = len(replies) - len(set(replies))
    qs = [q for t in turns for q in re.findall(r"[^.?!]*\?", t["sasha"])]
    asked_twice = sorted({_norm(q) for q in qs if [_norm(x) for x in qs].count(_norm(q)) > 1 and len(_norm(q)) > 12})
    from app.agent.sasha import _CLAIM
    unproven = [t["sasha"] for t in turns if _CLAIM.search(t["sasha"]) and not any(x.startswith("get_status") for x in t["tools"])]
    return {"name": name, "steps_left": todo, "turns": turns, "repeated": repeated, "asked_twice": asked_twice, "proposal_ok": proposal_ok,
            "proposals": proposals, "guarded": guarded, "unproven": unproven, "secs": int(time.time() - t0),
            "ms_first": [t["ms"]["first_text"] for t in turns if t["ms"] and t["ms"].get("first_text")],
            "ms_total": [t["ms"]["total"] for t in turns if t["ms"]]}


def render(results: list) -> str:
    def p(v):
        return "✅" if v else ("—" if v is None else "❌")
    lines = ["# Sasha 203 · the /next agent — ten conversations", "",
             f"*A second model ({TRAVELLER_MODEL}) plays the traveller. The agent is {__import__('app.agent.sasha', fromlist=['MODEL']).MODEL}. "
             "Scratch guests; Duffel replayed from recorded TEST answers; Stripe TEST. Generated by `backend/scripts/agent_conversations.py`.*", "",
             "| # | conversation | turns | no repetition | proposal: flight + total | no unproven claims | guard rewrites | first text, median ms | turn, median ms |",
             "|---|---|---|---|---|---|---|---|---|"]
    med = lambda xs: sorted(xs)[len(xs) // 2] if xs else "—"
    for r in results:
        lines.append(f"| {r['name'].split(' · ')[0]} | {r['name'].split(' · ', 1)[1]} | {len(r['turns'])} | "
                     f"{p(r['repeated'] == 0 and not r['asked_twice'])} | {p(r['proposal_ok'])} | {p(not r['unproven'])} | {r['guarded']} | "
                     f"{med(r['ms_first'])} | {med(r['ms_total'])} |" + (f" unsaid: {r['steps_left']}" if r.get("steps_left") else ""))
    for r in results:
        lines += ["", f"## {r['name']}", ""]
        if r["repeated"] or r["asked_twice"]:
            lines.append(f"- repetition: {r['repeated']} repeated replies; asked again: {r['asked_twice']}")
        if r["unproven"]:
            lines.append(f"- unproven claims: {r['unproven']}")
        for t in r["turns"]:
            lines.append(f"- **Traveller:** {t['user']}")
            lines.append(f"  **Sasha:** {t['sasha']}" + (f"  \n  *tools: {', '.join(t['tools'])}*" if t["tools"] else "")
                         + (f"  \n  *guard: {'; '.join(t['guard'])}*" if t["guard"] else ""))
    return "\n".join(lines) + "\n"


async def main() -> int:
    from booking_signer import routes  # noqa: F401
    sem = asyncio.Semaphore(int(os.getenv("CONV_PARALLEL", "4")))

    async def run(s):
        async with sem:
            try:
                r = await one(*s)
            except Exception as e:
                r = {"name": s[0], "steps_left": s[2], "turns": [], "repeated": 0, "asked_twice": [], "proposal_ok": False, "proposals": 0, "guarded": 0,
                     "unproven": [f"the run failed: {type(e).__name__}: {e}"], "secs": 0, "ms_first": [], "ms_total": []}
            print(f"{r['name']}: {len(r['turns'])} turns, proposal_ok={r['proposal_ok']}, repeated={r['repeated']}, "
                  f"asked_twice={len(r['asked_twice'])}, unproven={len(r['unproven'])}, guarded={r['guarded']}, {r['secs']}s", flush=True)
            return r
    results = await asyncio.gather(*[run(s) for s in SCENARIOS])
    open(OUT, "w", encoding="utf-8").write(render(results))
    print("wrote", OUT)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
