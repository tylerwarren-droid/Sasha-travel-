"""Sasha 366 · A GROUP TRIP'S WORK RUNS ON THE SERVER, from the trip record, whatever door started it — never driven by a page being open.

Found (Tyler, 10 Nov 19:35, WhatsApp, Jean Incorporated): "Book all executives to Lisbon 9-12 December" → "…I'll tell you as it goes, and when
it's done." Then nothing. The trip was planned (12 rows by 18:35:50) — but the mandate told only the S2 page's stream (live_events), so
WhatsApp heard nothing; and its work lived only in this process's memory (a restart would lose it).

ONE source: the mandate ON THE TRIP RECORD (rules.mandate) + ONE server worker (mandate.sweep, started with the app) that advances every open
one — and reports to the door that started it (booking_signer.channel: WhatsApp messages, the S2 live line).

    cd backend && python -m unittest tests.test_s366_server_worker -v
"""
from __future__ import annotations

import asyncio
import pathlib
import unittest
from unittest import mock

from agapi import v0 as API
from booking_signer import groups as G, live_events as LE, mandate as M
from tests import test_s339_book_all as W339, test_s365_mandate as T365

run = asyncio.run
OWNER = W339.OWNER
ROOT = pathlib.Path(__file__).resolve().parents[2]


class World(W339.World):
    def __enter__(self):
        super().__enter__()
        self.wa = []

        async def wa_send(account, text):   # their WhatsApp, captured (never sent from a test)
            self.wa.append(text)
            return "sent (captured)"
        for p in (mock.patch.object(G, "HOTELS", G._hotel_search), mock.patch.object(LE, "WA_SEND", wa_send),
                  mock.patch.dict(M._RUNS, {}, clear=True)):
            p.start()
            self.p.append(p)
        T365._executives(T365.SIX)
        return self


def _on_whatsapp(said=T365.SAID):
    """The WhatsApp door, as its brain calls the tool — and NO page open (nobody subscribed to the S2 stream)."""
    async def go():
        from booking_signer import channel as CH
        await CH.used(OWNER, CH.WA)                                                        # their last turn: WhatsApp
        from agapi import venue_submit as VS
        VS.WA.set({"wa_id": "34611000099", "message_id": "SM" + "a" * 32})   # the signed inbound, as the webhook sets it (367: the proof)
        ctx = API.Ctx(account=OWNER, user_said=said, surface="s2", via="wa", session="s366-session")
        r = await API.call(ctx, "group_select", {"change": "new", "destination": "London", "starts_on": "2026-12-15", "ends_on": "2026-12-17",
                                                 "roles": ["executives"]})
        await M.finished(OWNER)
        return r
    return run(go())


class NoClientAttached(unittest.TestCase):
    def test_whatsapp_hears_the_progress_and_the_one_finish_unasked(self):
        with World() as w:
            self.assertFalse(LE._SUBS.get(OWNER))                                           # no page open anywhere
            r = _on_whatsapp()
            mv = run(G.store().movement(OWNER))
        self.assertTrue(r["ok"], r)
        self.assertTrue(any(x.startswith("Planned 6 of 6") and "Hotel: 6 rooms at" in x for x in w.wa), w.wa)   # progress, unasked
        self.assertTrue(any(x.startswith("Booking 6 now") for x in w.wa), w.wa)
        fins = [x for x in w.wa if "booked (TEST)." in x]
        self.assertEqual(len(fins), 1, w.wa)                                                # the ONE finish, on WhatsApp
        self.assertTrue(fins[0].startswith("All 6 booked (TEST)."), fins[0])
        self.assertEqual((mv["rules"].get("mandate") or {}).get("state"), "done")         # the record says it's finished

    def test_a_restart_never_loses_it(self):
        """The mandate is ON THE RECORD: a process that never ran it (a restart) finds it and carries it through."""
        with World() as w:
            async def go():
                from booking_signer import channel as CH
                await CH.used(OWNER, CH.WA)
                from agapi import venue_submit as VS
                VS.WA.set({"wa_id": "34611000099", "message_id": "SM" + "b" * 32})
                ctx = API.Ctx(account=OWNER, user_said=T365.SAID, surface="s2", via="wa", session="s366-session")
                with mock.patch.object(M, "_start", lambda *a, **k: None):           # the process that took it dies before running it
                    await API.call(ctx, "group_select", {"change": "new", "destination": "London", "starts_on": "2026-12-15",
                                                         "ends_on": "2026-12-17", "roles": ["executives"]})
                await G.planned(OWNER)
                G._PLANNING.clear()
                M._RUNS.clear()                                                         # … a new process: nothing in memory
                self.assertEqual(((await G.store().movement(OWNER))["rules"].get("mandate") or {}).get("state"), "running")
                await M.sweep()                                                         # the ONE server worker, from the record
                await M.finished(OWNER)
            run(go())
        self.assertEqual(len([x for x in w.wa if x.startswith("All 6 booked (TEST).")]), 1, w.wa)


class ARefusedMandateIsSaid(unittest.TestCase):
    def test_nothing_booked_and_said_plainly(self):
        """Sasha 367 · AgAPI refusing the instruction's mandate (a proof it doesn't trust): said, never "not booked just now", nothing booked."""
        with World() as w:
            with mock.patch.object(w.agapi, "_proof_ok", lambda body: False):
                r = _on_whatsapp()
        self.assertIn("didn't accept your instruction as the yes", r["result"]["say"])
        self.assertEqual([op for op, _ in w.agapi.calls if op == "group.book"], [])


class OneRunnerPerMandate(unittest.TestCase):
    def test_another_runners_lease_is_respected_and_an_expired_one_taken_over(self):
        """Sasha 367 · found by the WhatsApp proof: a second process ran the same mandate beside the server's worker."""
        import time
        with World() as w:
            async def go():
                from booking_signer import channel as CH
                from agapi import venue_submit as VS
                await CH.used(OWNER, CH.WA)
                VS.WA.set({"wa_id": "34611000099", "message_id": "SM" + "c" * 32})
                ctx = API.Ctx(account=OWNER, user_said=T365.SAID, surface="s2", via="wa", session="s366-lease")
                with mock.patch.object(M, "_start", lambda *a, **k: None):
                    await API.call(ctx, "group_select", {"change": "new", "destination": "London", "starts_on": "2026-12-15",
                                                         "ends_on": "2026-12-17", "roles": ["executives"]})
                mv = await G.store().movement(OWNER)
                md = mv["rules"]["mandate"]
                await G.store().set_rule(OWNER, mv["id"], "mandate", {**md, "lease": {"by": "another:1", "until": time.time() + 600}})
                M._RUNS.clear()
                held = await M.sweep()                                                      # another runner holds it: stood back
                await G.store().set_rule(OWNER, mv["id"], "mandate", {**md, "lease": {"by": "another:1", "until": time.time() - 1}})
                taken = await M.sweep()                                                     # its lease ran out: taken over
                await M.finished(OWNER)
                return held, taken
            held, taken = run(go())
        self.assertEqual((held, taken), (0, 1))
        self.assertEqual(len([x for x in w.wa if x.startswith("All 6 booked (TEST).")]), 1, w.wa)


class OneSource(unittest.TestCase):
    def test_one_worker_started_with_the_app_and_no_door_of_its_own(self):
        routes = (ROOT / "backend" / "booking_signer" / "routes.py").read_text()
        self.assertIn("_mandate.start()", routes)                                            # the server's own loop
        src = (ROOT / "backend" / "booking_signer" / "mandate.py").read_text()
        self.assertIn("CH.tell(", src)                                                      # the finish: the ONE send to the right door
        self.assertNotIn('_publish(account, "group_done"', src)                             # the finish never only on the page's stream
        for f in ("booking_signer/wa_agent.py", "booking_signer/guest_whatsapp.py", "products/whatsapp.py"):
            self.assertNotIn("mandate", (ROOT / "backend" / f).read_text(), f)              # no WhatsApp loop or kick of its own


if __name__ == "__main__":
    unittest.main()
