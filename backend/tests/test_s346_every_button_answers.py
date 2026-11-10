"""Sasha 346 · EVERY /group button answers — from the record, never silent (docs/sasha/S-346-every-button-answers.md).
    cd backend && python -m unittest tests.test_s346_every_button_answers -v
"""
from __future__ import annotations

import asyncio
import pathlib
import re
import unittest
from unittest import mock

from agapi import s2_keep as KEEP
from booking_signer import group_book as GB, group_outcome as GO, groups as G
from tests import test_s334 as W334

run = asyncio.run
OWNER = W334.OWNER
NOBODY = "00000000-0000-4000-8000-000000000346"   # an organiser with no movement
ROOT = pathlib.Path(__file__).resolve().parents[2]


def go(action, **a):
    return run(GO.run(OWNER, action, a))


class World(W334.World):
    def __enter__(self):
        super().__enter__()
        p = mock.patch.dict(GB._JOBS, {}, clear=True)
        p.start()
        self.p.append(p)
        return self

    def names(self):
        return [m["name"] for m in self.members()]


class BookAll(unittest.TestCase):
    def test_nobody_bookable_says_why_with_the_invite(self):
        with World() as w:
            for m in w.members():
                run(KEEP.delete(m["person_id"]))                                                     # nobody's passport in
            out = go("book")
            self.assertEqual((out["done"], out["say"]), (False, "0 can be booked: 20 are waiting for their passport."))
            self.assertEqual([(t["label"], len(t["invite"])) for t in out["taps"]], [("Invite", 20)])
            self.assertEqual((GB._JOBS, w.agapi.supplier), ({}, []))                          # nothing started, nothing booked

    def test_some_bookable_starts_the_one_job_and_says_who_is_held(self):
        """Sasha 365 · the tap IS the instruction: the mandate books everyone inside the limits on its own and finishes with ONE grouped
        question about the held ones — the record's reasons (Hanna: no passport) and AgAPI's (Rania: over the limit), each once."""
        from booking_signer import live_events as LE, mandate as M
        with World() as w:
            hanna = next(m for m in w.members() if m["name"] == "Hanna Dummy")
            run(KEEP.delete(hanna["person_id"]))

            async def both():
                q = LE.subscribe(OWNER)
                out = await GO.run(OWNER, "book", {})
                await M.finished(OWNER)
                evs = []
                while not q.empty():
                    evs.append(q.get_nowait())
                LE.unsubscribe(OWNER, q)
                return out, evs
            out, evs = run(both())
            self.assertEqual((out["done"], out["status"]), (True, "booking"))
            self.assertTrue(out["say"].startswith("On it"))
            fin = [e["text"] for e in evs if e.get("type") == "group_done"][0]
            self.assertTrue(fin.startswith("18 of 20 booked (TEST)."), fin)
            self.assertEqual(fin.count("?"), 1, fin)                                            # ONE grouped question (Rania) …
            self.assertIn("Rania Mithal: over the company's limit", fin)
            self.assertIn("No email on the list for Hanna Dummy — their passport link is on the Group page", fin)   # … Hanna: invited, said
            self.assertNotIn("Hanna Dummy:", fin)

    def test_everyone_booked_says_so(self):
        with World() as w:
            run(w.tap(run(GB.prepare(OWNER, "book"))["read_back_id"]))
            run(w.tap(run(GB.prepare(OWNER, "book", ["Rania Mithal"], over_ok=True))["read_back_id"]))
            self.assertEqual(go("book")["say"], "0 can be booked: 20 already booked.")


class Swap(unittest.TestCase):
    def test_each_missing_field_is_named(self):
        with World():
            self.assertEqual((go("swap")["say"], go("swap")["missing"]), ("Swap needs who leaves and who comes.", ["who leaves", "who comes"]))
            self.assertEqual(go("swap", who=["Bruno Example"])["say"], "Swap needs who comes.")
            self.assertEqual(go("swap", who=[""], to="Zoe Newhire")["say"], "Swap needs who leaves.")
            out = go("swap", who=["Bruno Example"], to="Zoe Newhire")
            self.assertEqual(out["missing"], ["their home city"])
            self.assertTrue(out["say"].startswith("Swap needs Zoe Newhire's home city — they're not on the list yet"), out["say"])
            self.assertEqual(go("swap", who=["Nobody Here"], to="Zoe Newhire")["say"], "Nobody Here isn't on the list — check the name of who leaves.")

    def test_nothing_booked_swaps_on_the_list_and_plans_the_newcomer(self):
        with World() as w:
            bruno = next(m for m in w.members() if m["name"] == "Bruno Example")
            out = go("swap", who=["Bruno Example"], to="Zoe Newhire", to_city="Lyon")
            self.assertEqual((out["done"], out["status"]), (True, "swapped_on_list"), out["say"])
            self.assertNotIn("Bruno Example", w.names())
            zoe = next(m for m in w.members() if m["name"] == "Zoe Newhire")
            self.assertEqual((zoe["home_city"], str(zoe["out_date"]), str(zoe["back_date"]), zoe["grade"]),
                             ("Lyon", str(bruno["out_date"]), str(bruno["back_date"]), bruno["grade"]))   # the leaver's place
            row = out["row"]
            self.assertEqual(row["name"], "Zoe Newhire")
            self.assertTrue(row["transport"] and row["price_eur"], row)                         # the new row, planned
            self.assertTrue(out["say"].startswith("Swapped on the list: Bruno Example is off (nothing was booked for them); Zoe Newhire is on"))
            self.assertIn("Planned:", out["say"])
            self.assertEqual(w.agapi.supplier, [])
            self.assertEqual(go("swap", who=["Zoe Newhire"], to="Ana Example")["done"], False)     # both already on the list: said

    def test_a_booking_is_swapped_through_agapi_as_before(self):
        with World() as w:
            run(w.tap(run(GB.prepare(OWNER, "book"))["read_back_id"]))
            out = go("swap", who=["Bruno Example"], to="Zoe Newhire", to_city="Lyon")
            self.assertEqual((out["done"], out["status"]), (True, "needs_vault"))               # her vault first (Sasha 336)
            self.assertIn("Bruno Example", w.names())                                           # a booked leaver stays until AgAPI swaps


class CancelInviteInvoiceAdd(unittest.TestCase):
    def test_cancel(self):
        with World():
            self.assertEqual(go("cancel")["say"], "Cancel needs who to cancel.")
            self.assertEqual(go("cancel", who=["Bruno Example"])["say"], "0 can be cancelled: Bruno Example has no booking.")

    def test_invite(self):
        with World() as w:
            self.assertEqual(go("invite")["say"], "Nobody to invite: all 20 people have their passport in the vault.")
            hanna = next(m for m in w.members() if m["name"] == "Hanna Dummy")
            run(KEEP.delete(hanna["person_id"]))
            out = go("invite")
            self.assertTrue(out["done"])
            self.assertTrue(out["say"].startswith("Invited 1 person:"), out["say"])
            self.assertEqual(go("invite", who=["Nobody Here"])["say"], "Nobody Here isn’t on the list — check the name.")

    def test_invoice(self):
        with World() as w:
            out = go("invoice")
            self.assertEqual((out["done"], out.get("link")), (False, None))
            self.assertTrue(out["say"].startswith("Nothing is booked yet"))
            run(w.tap(run(GB.prepare(OWNER, "book"))["read_back_id"]))
            out = go("invoice")
            self.assertTrue(out["done"] and out["link"])
            self.assertRegex(out["say"], r"^The invoice KAN-\w+-TEST for .+: 19 people booked, total €[\d,.]+ \(TEST\)\.$")

    def test_add_these(self):
        with World() as w:
            self.assertEqual(go("add", rows=None)["missing"], ["the list — paste it (Name, home city, out, back, grade — one per line) or choose a file"])
            self.assertTrue(go("add", rows=[])["say"].startswith("Add these needs the list"))
            out = go("add", rows=G.read_text("Nina Newline, Lisbon, 2026-12-01, 2026-12-19, worker"))
            self.assertEqual((out["done"], out["say"]), (True, "Added 1 person to the list."))
            self.assertIn("Nina Newline", w.names())


class NeverSilent(unittest.TestCase):
    def test_no_movement_is_said_by_every_action(self):
        with World():
            args = {"swap": {"who": ["A"], "to": "B"}, "cancel": {"who": ["A"]}, "add": {"rows": [{"name": "A"}]}}
            for a in GO.ACTIONS:
                if a in ("person_add", "person_edit", "documents", "open", "create", "select", "confirm", "archive"):   # Sasha 351 · the roster's actions need a company, not a trip; open: its own words; Sasha 358 · create MAKES the trip
                    continue
                out = run(GO.run(NOBODY, a, {**args, "choose": {"who": ["A"]}, "switch": {"person": "A"}}.get(a, {})))
                want = "There's no trip yet — tell me where, when and the hotel area first." if a in ("choose", "switch") else GO.NO_MOVEMENT
                self.assertEqual((out["done"], out["say"]), (False, want), a)

    def test_the_one_exit_never_answers_empty(self):
        with self.assertLogs("booking_signer.group_outcome", "ERROR"):
            out = GO.answered("book", {"done": True})
        self.assertTrue(out["say"].startswith("Book: Sasha has no answer to show"))
        self.assertEqual(run(GO.run(OWNER, "explode", {}))["say"], "Sasha doesn't know the action “explode”.")

    def test_an_exception_is_said_never_a_success(self):
        with World(), mock.patch.object(GO, "_HOW", {**GO._HOW, "invite": mock.AsyncMock(side_effect=RuntimeError())}):
            out = go("invite")
        self.assertEqual((out["done"], out["say"]), (False, "Invite didn't go through (RuntimeError) — nothing was changed. Try again."))


class OnePlace(unittest.TestCase):
    """The page's routes and the chat's tools ask the ONE outcome — none decides on its own (that would be a PATCH)."""

    def test_the_routes(self):
        src = (ROOT / "backend/booking_signer/group_routes.py").read_text()
        for route in ("/act", "/invite", "/invoice", "/upload"):
            body = src[src.index(f'@router.{"get" if route == "/invoice" else "post"}("{route}")'):]
            body = body[:body.index("\n@", 1)]
            self.assertIn("GO.run(", body, route)
            for direct in ("GB.prepare(", "GB.start(", "TV.invite(", "G.upload(", "GB.invoice("):
                self.assertNotIn(direct, body, f"{route} decides on its own: {direct}")

    def test_the_chat_tools(self):
        src = (ROOT / "backend/agapi/v0.py").read_text()
        for tool, action in (("group_book", "book"), ("group_swap", "swap"), ("group_cancel", "cancel"), ("group_invite_vault", "invite"),
                             ("group_invoice", "invoice"), ("group_upload", "add")):
            body = src[src.index(f"async def {tool}("):]
            body = body[:body.index("\nasync def ", 1)]
            self.assertIn(f'_GO().run(ctx.account, "{action}"', body, tool)
            for direct in ("GB.prepare(", "TV.invite(", "G.upload(", "GB.invoice("):
                self.assertNotIn(direct, body, f"{tool} decides on its own: {direct}")

    def test_the_page_holds_no_press_back(self):
        page = (ROOT / "frontend/app/components/group/GroupView.tsx").read_text()   # Sasha 358 · the page renders the ONE group view
        code = re.sub(r"/\*[\s\S]*?\*/|(^|[^:])//[^\n]*", r"\1", page)
        self.assertNotIn("disabled=", code)                                                    # a grey button says nothing
        self.assertNotIn("window.open", code)                                                  # a pop-up after a wait is blocked: nothing
        # each press, told: every button's onClick is press(…) — the switch's own button takes onPress, and every switch is given press(…)
        self.assertEqual(len(re.findall(r"<button\b", code)), len(re.findall(r"<button\b[^>]*onClick=\{(?:press\(|onPress\})", code)))
        self.assertEqual(len(re.findall(r"<Switch\b", code)), len(re.findall(r"<Switch\b[^>]*onPress=\{press\(", code)))
        for name in ("post", "invoice", "act", "answer"):
            fn = code[code.index(f"const {name} = async"):]
            fn = fn[:fn.index("\n  }\n")]
            self.assertIn("heard(", fn, f"{name}: an answer not read by the ONE reader")

    def test_every_page_that_acts_is_checked(self):
        chk = (ROOT / "frontend/scripts/check-outcome-surfaces.mjs").read_text()
        self.assertIn('"app/group/page.tsx"', chk)
        self.assertIn("const surfaces = [...new Set([...OUTCOME_SURFACES, ...actingPages()])];", chk)   # found, not remembered — no exceptions
        self.assertNotIn("NOT_YET_CLEAN", chk)                                                   # Sasha 347 · the debt list is gone


if __name__ == "__main__":
    unittest.main()
