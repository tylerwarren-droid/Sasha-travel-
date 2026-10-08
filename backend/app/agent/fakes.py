"""Sasha 204 · a scripted stand-in for the model, for tests and the deploy gate: each step is a list of blocks, streamed as the
real SDK streams them (text deltas, a tool_use block start), with optional delays — so timing behaviour can be checked."""
from __future__ import annotations

import asyncio
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


def client(steps, delays=None, filler="Ooh, lovely — let me look."):
    """steps: [[Block, …], …] — one list per model call; delays: seconds before each call's first event; `filler`: what
    the acknowledgement writer (messages.create) answers."""
    steps, delays = list(steps), list(delays or [])

    class Msgs:
        def stream(self, **kw):
            return _Stream(steps.pop(0), delays.pop(0) if delays else 0.0)

        async def create(self, **kw):
            return types.SimpleNamespace(content=[Block(type="text", text=filler)])

        async def count_tokens(self, **kw):
            return None
    return types.SimpleNamespace(messages=Msgs())


async def quiver_checks() -> dict:
    """The gate's timing checks — {name: (ok, detail)}: a tool slower than 1 s gets a quiver before its result; a slow first
    answer gets a quiver at ~0.9 s; a quick answer gets none."""
    import time
    import app.services.llm as LLM
    from agapi import v0 as API
    from app.agent import sasha as AG
    real_client, real_call = LLM.client, API.call
    out = {}

    async def slow_call(ctx, name, args):
        if name in ("get_status", "get_total", "get_trip"):
            return {"ok": True, "result": {"anything_booked": False, "total_eur": 1468.14}}
        await asyncio.sleep(1.5)
        return {"ok": True, "result": {"total_eur": 1468.14}}

    async def run(steps, delays, message):
        LLM.client, API.call = client(steps, delays), slow_call
        t0, evs = time.perf_counter(), []
        try:
            async for ev in AG.turn_with_quiver("00000000-0000-4000-8000-000000000001", message, [], f"gate-{time.time()}"):
                evs.append((round(time.perf_counter() - t0, 2), ev))
        finally:
            LLM.client, API.call = real_client, real_call
        return evs
    evs = await run([[Block(type="tool_use", id="t1", name="get_total_slow", input={})],
                     [Block(type="text", text="The whole trip comes to about €1,468.")]], [0.2, 0], "What's the total?")
    q = [(t, e) for t, e in evs if e["type"] == "filler"]
    tool = next(((t, e) for t, e in evs if e["type"] == "tool"), None)
    out["a tool slower than 1 s gets an acknowledgement before its result (never a fact)"] = (
        bool(q) and tool and q[0][0] < tool[0] and q[0][0] <= 1.2 and AG.filler_ok(q[0][1]["text"], []), f"filler {q[:1]} · tool at {tool and tool[0]}")
    evs = await run([[Block(type="text", text="Lovely to meet you. Where would you like to go?")]], [1.6], "Hi Sasha, I'm Tyler")
    q = [(t, e) for t, e in evs if e["type"] == "filler"]
    out["a slow first answer gets an acknowledgement at ~0.9 s (never a fact)"] = (
        bool(q) and 0.7 <= q[0][0] <= 1.6 and AG.filler_ok(q[0][1]["text"], []), str(q[:1]))
    evs = await run([[Block(type="text", text="Lovely to meet you. Where would you like to go?")]], [0.1], "Hi Sasha")
    out["a quick answer gets no acknowledgement"] = (not any(e["type"] == "filler" for _, e in evs) and any(e["type"] == "say" for _, e in evs),
                                                     str([e["type"] for _, e in evs]))
    sess = "gate-fillers"
    lines = [await AG.make_filler("Hoi An!", "think", sess) for _ in range(8)]
    AG._USED.pop(sess, None)
    out["acknowledgements never repeat in a conversation and never carry a fact"] = (
        len({AG._norm(x) for x in lines if x}) == len([x for x in lines if x]) and all(AG.filler_ok(x, []) for x in lines if x), str(lines[:4]))
    return out
