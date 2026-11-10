"""Sasha 364 (with 363's remaining parts) · a group trip ENDS in one clear finished state built from the ONE trip record.

Found (Tyler's dry run 9 Nov 21:00–21:10, iPhone, the demo organiser, Lisbon 9–12 Dec, 5 executives): Ana García's fare (cancellable only by
the airline) came back as a FAILURE with the raw nested error; the Group page's Book all did nothing ("this page can't do that yet"); no
finish; the chat's card stayed "not planned"; grade where people were chosen by role; "(fictional)" in the company name; the card titled
"YOUR BOOKING · ONE TAP" though nothing was booked; old test trips everywhere.

    cd backend && python -m unittest tests.test_s364_one_finish -v
"""
from __future__ import annotations

import asyncio
import pathlib
import re
import unittest
from unittest import mock

from booking_signer import group_book as GB, group_outcome as GO, groups as G, next_actions as NA
from tests import test_s332 as W

run = asyncio.run
OWNER = W.OWNER
ROOT = pathlib.Path(__file__).resolve().parents[1]
COMPANY = "Acme Components (fictional)"


def _in_world(scenario):
    with W.World() as w:
        return run(scenario(w))


class OneBookAll(unittest.TestCase):
    def test_every_action_carries_its_tool_to_every_door(self):
        """The Group page's Book all got no tool, so it said "this page can't do that yet": the ONE table's tool goes with every action."""
        self.assertEqual(NA.action("book_all")["tool"], "group_book")
        rows = [{"name": "A", "status": "planned"}, {"name": "B", "status": "booked"}]
        for a in NA.for_group(rows):
            self.assertTrue(a.get("tool"), a)
        page = (ROOT.parent / "frontend" / "app" / "components" / "group" / "GroupView.tsx").read_text()
        for tool in {a["tool"] for a in NA.for_group(rows)}:
            self.assertIn(f"a.tool === '{tool}'", page, tool)                             # the page runs each one


class ADecisionNeverAnError(unittest.TestCase):
    def test_a_refusal_is_a_named_decision_in_plain_words(self):
        e = {"code": "not_cancellable", "message": "The airline won't quote a cancellation for this order (This order cannot be cancelled "
                                                   "through the API.)."}
        d = GB.decision(e)
        self.assertIn("can only be cancelled by the airline", d["why"])
        self.assertIn("condition of the fare, not a failure", d["why"])
        self.assertNotIn("API", d["why"])
        self.assertNotIn("(", d["why"])                                                    # never the supplier's nested text
        self.assertTrue(d["why"].rstrip().endswith("?"))                                   # a decision, put to the manager
        u = GB.decision({"code": "weird_new_code", "message": "Field x (nested (error))"})
        self.assertNotIn("Field x", u["why"])
        self.assertIn("nothing was taken", u["why"])

    def test_no_raw_supplier_message_reaches_the_failed_list(self):
        src = (ROOT / "booking_signer" / "group_book.py").read_text()
        self.assertNotRegex(src, r'"why": e\.get\("message"\)')
        self.assertIn('failed.append({"name": it["name"], **decision(e)})', src)


class TheFinish(unittest.TestCase):
    def test_built_from_the_record(self):
        async def go(w):
            await GO.run(OWNER, "person_add", {"rows": [{"name": n, "home_city": c, "role": "executive", **({"email": e} if e else {})}
                                                        for n, c, e in (("Ana Example", "Lisbon", None), ("Bo Example", "Porto", "bo@example.test"),
                                                                        ("Cy Example", "Paris", "cy@example.test"))], "company": COMPANY})
            ids = [p["id"] for p in (await G.state(OWNER))["roster"]]
            await G.create_trip(OWNER, None, "Lisbon", "2026-12-09", "2026-12-12", None, ids)
            await G.planned(OWNER)
            booked = {"Bo Example", "Cy Example"}
            real_view = G.view

            async def view(account, mid=None):
                v = await real_view(account, mid)
                for r in v["rows"]:
                    if r["name"] in booked:
                        r.update(status="booked", references=["REF" + r["name"][:2].upper()])
                return v
            sent = []

            async def send(msg):
                sent.append(msg["to"])
                return {"sent": True}
            with mock.patch.object(G, "view", view), mock.patch("booking_signer.live_events.SEND", send), \
                    mock.patch.object(GB, "invoice", mock.AsyncMock(return_value={"number": "KAN-TEST", "total": "€1,234.00"})):
                fin = await GB.finish(OWNER, [{"name": n} for n in booked], [{"name": "Ana Example", **GB.decision({"code": "not_cancellable"})}])
            return fin, sent
        fin, sent = _in_world(go)
        self.assertTrue(fin["say"].startswith("2 of 3 booked (TEST)."), fin["say"])
        self.assertIn("references are on the master list", fin["say"])
        self.assertIn("Confirmations have been sent to each traveller's registered email", fin["say"])
        self.assertIn("The invoice KAN-TEST: €1,234.00.", fin["say"])
        self.assertIn("Ana Example: their fare can only be cancelled by the airline", fin["say"])   # a decision, named
        self.assertEqual(sorted(sent), ["bo@example.test", "cy@example.test"])           # each traveller, to THEIR email, the one sender

    def test_a_traveller_with_no_email_is_named(self):
        async def go(w):
            await GO.run(OWNER, "person_add", {"rows": [{"name": "Ana Example", "home_city": "Lisbon"}], "company": COMPANY})
            ids = [p["id"] for p in (await G.state(OWNER))["roster"]]
            await G.create_trip(OWNER, None, "Lisbon", "2026-12-09", "2026-12-12", None, ids)
            await G.planned(OWNER)
            real_view = G.view

            async def view(account, mid=None):
                v = await real_view(account, mid)
                for r in v["rows"]:
                    r["status"] = "booked"
                return v
            with mock.patch.object(G, "view", view), mock.patch.object(GB, "invoice", mock.AsyncMock(return_value={})):
                return await GB.finish(OWNER, [{"name": "Ana Example"}], [])
        fin = _in_world(go)
        self.assertTrue(fin["say"].startswith("All 1 booked (TEST)."), fin["say"])
        self.assertIn("No email on file for Ana Example", fin["say"])

    def test_the_yes_ends_in_the_finish(self):
        src = (ROOT / "booking_signer" / "group_book.py").read_text()
        self.assertIn('if c["action"] == "book":', src)
        self.assertIn("fin = await finish(account, done, failed)", src)


class PlanningLive(unittest.TestCase):
    def test_planning_is_a_status_until_each_is_planned(self):
        async def go(w):
            await GO.run(OWNER, "person_add", {"rows": [{"name": "Ana Example", "home_city": "Lisbon", "role": "engineer"}], "company": COMPANY})
            ids = [p["id"] for p in (await G.state(OWNER))["roster"]]
            gate = asyncio.Event()
            real_quote = G.QUOTE

            async def slow(m, mv):
                await gate.wait()
                return await real_quote(m, mv)
            with mock.patch.object(G, "QUOTE", slow):
                await G.create_trip(OWNER, None, "Lisbon", "2026-12-09", "2026-12-12", None, ids)
                await asyncio.sleep(0)
                during = [r["status"] for r in (await G.view(OWNER))["rows"]]
                card = await G.card(OWNER)
                gate.set()
                await G.planned(OWNER)
            after = [r["status"] for r in (await G.view(OWNER))["rows"]]
            return during, card, after
        during, card, after = _in_world(go)
        self.assertEqual(during, ["planning…"])
        self.assertIn("Planning 1 now", card["empty"])
        self.assertEqual(card["rows"][0]["role"], "engineer")                             # the label they were chosen by
        self.assertNotIn("grade", card["rows"][0])                                        # no limits set: no grade
        self.assertIn(after[0], ("planned", "needs vault"))


class ArchivedNeverDeleted(unittest.TestCase):
    def test_archive_leaves_the_trips_and_keeps_the_rows(self):
        async def go(w):
            await GO.run(OWNER, "person_add", {"rows": [{"name": "Ana Example", "home_city": "Lisbon"}], "company": COMPANY})
            ids = [p["id"] for p in (await G.state(OWNER))["roster"]]
            r = await G.create_trip(OWNER, None, "Porto", "2026-12-01", "2026-12-03", None, ids)
            out = await GO.run(OWNER, "archive", {"trip": r["movement_id"]})
            return r["movement_id"], out, (await G.trips(OWNER))["trips"], w.store.movements
        mid, out, trips, movements = _in_world(go)
        self.assertTrue(out["done"], out["say"])
        self.assertNotIn(mid, [t["id"] for t in trips])
        self.assertIn(mid, movements)                                                     # never deleted
        self.assertTrue(movements[mid].get("archived"))
        sql = (ROOT / "booking_signer" / "sql" / "060_archived_trips.sql").read_text()
        self.assertNotRegex(sql.lower(), r"\bdelete\b")


class NoLabelInACompanysName(unittest.TestCase):
    def test_refused_and_renamed_through_the_engine(self):
        async def go(w):
            bad = await G.rename_company(OWNER, "Lusa Obras Demo (fictional)")
            good = await G.rename_company(OWNER, "Lusa Obras Demo")
            return bad, good, (await G.store().movement(OWNER))["company"]
        bad, good, now = _in_world(go)
        self.assertIn("belongs on the organisation's account", bad["why"])
        self.assertEqual((good["company"], now), ("Lusa Obras Demo", "Lusa Obras Demo"))


class TheCardNamesItself(unittest.TestCase):
    def test_a_list_of_people_is_never_your_booking(self):
        from app.agent import sasha as S
        ev = S.render("group_select", {"proposal_id": "p1", "read_back": ["Lisbon", "• Ana"], "ask": "Make the Lisbon trip with these 1?"}, {})
        self.assertEqual(ev["head"], "Who's going · one tap")
        s2 = (ROOT.parent / "frontend" / "app" / "s2" / "S2App.tsx").read_text()
        self.assertIn("const head = c.head ? untag(c.head)", s2)


class EveryLineSpokenIsWritten(unittest.TestCase):
    def test_each_spoken_line_has_its_written_twin(self):
        """WORDS: in the turn, every line said by code is written first (the same line); after a payment, the card shows Sasha's result
        (never Stripe's screen) and the chat writes it."""
        src = (ROOT / "app" / "agent" / "sasha.py").read_text()
        for m in re.finditer(r'yield \{"type": "say", "text": SP\.speakable\((\w+)\)\}', src):
            before = src[max(0, m.start() - 200):m.start()]
            self.assertRegex(before, r'yield \{"type": "text", "delta": (?:" " \+ )?' + m.group(1) + r'(?: \+ " ")?\}', m.group(0))
        pay = (ROOT.parent / "frontend" / "app" / "components" / "PayHere.tsx").read_text()
        self.assertIn("live.current?.destroy()", pay)                                    # Stripe's checkout removed on completion
        self.assertIn("data-pay-result", pay)


class OneAsk(unittest.TestCase):
    """363(a) · ONE read-back card is the only question: its payment is IN it (the pay tap = the yes). Found 9 Nov: a read-back,
    "Shall I go ahead?", "Pay here, or on your phone?", then a second card."""

    def test_the_card_carries_its_payment_and_no_yes_no(self):
        from app.agent import sasha as S
        res = {"read_back": ["✈️ U2 7640 MAD→LIS", "Total €41.47"], "read_back_sha256": "a" * 64, "total_eur": 41.47,
               "pay": {"where": "here", "session_id": "cs_1", "client_secret": "cs_1_secret", "total_eur": 41.47}}
        ev = S.render("hold_booking", res, {})
        self.assertEqual(ev["pay"]["client_secret"], "cs_1_secret")
        self.assertNotIn("choices", ev)                                                    # the pay IS the yes: no Yes / No beside it
        self.assertNotIn("pay", S.clean_for_model(res).get("pay", {}).get("client_secret", "") or "")   # never the model's
        saved = S.render("hold_booking", {**res, "pay": {"where": "saved", "card": "Visa ••4242"}}, {})
        self.assertEqual(saved["choices"][0], {"title": "Pay with Visa ••4242", "route": "say:Yes, book it"})

    def test_whatsapp_one_message_with_its_link(self):
        from booking_signer import guest_whatsapp as GW, wa_agent as WA
        out = GW.Out()
        WA._read_back({"read_back": ["✈️ U2 7640", "Total €41.47"], "pay": {"where": "phone", "checkout_url": "https://checkout.stripe.test/x"}}, out)
        self.assertEqual(len(out.items), 1)
        self.assertIn("https://checkout.stripe.test/x", out.items[0][1])

    def test_a_saved_card_is_held_never_said_charged(self):
        src = (ROOT / "agapi" / "v0.py").read_text()       # found by the iPhone proof: "has been charged €41.48" — it is a hold (363)
        self.assertNotIn('f"Paid with {got', src)
        self.assertIn("is HELD on {got['card']}", src)

    def test_the_question_is_gone_everywhere(self):
        from agapi import v0 as API
        from app.services import persona as P
        self.assertFalse(hasattr(API, "PAY_ASK"))
        self.assertNotIn("Pay here, or on your phone?", P.AGENT_SYSTEM)
        self.assertNotIn("and asks whether to go ahead", P.AGENT_SYSTEM)
        src = (ROOT / "agapi" / "v0.py").read_text()
        self.assertIn('res.update(await _pay_in_card(ctx, q["sha256"], res))', src)
        self.assertNotIn("choose_payment", src)
        s2 = (ROOT.parent / "frontend" / "app" / "s2" / "S2App.tsx").read_text()
        self.assertIn("<ReadBackPay c={c} send={send} />", s2)


class TheRulesQuestionIsTheirs(unittest.TestCase):
    """Found by the recording gate (10 Nov, REST typed): after the guest gave a name and number, the model sent hold_venue route
    "page" — it answered the rules' ONE question ("a prefilled form you just confirm, or shall I handle it?") for them, and the test
    venue was never booked through AgAPI. Its options are the person's to choose: their own words this turn, or their tap."""

    def run_door(self, said, route):
        from agapi import v0 as API, venues as VN
        seen = []

        async def hold(ctx, a):
            seen.append(a.get("route"))
            return {"status": "awaiting_yes"}
        with mock.patch.object(VN, "hold_venue", hold), mock.patch.object(VN, "one_path", lambda ctx: True):
            run(API.hold_venue(API.Ctx(account=OWNER, user_said=said, surface="s2"), {"name": "Sasha Test Venue", "route": route}))
        return seen[0]

    def test_the_models_pick_is_dropped_their_words_keep_it(self):
        from agapi import v0 as API
        API._ROUTE_CHOSEN.clear()
        self.assertIsNone(self.run_door("Suite Guest +34 600 000 000", "page"))          # the model chose: dropped → the rules ask
        self.assertIsNone(self.run_door("yes", "form"))
        self.assertEqual(self.run_door("Prefilled form, please", "page"), "page")        # their words: kept
        self.assertEqual(self.run_door("Handle it", "form"), "form")
        self.assertEqual(self.run_door("yes", "call"), "call")                           # the call's OK is not this question
        self.assertEqual(self.run_door("no thanks", "no"), "no")

    def test_their_earlier_answer_carries_the_booking_on(self):
        from agapi import v0 as API
        API._ROUTE_CHOSEN.clear()
        self.assertEqual(self.run_door("Handle it", "form"), "form")                     # they chose …
        self.assertEqual(self.run_door("Tyler Warren, +34 600 111 222", "form"), "form")  # … the contact, then the hold as they chose
        self.assertIsNone(self.run_door("Tyler Warren, +34 600 111 222", "page"))        # never another option for them
        API._ROUTE_CHOSEN.clear()


class TheAirlinesNeedBeforeTheCard(unittest.TestCase):
    """Found by the iPhone proof (Part A, 10 Nov): the saved card's ONE button was tapped, THEN she asked for a mobile ("The airline
    won't accept the mobile number I have on file") — a second question after the yes. The airline's need is asked before the card."""

    def test_hold_booking_asks_for_the_mobile_before_any_card(self):
        from agapi import v0 as API
        from booking_signer import basket as BK, basket_book as BB, passengers as PX
        API._HELD.clear()
        pay, need = mock.AsyncMock(), {"why": "Before I take any payment: the airline needs the traveller's mobile number.", "needs": ["mobile"]}
        figs = mock.AsyncMock(return_value={"total_eur": 42.25, "party": 1})
        with mock.patch.object(API, "_plan", mock.AsyncMock(return_value={"trip_id": "t1", "party": 1})), \
                mock.patch.object(PX, "saved", mock.AsyncMock(return_value=[{}])), mock.patch.object(BK, "trip_figures", figs), \
                mock.patch.object(API, "_s1_passport", mock.AsyncMock(return_value=None)), \
                mock.patch.object(BB, "quote", mock.AsyncMock(return_value={"lines": ["✈️ UX 1159", "Total €42.25 (TEST)"], "sha256": "s1", "eur": 42.25})), \
                mock.patch.object(BK, "items", mock.AsyncMock(return_value=[{"kind": "flight"}])), mock.patch.object(BK, "to_book", lambda rows: rows), \
                mock.patch.object(API, "breakdown", lambda rows, eur: {}), mock.patch.object(BB, "mobile_needed", mock.AsyncMock(return_value=need)), \
                mock.patch.object(BB, "pay", pay), mock.patch("booking_signer.test_deposit.saved_card", mock.AsyncMock(return_value={"words": "Visa ••2235"})):
            r = run(API.call(API.Ctx(account=OWNER, surface="s2"), "hold_booking", {"idempotency_key": "k-s364-mobile"}))
        self.assertEqual(r["error"]["code"], "mobile_needed", r)
        self.assertIn("Before I take any payment", r["error"]["message"])
        pay.assert_not_called()                                                           # no card, no hold, no payment
        API._HELD.clear()


if __name__ == "__main__":
    unittest.main()
