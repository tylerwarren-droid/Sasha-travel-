"""Sasha 321 · THE VOICE-AVATAR PROOF, after the deploy gate's verdict (never part of it): one booking at Kanoe's test venue on the voice
avatar's path (voice_turn.turn — what /api/voice/conductor calls), through the REAL AgAPI SANDBOX — no saved answers — by a scratch TEST
guest (a test person's acts go to the sandbox; nothing reaches a real venue, the sandbox captures every send). Prints AgAPI's act id.
A failure is printed, never a failed deploy: the sandbox being down must not block production. SASHA_GATE_VOICE_PROOF=off skips it.
    gate.py calls run(original_call) after its verdict, with AgAPI's real sender (the gate's fake is put back after)."""
from __future__ import annotations

import os
import secrets


async def run(real_call) -> None:
    if os.getenv("SASHA_GATE_VOICE_PROOF", "on").strip().lower() == "off":
        print("voice proof: SKIPPED (SASHA_GATE_VOICE_PROOF=off)")
        return
    from agapi import venue_submit as VS
    from booking_signer import guest_accounts as GA, ops, voice_turn as VT
    from agapi.booking_rules import booking_rules as BR
    from scripts.core_suites import _book_by_voice
    fake, VS.CALL = VS.CALL, real_call   # the real AgAPI for this proof only (a test person → the sandbox)
    g, why = await GA.create_guest("voice-proof")
    if not g:
        VS.CALL = fake
        print(f"voice proof: ⚠ no scratch guest ({why}) — not run")
        return
    a = g["account_id"]
    try:
        assert await VS.target(a) == "sandbox", "a scratch guest must book on the sandbox"
        guest = "+15005550" + f"{secrets.randbelow(800) + 200:03d}"   # the sandbox's own guest numbers; never a STOP
        made, seen = await _book_by_voice(a, ("Book a table for two at the Sasha Test Venue in Madrid on Saturday at 9pm, please.",),
                                          VT, BR, contact=f"Proof Guest {guest}")
        tyler = any("hand this to Tyler" in x for x in seen)
        for m in made:
            print(f"voice proof: {'✅' if not tyler else '⚠'} AgAPI act {m.get('act_id')} · {m.get('venue')} · state {m.get('state')} (sandbox)")
        if not made:
            print(f"voice proof: ⚠ no AgAPI act — {' | '.join(seen)[-200:]}")
    except Exception as e:
        print(f"voice proof: ⚠ {type(e).__name__}: {e}")
    finally:
        VS.CALL = fake
        s, _ = await ops.ADMIN("DELETE", f"/admin/users/{a}", {})
        print(f"voice proof: scratch guest {a[:8]} deleted (HTTP {s})")
