"""Sasha 204 · a scripted stand-in for the model, for tests and the deploy gate: each step is a list of blocks, streamed as the
real SDK streams them (text deltas, a tool_use block start), with optional delays — so timing behaviour can be checked."""
from __future__ import annotations

import asyncio
import json
import types


class Block(types.SimpleNamespace):
    def model_dump(self, exclude_none=True):
        return {k: v for k, v in self.__dict__.items() if v is not None and k != "delay"}


class _Stream:
    def __init__(self, blocks, delay=0.0):
        self.blocks, self.delay = blocks, delay

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    def __aiter__(self):
        async def gen():
            if self.delay:
                await asyncio.sleep(self.delay)
            for b in self.blocks:
                if b.type == "text":
                    yield types.SimpleNamespace(type="text", text=b.text)
                elif b.type == "tool_use":
                    yield types.SimpleNamespace(type="content_block_start", content_block=types.SimpleNamespace(type="tool_use", name=b.name))
        return gen()

    async def get_final_message(self):
        return types.SimpleNamespace(content=self.blocks)


def client(steps, delays=None, filler="Ooh, lovely — let me look.", seen=None):
    """steps: [[Block, …], …] — one list per model call; delays: seconds before each call's first event; `filler`: what
    the acknowledgement writer (messages.create) answers; `seen`: a list that gets each model call's arguments."""
    steps, delays = list(steps), list(delays or [])

    class Msgs:
        def stream(self, **kw):
            if seen is not None:
                seen.append(kw)
            return _Stream(steps.pop(0), delays.pop(0) if delays else 0.0)

        async def create(self, **kw):
            return types.SimpleNamespace(content=[Block(type="text", text=filler)])

        async def count_tokens(self, **kw):
            return None
    return types.SimpleNamespace(messages=Msgs())


async def quiver_checks() -> dict:
    """The gate's voice checks (Sasha 204/205 → 210 · ONE VOICE) — {name: (ok, detail)}: an acknowledgement only when nothing
    is ready after ~1.5 s, and the answer then continues it (no second opener; the next model step is told what was said);
    a quick answer gets none; each model step is ONE utterance; her internals and test disclaimers are never said; an opener
    is never used twice in a conversation."""
    import time
    import app.services.llm as LLM
    from agapi import v0 as API
    from app.agent import sasha as AG
    real_client, real_call = LLM.client, API.call
    out = {}

    async def slow_call(ctx, name, args):
        if name in ("get_status", "get_total", "get_trip"):
            return {"ok": True, "result": {"anything_booked": False, "total_eur": 1468.14}}
        await asyncio.sleep(1.8)
        return {"ok": True, "result": {"total_eur": 1468.14, "note": "Duffel TEST fares — nothing is held until book"}}

    async def run(steps, delays, message, history=None, seen=None, session=None):
        LLM.client, API.call = client(steps, delays, seen=seen), slow_call
        t0, evs = time.perf_counter(), []
        try:
            async for ev in AG.turn_with_quiver("00000000-0000-4000-8000-000000000001", message, history or [], session or f"gate-{time.time()}"):
                evs.append((round(time.perf_counter() - t0, 2), ev))
        finally:
            LLM.client, API.call = real_client, real_call
        return evs
    says = lambda evs: [e["text"] for _, e in evs if e["type"] == "say"]
    seen: list = []
    evs = await run([[Block(type="tool_use", id="t1", name="get_total_slow", input={})],
                     [Block(type="text", text="Lovely — the whole trip comes to about €1,468.")]], [0.2, 0], "What's the total?", seen=seen)
    q = [(t, e) for t, e in evs if e["type"] == "filler"]
    tool = next(((t, e) for t, e in evs if e["type"] == "tool"), None)
    out["nothing ready after ~1.5 s → ONE acknowledgement, before the slow tool's result (never a fact)"] = (
        len(q) == 1 and tool and q[0][0] < tool[0] and 1.3 <= q[0][0] <= 2.1 and AG.filler_ok(q[0][1]["text"], []),
        f"filler {q[:1]} · tool at {tool and tool[0]}")
    out["the answer CONTINUES the acknowledgement: no second opener, and the model is told what she said"] = (
        says(evs) == ["The whole trip comes to about one thousand five hundred euros."] and len(seen) == 2 and q
        and q[0][1]["text"] in json.dumps(seen[1]["system"], ensure_ascii=False), f"{says(evs)}")
    evs = await run([[Block(type="text", text="Lovely to meet you. Where would you like to go?")]], [1.9], "Hi Sasha, I'm Tyler")
    q = [(t, e) for t, e in evs if e["type"] == "filler"]
    out["a slow first answer gets an acknowledgement at ~1.5 s (never a fact, never opening like an answer)"] = (
        bool(q) and 1.3 <= q[0][0] <= 2.1 and AG.filler_ok(q[0][1]["text"], []), str(q[:1]))
    evs = await run([[Block(type="text", text="Lovely to meet you, Tyler. "), Block(type="text", text="Where would you like to go? "),
                      Block(type="text", text="Somewhere warm, or somewhere with mountains?")]], [0.1], "Hi Sasha")
    out["a quick answer gets no acknowledgement, and the whole step is ONE utterance (no gaps between her phrases)"] = (
        not any(e["type"] == "filler" for _, e in evs) and len(says(evs)) == 1, str([e["type"] for _, e in evs]))
    evs = await run([[Block(type="text", text="I got a bit mixed up there, sorry. Here's your trip, with a flight that fits. "
                                               "These are test bookings, so nothing is charged. Have a look at the other flights if you like.")]],
                    [0.1], "Show me")
    said = " ".join(says(evs))
    out["her internals and test disclaimers are never said"] = (
        said == "Here's your trip, with a flight that fits. Have a look at the other flights if you like.", said)
    sess = f"gate-openers-{time.time()}"
    evs = await run([[Block(type="text", text="Great! Where are you flying from?")]], [0.1], "Vietnam",
                    history=[{"role": "user", "content": "Hi"}, {"role": "assistant", "content": "Great — who's coming with you?"}], session=sess)
    out["an opener is never used twice in a conversation"] = (says(evs) == ["Where are you flying from?"], str(says(evs)))
    real_still, AG.STILL_AFTER_S = AG.STILL_AFTER_S, 1.0   # (8 s live; 1 s here, the same rule)
    try:
        evs = await run([[Block(type="text", text="Let me put that together. "), Block(type="tool_use", id="t1", name="propose_trip_slow", input={})],
                         [Block(type="text", text="Here's your trip, with a flight that fits.")]], [0.2, 0], "Plan it")
    finally:
        AG.STILL_AFTER_S = real_still
    st = [(t, e) for t, e in evs if e["type"] == "filler"]
    out["long work after she spoke → ONE plain “nearly there”, never more"] = (
        len(st) == 1 and st[0][1]["why"] == "still working" and st[0][1]["text"] in AG.FILLERS["still"], str(st))
    sess = "gate-fillers"
    lines = [await AG.make_filler("Hoi An!", "think", sess) for _ in range(8)]
    AG._USED.pop(sess, None)
    out["acknowledgements never repeat in a conversation and never carry a fact"] = (
        len({AG._norm(x) for x in lines if x}) == len([x for x in lines if x]) and all(AG.filler_ok(x, []) for x in lines if x), str(lines[:4]))
    return out
