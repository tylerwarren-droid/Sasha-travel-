"""Sasha 359 · WHO GOES IS CHOSEN BY DESCRIPTION — through the ONE group engine (358), from every door (S2, /next, WhatsApp, /group).
Tyler 7 Nov: "I want to choose people by description. I want the user to be able to converse naturally with Sasha to plan their trip."

The model only PROPOSES a structured filter (roles / grades / names in or out / "last trip" / everyone); groups.resolve applies it to the
roster deterministically and names every word it couldn't match ("no one called Javier Prieto — did you mean Javier Moreno?");
groups.propose shows the list for a yes; groups.confirm — and only it — then makes the trip or changes it (create_trip / set_on_trip).

    cd backend && python -m unittest tests.test_s359_by_description -v
"""
from __future__ import annotations

import asyncio
import pathlib
import re
import unittest
from unittest import mock

from agapi import v0 as API
from booking_signer import group_outcome as GO, groups as G
from tests import test_s332 as W

run = asyncio.run
OWNER = W.OWNER
ROOT = pathlib.Path(__file__).resolve().parents[1]
COMPANY = "Acme Components (fictional)"
CITIES = list(W.FARE)
PEOPLE = [("Ana Garcia", "executive"), ("Bruno Costa", "executive"), ("Carla Dias", "executive"), ("Javier Moreno", "executive"),
          ("Marta Ruiz", "engineer"), ("Nuno Alves", "engineer"), ("Olga Pires", "engineer"), ("Pedro Sousa", "technician"),
          ("Rita Lopes", "intern"), ("Sara Neves", "intern")]


def _in_world(scenario):
    with W.World() as w:
        return run(scenario(w))


async def _roster():
    await GO.run(OWNER, "person_add", {"rows": [{"name": n, "role": r, "home_city": CITIES[i], "grade": "worker"} for i, (n, r) in enumerate(PEOPLE)],
                                       "company": COMPANY})


def names(r):
    return sorted(p["name"] for p in r["people"])


class TheResolver(unittest.TestCase):
    def test_a_description_becomes_people_deterministically_and_every_miss_is_named(self):
        async def go(w):
            await _roster()
            r = await G.resolve(OWNER, {"roles": ["executives"]})
            self.assertEqual(names(r), ["Ana Garcia", "Bruno Costa", "Carla Dias", "Javier Moreno"])
            r = await G.resolve(OWNER, {"roles": ["executives"], "names_out": ["Javier Prieto"]})
            self.assertEqual(len(r["people"]), 4)                                           # never guessed: Prieto is nobody here
            self.assertEqual(r["unmatched"][0]["word"], "Javier Prieto")
            self.assertIn("Javier Moreno", r["unmatched"][0]["did_you_mean"])
            self.assertIn("no one called Javier Prieto — did you mean Javier Moreno?", r["said"])
            r = await G.resolve(OWNER, {"roles": ["engineers"], "names_in": ["Marta"], "names_out": ["Olga Pires"]})
            self.assertEqual(names(r), ["Marta Ruiz", "Nuno Alves"])                         # a first name that is one person: them
            r = await G.resolve(OWNER, {"roles": ["pilots"]})
            self.assertEqual(r["people"], [])
            self.assertIn("pilot", r["said"])                                                # a role nobody has: said, with the roles there are
            self.assertIn("executive", r["said"])
            r = await G.resolve(OWNER, {"everyone": True, "roles": ["intern"], "exclude_roles": True})
            self.assertEqual(len(r["people"]), 8)                                            # "everyone but the interns"
        _in_world(go)

    def test_same_people_as_last_time(self):
        async def go(w):
            await _roster()
            first = (await G.resolve(OWNER, {"roles": ["engineer"]}))["people"]
            p = await G.propose(OWNER, "new", {"roles": ["engineer"]}, {"destination": "Porto", "starts_on": "2026-12-01", "ends_on": "2026-12-03"})
            await G.confirm(OWNER, p["proposal_id"])
            await G.planned(OWNER)
            r = await G.resolve(OWNER, {"last_trip": True})
            self.assertEqual(names(r), sorted(x["name"] for x in first))
        _in_world(go)


class ProposeThenYes(unittest.TestCase):
    def test_nothing_changes_before_the_yes_then_exactly_the_list(self):
        async def go(w):
            await _roster()
            before = len(w.store.movements)
            p = await G.propose(OWNER, "new", {"roles": ["executives"], "names_out": ["Javier Moreno"]},
                                {"destination": "Lisbon", "starts_on": "2026-11-24", "ends_on": "2026-11-27"})
            self.assertEqual(len(w.store.movements), before)                                 # a proposal makes nothing
            self.assertIn("Ana Garcia", "\n".join(p["read_back"]))
            self.assertNotIn("Javier Moreno", "\n".join(p["read_back"]))
            self.assertTrue(p["ask"].endswith("?"))
            r = await G.confirm(OWNER, p["proposal_id"])
            self.assertTrue(r["done"], r)
            await G.planned(OWNER)
            st = await G.state(OWNER)
            self.assertEqual((st["trip"]["destination"], sorted(x["name"] for x in st["roster"] if x["on"])),
                             ("Lisbon", ["Ana Garcia", "Bruno Costa", "Carla Dias"]))
            again = await G.confirm(OWNER, p["proposal_id"])                                  # a yes is used once
            self.assertFalse(again["done"])
            # then, on that trip: "add Marta", "drop the interns" (none on it: said), "add the interns" → "drop the interns"
            for mode, f, want in (("add", {"names_in": ["Marta"]}, 4), ("add", {"roles": ["interns"]}, 6), ("drop", {"roles": ["interns"]}, 4)):
                p = await G.propose(OWNER, mode, f)
                await G.confirm(OWNER, p["proposal_id"])
                await G.planned(OWNER)
                self.assertEqual(sum(x["on"] for x in (await G.state(OWNER))["roster"]), want, (mode, f))
            p = await G.propose(OWNER, "drop", {"roles": ["interns"]})
            self.assertIn("nobody", p["say"].lower())                                         # none of them on it: said, nothing to confirm
        _in_world(go)

    def test_asks_only_whats_missing_one_at_a_time(self):
        async def go(w):
            await _roster()
            self.assertEqual((await G.propose(OWNER, "new", {"roles": ["executive"]}, {}))["ask"], "Where to?")
            self.assertEqual((await G.propose(OWNER, "new", {"roles": ["executive"]}, {"destination": "Lisbon"}))["ask"], "Which dates?")
            self.assertEqual((await G.propose(OWNER, "new", {}, {"destination": "Lisbon", "starts_on": "2026-11-24", "ends_on": "2026-11-27"}))["ask"],
                             "Who's going?")
        _in_world(go)


class TheChatDoors(unittest.TestCase):
    """S2, /next and WhatsApp share ONE brain: group_select (the model's structured filter → the engine's list, a card with Yes / No) and
    group_confirm (only on the person's own yes)."""

    def test_select_then_confirm_only_on_their_yes(self):
        """Sasha 365 · the instruction IS the yes: who / where / when complete and every word matched → the trip is made at once (no card).
        A word the engine couldn't match is a MISSING FACT: the ONE question (the list, Yes / No); group_confirm only on their answer."""
        from app.agent import sasha as S

        async def go(w):
            await _roster()
            ctx = API.Ctx(account=OWNER, user_said="plan a Lisbon retreat 24–27 Nov for all the executives minus Javier Moreno")
            done = await API.group_select(ctx, {"change": "new", "destination": "Lisbon", "starts_on": "2026-11-24", "ends_on": "2026-11-27",
                                                "roles": ["executives"], "names_out": ["Javier Moreno"]})
            self.assertTrue(done.get("done"), done)                                            # made, planned — no question
            self.assertNotIn("?", done["say"])
            self.assertIsNone(S.render("group_select", done, {}))                              # no card waiting for a yes
            ctx = API.Ctx(account=OWNER, user_said="plan a Porto trip 1–3 Dec for the executives minus Javier Prieto")
            r = await API.group_select(ctx, {"change": "new", "destination": "Porto", "starts_on": "2026-12-01", "ends_on": "2026-12-03",
                                             "roles": ["executives"], "names_out": ["Javier Prieto"]})
            self.assertTrue(r.get("unmatched"))                                                # nobody called Javier Prieto: asked
            ev = S.render("group_select", r, {})
            self.assertEqual(ev["kind"], "read_back")
            self.assertEqual([c["route"] for c in ev["choices"]], ["say:Yes, these people", "say:No"])   # a tap sends the words (WhatsApp too)
            from booking_signer import guest_whatsapp as GW, wa_agent as WA
            out = GW.Out()
            WA._read_back(ev, out)                                                             # WhatsApp: the list and its buttons, ONE message
            kind, body, buttons = out.items[0][:3]
            self.assertEqual(kind, "ask")
            self.assertIn("Ana Garcia", body)
            with self.assertRaises(API.ToolError):                                             # not their answer: nothing made
                await API.group_confirm(API.Ctx(account=OWNER, user_said="hmm, maybe"), {"proposal_id": r["proposal_id"]})
            ok = await API.group_confirm(API.Ctx(account=OWNER, user_said="Yes, these people"), {"proposal_id": r["proposal_id"]})
            self.assertIn("4", ok["say"])
        _in_world(go)

    def test_the_old_doors_that_picked_people_their_own_way_are_gone(self):
        tools = {t["name"] for t in API.TOOLS} if hasattr(API, "TOOLS") else set(API.REGISTRY)
        self.assertIn("group_select", tools)
        self.assertIn("group_confirm", tools)
        self.assertNotIn("group_start", tools)
        self.assertNotIn("group_choose", tools)


class NoLabelInAName(unittest.TestCase):
    def test_a_label_lives_on_the_organisation_never_in_a_persons_name(self):
        """Sasha 360 · "Rui Novo (fictional)" was said aloud: every way onto the roster (a person, a pasted list, an edit) refuses a label in
        a name — and says why."""
        async def go(w):
            await _roster()
            r = await GO.run(OWNER, "person_add", {"rows": [{"name": "Rui Novo (fictional)", "home_city": "Porto"}], "company": COMPANY})
            self.assertFalse(r["done"])
            self.assertIn("belongs on the organisation", r["say"])
            r = await GO.run(OWNER, "add", {"rows": G.read_text("Name, Home city\nTess Example (test), Lisbon"), "on_trip": False})
            self.assertFalse(r["done"])
            pid = (await G.roster(OWNER))["people"][0]["id"]
            r = await GO.run(OWNER, "person_edit", {"person_id": pid, "fields": {"name": "Ana Garcia (demo)"}})
            self.assertFalse(r["done"])
            self.assertFalse([p["name"] for p in (await G.roster(OWNER))["people"] if G.LABEL_IN_NAME.search(p["name"])])
        _in_world(go)


class TheModelSeesTheTools(unittest.TestCase):
    def test_an_organiser_is_offered_the_group_tools_whatever_words_they_use(self):
        """Found by the S2 proof: "plan a Lisbon retreat … for all the executives" offered no group tool (the words named no group word),
        so she answered "I don't have your executive list". An organiser (a company roster) is offered them on every turn."""
        from app.agent import tool_need as TN
        said = "plan a Lisbon retreat 24–27 Nov for all the executives minus Javier Moreno"
        self.assertNotIn("group", TN.families(said))
        self.assertIn("group", TN.families(said, organiser=True))
        src = (ROOT / "app" / "agent" / "sasha.py").read_text()
        self.assertIn("organiser=_org", src)


class OneSource(unittest.TestCase):
    def test_only_the_engine_puts_a_described_selection_on_a_trip(self):
        """Whole class: in the chat's tools (agapi/) and the routes, nothing calls the engine's writers directly — a selection goes through
        groups.confirm (the chat, /group's search box) or a page's own one-person press / [Go] (group_outcome)."""
        hits = []
        for f in [ROOT / "agapi" / "v0.py", ROOT / "booking_signer" / "group_routes.py", ROOT / "products" / "whatsapp.py"]:
            for m in re.finditer(r"\bG\.(create_trip|set_on_trip|choose)\(", f.read_text()):
                hits.append(f"{f.name}: G.{m.group(1)}(")
        self.assertEqual(hits, [])

    def test_the_group_view_is_one_component_on_every_tab(self):
        fe = ROOT.parent / "frontend" / "app"
        for rel in ("s2/S2App.tsx", "components/SashaChat.tsx", "group/page.tsx"):
            self.assertIn("GroupView", (fe / rel).read_text(), rel)
        comp = (fe / "components" / "group" / "GroupView.tsx").read_text()
        self.assertIn("/api/booking/group/select", comp)                                     # /group's own search box: the same resolver
        self.assertIn("/api/booking/group/confirm-list", comp)


class EveryRouteTheViewCallsIsMounted(unittest.TestCase):
    def test_each_group_path_in_the_component_is_a_route(self):
        """Found by the S2 proof: removing /choose took /state, /create and /switch with it — the Group tab read nothing (404). Every
        /api/booking/group/<path> the ONE view calls must be a route."""
        from booking_signer import group_routes as GR
        comp = (ROOT.parent / "frontend" / "app" / "components" / "group" / "GroupView.tsx").read_text()
        called = set(re.findall(r"/api/booking/group/([a-z-]+)", comp))
        mounted = {r.path.split("/")[2] for r in GR.router.routes if r.path.startswith("/group/")}
        self.assertTrue({"state", "create", "switch", "select", "confirm-list"} <= called)
        self.assertEqual(called - mounted, set())


class TheSearchBox(unittest.TestCase):
    def test_the_page_describes_through_the_same_resolver(self):
        async def go(w):
            await _roster()

            async def model(text):   # the model only PROPOSES the filter (stood in here)
                return {"roles": ["executive"], "names_out": ["Javier Prieto"]}
            with mock.patch.object(G, "FILTER_FROM_TEXT", model):
                r = await GO.run(OWNER, "select", {"text": "all the executives minus Javier Prieto", "mode": "tick"})
            self.assertTrue(r["done"], r["say"])
            self.assertEqual(len(r["people"]), 4)
            self.assertIn("did you mean Javier Moreno", r["say"])
        _in_world(go)


if __name__ == "__main__":
    unittest.main()
