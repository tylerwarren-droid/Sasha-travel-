"""Sasha 381k · TWO GATE RUNS NEVER SHARE A TEST IDENTITY. Found by 6da7a18b's two builds (55068c85 + ccb3af9a, row 1998): both gates
ran at the same minute and linked the SAME fixed WhatsApp numbers (+3461000000n) to their own scratch guests — guest_whatsapp's link
deletes any channel already on that number, so each run took the other's mobile and the airline's hold said mobile_needed.

ONE rule for every gate suite that links a shared identity: it comes from THIS run (Railway's deployment id, else a fresh id per
process) — never a fixed one. And a number already linked to anyone is never used (the link would remove their channel): the next.

The identities the gate suites use, and why only the voice loop's needed this (as of 381k):
  · voice_loop_suite — a WhatsApp CHANNEL per check (GW.STORE.link: one channel per number, across accounts) → run_mobile() here.
  · agent_suite, basket_suite, flight_suite, venue_suite, say_show_suite — a mobile on the scratch guest's OWN booking contact (a row per
    account, nothing shared, nothing unique by number) — no collision; left as they are.
  · every suite's guest — GA.create_guest: a fresh account and email per call (guest-<random>@guests.kanoe.ai) — already per run.
  · venue_suite / her_voice_suite / venue_truth_suite's door (VS.TAP / VS.WA) — ContextVars in the gate's own process, never stored.
  · the venue engine's fake (venue_engine_fake) — in process; its ids (act_gate, cpl_gate) never leave it."""
from __future__ import annotations

import hashlib
import os
import uuid

RUN = os.getenv("RAILWAY_DEPLOYMENT_ID", "").strip() or uuid.uuid4().hex   # THIS run — two builds never share it


def mobile_for(run: str, n: int, attempt: int = 0) -> str:
    """A Spanish mobile a supplier accepts (+346 + 8 digits), derived from the run, the check and the attempt."""
    h = int(hashlib.sha256(f"{run}|{attempt}".encode()).hexdigest()[:10], 16) % 100000
    return f"+346{h:05d}{n % 1000:03d}"


async def run_mobile(n: int, taken) -> str:
    """THIS run's mobile for check n — never one already linked to anyone (`taken(number) -> bool`, the store's own lookup)."""
    for attempt in range(20):
        number = mobile_for(RUN, n, attempt)
        if not await taken(number):
            return number
    raise RuntimeError("no free test mobile for this run — nothing linked")
