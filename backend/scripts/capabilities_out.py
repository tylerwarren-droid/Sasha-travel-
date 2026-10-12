"""Sasha 249 · writes frontend/lib/capabilities.generated.mjs FROM agapi/s2_home.py CAPABILITIES — the chips on /s2 and /next are
never written by hand, so they can't drift from what she can do (EU 245 §1.5 / T10).
    python -m scripts.capabilities_out            (from backend/)"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "frontend", "lib",
                   "capabilities.generated.mjs")


def render() -> str:
    from agapi import s2_home as HOME
    return HOME.frontend_module()


if __name__ == "__main__":
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(render())
    print(f"wrote {OUT}")
