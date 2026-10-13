"""Sasha 257 · T39 — A PLAN'S HOTELS SEARCHED BESIDE ITS MODEL (row 863, measured on production: the itinerary build is 13–24 s of a
plan turn — the plan model 8–9.5 s, THEN the hotel search 3.6–3.9 s). The destination's hotels are searched beside the model and
used only when the plan stays exactly there and every hotel is in the plan's country; else searched after the plan, as before.
Offline: the model and the hotel search are stand-ins.

    cd backend && python -m unittest tests.test_s257_plan_speed -v
"""
from __future__ import annotations

import asyncio
import json
import unittest
from types import SimpleNamespace
from unittest import mock

from app.services import world_itinerary as W


def run(c):
    return asyncio.run(c)


def plan(cities, country="Italy"):
    return {"title": "x", "country": country, "country_code": "IT", "arrive_airport": "FCO", "depart_airport": "FCO",
            "days": [{"city": c, "title": f"Day {i}", "activities": []} for i, c in enumerate(cities)]}


class Model:
    def __init__(self, p, delay=0.2):
        self.p, self.delay = p, delay
        self.messages = self

    async def create(self, **k):
        await asyncio.sleep(self.delay)
        return SimpleNamespace(content=[SimpleNamespace(text=json.dumps(self.p))])


class Base(unittest.TestCase):
    def build(self, cities, dest, addr="Via Roma 1, 00184 Roma RM, Italy", country="Italy"):
        calls = []

        async def hotels(account, city, country_name, code, prefer="", strict=False):
            calls.append((city, country_name))
            await asyncio.sleep(0.15)
            return [{"name": f"Hotel {city}", "place_id": f"p-{city}", "est_usd": 100, "est_eur": 90, "address": addr}]
        with mock.patch("app.services.llm.client", Model(plan(cities, country))), mock.patch.object(W, "hotels_in", hotels), \
                mock.patch.object(W, "_photos", mock.AsyncMock(return_value={})), mock.patch.object(W, "_place_photo", mock.AsyncMock(return_value=None)):
            out = run(W.build_world({"destination": dest, "start_date": "2026-12-03", "nights": len(cities) - 1, "party": 2, "origin": "Madrid"}))
        return out, calls


class EarlyHotels(Base):
    def test_one_city_plan_uses_the_search_made_beside_the_model(self):
        out, calls = self.build(["Rome", "Rome", "Rome"], "Rome")
        self.assertEqual(calls, [("Rome", "")])                         # one search, started beside the model
        self.assertEqual(out["days"][0]["hotel"]["name"], "Hotel Rome")

    def test_a_multi_city_plan_searches_after_the_plan_as_before(self):
        out, calls = self.build(["Rome", "Florence", "Florence"], "Rome")
        self.assertEqual(calls[0], ("Rome", ""))
        self.assertEqual(sorted(calls[1:]), [("Florence", "Italy"), ("Rome", "Italy")])

    def test_a_hotel_in_another_country_is_never_used(self):
        out, calls = self.build(["Valencia", "Valencia", "Valencia"], "Valencia", addr="Av. Bolívar, Valencia, Venezuela", country="Spain")
        self.assertEqual(calls, [("Valencia", ""), ("Valencia", "Spain")])   # searched again, with the plan's country


if __name__ == "__main__":
    unittest.main()
