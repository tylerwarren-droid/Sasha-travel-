"""Sasha 194 · THE DEPLOY GATE (Railway preDeployCommand): the flight suite, then the core-flow suites (itinerary, restaurant,
spa, spaces). Any failure → exit 1 → Railway keeps the old deploy. SASHA_FLIGHT_SUITE=skip skips both (said in the log).
Sasha 198 · DETERMINISTIC: Duffel is replayed from recorded fixtures (scripts/duffel_fake.py) — a Duffel timeout, rate limit or
withdrawn fare can no longer block a deploy. SASHA_GATE_DUFFEL=live runs it against Duffel TEST instead; the live suite also runs
on a schedule (scripts/live_suite.py), alerting without blocking."""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scripts import gate_cost as COST  # noqa: E402   # Sasha 232 · the gate's own Anthropic key — BEFORE any client is built
COST.use_gate_key()
COST.install()
# Sasha 353 · THE GATE REPLAYS RECORDED REPLIES: the model calls of its suites are answered from the record (booking_signer.model_gateway),
# never the API — one tiny live check only (the preflight's 1-token Haiku call). SASHA_GATE_RECORD=1 → ONE live run that records them
# (set it once, after a prompt or a tool changes what the suites ask; a request with no recording fails the gate by name).
from booking_signer import model_gateway as _MG  # noqa: E402
_MG.install()


def _replay_mode() -> None:
    """Set when the gate RUNS (main) — never at import: a test importing this module must not change how its process calls the model."""
    os.environ["SASHA_MODEL_REPLAY"] = "record" if os.getenv("SASHA_GATE_RECORD", "").strip() == "1" else "replay"
    print(f"gate: model calls {'RECORDED live (SASHA_GATE_RECORD=1)' if os.environ['SASHA_MODEL_REPLAY'] == 'record' else 'replayed from the record — one live Haiku check only'}")
from scripts import flight_suite as F, core_suites as C, basket_suite as BS, agent_suite as AS, whatsapp_suite as WS, postgres_suite as PG, \
    voice_loop_suite as VS, venue_suite as VN  # noqa: E402


async def _clean_orphans(since) -> None:
    """Sasha 203 · the suites' scratch guests are deleted, and their payment events lose their item (on delete set null):
    THIS run's orphaned order events go too. Real Duffel webhooks (duffel_webhook) are never touched."""
    try:
        from booking_signer import plan_store as PS
        run = PS._run()
        n = await run(lambda c: c.execute("delete from basket_events where item_id is null and source = 'duffel_order' and received_at >= $1", since))
        print(f"gate: scratch order events cleaned ({n})")
    except Exception as e:
        print(f"gate: scratch order events NOT cleaned: {type(e).__name__}")


async def main() -> int:
    _replay_mode()   # Sasha 353
    # Sasha 257 · FIRST: can the model answer at all? An exhausted Anthropic credit stops the gate here, by name (and the founder is
    # told) — before, it failed 40 unrelated-looking checks and production went silent with nobody told
    from app.services import model_health as MH
    ok, why = await MH.preflight()
    print(f"gate: model preflight — {why}")
    if not ok:
        await MH.alert("the deploy gate's preflight")
        print(f"GATE FAIL · {why}")
        return 1
    from scripts import places_fake   # Sasha 213 · NO live Google Places from a suite (it costs money) — the founder's say-so only
    places_fake.install()
    # Sasha 247 · the gate's test bookings never go in the LIVE outcomes ledger (found by CR: after the switch, the restart's gate
    # recorded its test venue bookings live) — the gate runs with production's environment, so the ledger is pinned to the sandbox here
    os.environ["SASHA_OUTCOMES_VIA"] = "sandbox"
    # Sasha 249 · outcomes is a family of the one route table now: the table wins over the legacy switch, so it is pinned there too
    os.environ["SASHA_AGAPI_ROUTE"] = (os.getenv("SASHA_AGAPI_ROUTE", "") + ",outcomes=sandbox").lstrip(",")
    from agapi import venue_submit as _VSB
    real_call = _VSB.CALL   # Sasha 321 · AgAPI's real sender, for the voice proof after the verdict
    from agapi import venue_truth as _VTR
    real_engine = _VTR.CALL   # … and its real venue read
    from scripts import venue_engine_fake   # Sasha 248 · the venue engine's saved answers: no AgAPI read from a suite
    venue_engine_fake.install(submit=True)   # Sasha 254 · + the booking sender: nothing reaches AgAPI live
    # Sasha 254 item 5 · the access record: every gate guest is a scratch account with no person_access row, so it reads CLOSED
    # (test, everything off) — answered here, in this process, with no users.register / access.get on agapi-live (no gate end
    # users on live). A suite that needs a power installs a record for its own guest (person_access.install), never a real grant.
    from agapi import person_access as PA
    PA.RESOLVER = lambda account: {**PA.CLOSED, "mailboxes": [], "source": "gate"}
    from datetime import datetime, timezone
    since = datetime.now(timezone.utc)
    if os.getenv("SASHA_GATE_DUFFEL", "fixtures") != "live":
        from scripts import duffel_fake
        duffel_fake.install()
    a = await F.main()
    b = await C.main()
    c = await BS.main()   # Sasha 198 · the trip basket (grows R2 → R10)
    d = await AS.main()   # Sasha 203 · the agent's tools (AgAPI v0) in the real database
    v = await VS.main()   # Sasha 210 · ten scripted voice conversations: plan → flights → "book it" → the payment link on the phone
    w = await VN.main()   # Sasha 211 · venue bookings on the agent, every route (our test venue for real; the rest stand-in)
    await _clean_orphans(since)
    e = await __import__("asyncio").to_thread(WS.main)   # Sasha 206 · WhatsApp: spaces, R1, R2, the guest pipeline (offline)
    f = await __import__("asyncio").to_thread(PG.main)   # Sasha 207 · the stores on a real, throwaway Postgres (never production)
    from scripts import demo_safety_suite as DS   # Sasha 215 · CR 56 + the safety items: the yes, outages, once-only acts (offline)
    s = await __import__("asyncio").to_thread(DS.main)
    from scripts import venue_truth_suite as VTS   # Sasha 248 · ONE VENUE TRUTH: the three demo paths (Spanish not "Korean", the form, the sheet)
    t = 0 if await VTS.main() else 1
    from scripts import her_voice_suite as HV   # Sasha 249 · her voice: no channel named, one question per detail
    h = 0 if await HV.main() else 1
    from scripts import one_truth_suite as OT   # Sasha 249 · the consistency test, T1–T14 (EU 245)
    o = await __import__("asyncio").to_thread(OT.main)
    COST.report()   # Sasha 232 · what this run spent on the model
    # Sasha 249 · ONE VERDICT: the line printed and the exit code are the same expression (the safety suite was printed, never failed)
    bad = bool(a or b or c or d or v or w or e or f or s or t or h or o)
    print(f"\nDEPLOY GATE: {'PASS' if not bad else 'FAIL'}")
    if not bad and os.getenv("SASHA_GATE_LOOP5_PROBE", "on") != "off" and os.environ.get("SASHA_MODEL_REPLAY") != "replay":   # 353: replies
        # replayed are the same every run — the probe measures a live model's variance, so it runs only when recording   # Sasha 323 · after the verdict, never part of it: VOICE LOOP 5
        try:                                                                 # run until it fails once — its whole conversation printed
            await VS.probe("5 ·", int(os.getenv("SASHA_GATE_LOOP5_RUNS", "6")))
        except Exception as e:
            print(f"loop 5 probe: ⚠ {type(e).__name__}: {e}")
    if not bad and os.environ.get("SASHA_MODEL_REPLAY") == "replay":   # Sasha 353 · the deploy's ONE live call is the preflight's; the voice
        print("voice proof: skipped — the gate replays recorded replies (it runs when the gate records: SASHA_GATE_RECORD=1)")   # proof
    elif not bad:   # Sasha 321 · after the verdict, never part of it: one voice-avatar booking at the test venue on the REAL sandbox
        from scripts import voice_proof
        try:
            await voice_proof.run(real_call, real_engine)
        except Exception as e:
            print(f"voice proof: ⚠ {type(e).__name__}")
    if not bad:   # Sasha 327 · after the verdict, never part of it: pay in one tap on Stripe TEST (its own test cards)
        from scripts import pay_proof
        try:
            await pay_proof.run()
        except Exception as e:
            print(f"pay proof: ⚠ {type(e).__name__}: {e}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
