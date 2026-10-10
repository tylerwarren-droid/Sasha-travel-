"""Sasha 232 · THE GATE'S OWN KEY, AND WHAT ONE RUN COSTS.

  use_gate_key()  before anything builds an Anthropic client: SASHA_GATE_ANTHROPIC_API_KEY (when set) becomes this process's
                  ANTHROPIC_API_KEY — the gate's spend is on its own key, never the live app's. Only its fingerprint is printed
                  (type prefix + sha256 first 12). Unset → the service's key, as before (said in the log).
  install()       counts every model call's usage in this process (messages.create, and each stream's final message).
  report()        one line per model: calls, tokens (input · cache write · cache read · output), and dollars where the price is known.
The suites that run in subprocesses (WhatsApp, Postgres, demo safety) are offline unit tests with fakes — no model calls.
"""
from __future__ import annotations

import hashlib
import os
from collections import defaultdict
from typing import Dict

# $ per million tokens: (input, output[, 5-minute cache write, cache read]). Without the last two: write = 1.25 × input, read =
# 0.1 × input. Sonnet 5.5 from Anthropic's pricing page (platform.claude.com/docs/en/about-claude/pricing, read 10 Oct 2026).
PRICES = {"claude-haiku-4-5": (1.0, 5.0), "claude-sonnet-4-5": (3.0, 15.0), "claude-sonnet-4-6": (3.0, 15.0),
          "claude-opus-4-1": (15.0, 75.0), "claude-sonnet-5-5": (2.0, 10.0, 2.5, 0.10)}
_USE: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
_SEEN: set = set()


def fingerprint(v: str) -> str:
    v = (v or "").strip()
    prefix = "-".join(v.split("-")[:2]) + "-" if v.count("-") >= 2 else ""
    return f"{prefix}… sha256 {hashlib.sha256(v.encode()).hexdigest()[:12]}" if v else "(none)"


def use_gate_key() -> None:
    gate = os.getenv("SASHA_GATE_ANTHROPIC_API_KEY", "").strip()
    if gate:
        os.environ["ANTHROPIC_API_KEY"] = gate
        print(f"gate: its own Anthropic key ({fingerprint(gate)})")
    else:
        print(f"gate: SASHA_GATE_ANTHROPIC_API_KEY unset — the service's key ({fingerprint(os.getenv('ANTHROPIC_API_KEY', ''))})")


def _model(m: str) -> str:
    m = str(m or "?")
    return next((k for k in PRICES if m.startswith(k)), m)


def _add(model: str, usage) -> None:
    if usage is None:
        return
    u = _USE[_model(model)]
    u["calls"] += 1
    u["input"] += int(getattr(usage, "input_tokens", 0) or 0)
    u["output"] += int(getattr(usage, "output_tokens", 0) or 0)
    u["cache_write"] += int(getattr(usage, "cache_creation_input_tokens", 0) or 0)
    u["cache_read"] += int(getattr(usage, "cache_read_input_tokens", 0) or 0)


def install() -> None:
    from anthropic.resources.messages import AsyncMessages, Messages
    from anthropic.lib.streaming import AsyncMessageStream

    def wrap_create(orig):
        async def acreate(self, *a, **kw):
            r = await orig(self, *a, **kw)
            if not kw.get("stream"):
                _add(getattr(r, "model", kw.get("model")), getattr(r, "usage", None))
            return r
        return acreate
    AsyncMessages.create = wrap_create(AsyncMessages.create)
    orig_sync = Messages.create

    def screate(self, *a, **kw):
        r = orig_sync(self, *a, **kw)
        if not kw.get("stream"):
            _add(getattr(r, "model", kw.get("model")), getattr(r, "usage", None))
        return r
    Messages.create = screate
    orig_final = AsyncMessageStream.get_final_message

    async def final(self):
        m = await orig_final(self)
        if id(self) not in _SEEN:
            _SEEN.add(id(self))
            _add(getattr(m, "model", "?"), getattr(m, "usage", None))
        return m
    AsyncMessageStream.get_final_message = final


def report() -> float:
    total, known = 0.0, True
    for model, u in sorted(_USE.items()):
        p = PRICES.get(model)
        cost = None
        if p:
            cw, cr = (p[2], p[3]) if len(p) == 4 else (p[0] * 1.25, p[0] * 0.1)
            cost = (u["input"] * p[0] + u["cache_write"] * cw + u["cache_read"] * cr + u["output"] * p[1]) / 1e6
            total += cost
        else:
            known = False
        print(f"gate cost: {model}: {u['calls']} calls · in {u['input']:,} · cache write {u['cache_write']:,} · cache read "
              f"{u['cache_read']:,} · out {u['output']:,} · " + (f"${cost:.2f}" if cost is not None else "price not in the table"))
    print(f"gate cost: TOTAL ${total:.2f}" + ("" if known else " (+ models without a price above)")
          + f" over {sum(u['calls'] for u in _USE.values())} model calls")
    return total
