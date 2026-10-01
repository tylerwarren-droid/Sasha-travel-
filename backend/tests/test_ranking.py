"""S-68 step 6 · ranking the 20: the ≥ 20-review rule, filters as visible groups, chip sorts, ties. Offline.

    cd backend && python -m unittest tests.test_ranking -v
"""
from __future__ import annotations

import unittest

from booking_signer import ranking as K


def c(pid, rating=None, n=None, price=None, dist=None, open_=None, status="OPERATIONAL"):
    return {"place_id": pid, "rating": rating, "rating_count": n, "price_level": price, "distance_m": dist, "status": status,
            "open_at": {"known": open_ is not None, "open": open_, "words": "x"}}


class Ranking(unittest.TestCase):
    def test_best_rated_counts_only_with_twenty_reviews(self):
        cs = [c("few5", 5.0, 6), c("ok46", 4.6, 300), c("none"), c("ok48", 4.8, 20), c("few49", 4.9, 19)]
        r = K.rank(cs, open_at=None, near_found=False)
        self.assertEqual(r["orders"]["rated"], ["ok48", "ok46", "few5", "few49", "none"])
        self.assertEqual(r["default"], "rated")
        self.assertEqual(K.rating_words(cs[0]), "★ 5.0 (6 Google reviews — too few to rank)")
        self.assertEqual(K.rating_words(cs[1]), "★ 4.6 (300 Google reviews)")
        self.assertEqual(K.rating_words(cs[2]), "no rating")
        self.assertNotIn("closest", r["orders"])          # no place named: no distance chip
        self.assertNotIn("open", r["orders"])             # no time stated: no open chip, no groups

    def test_ties_go_to_rating_then_distance(self):
        cs = [c("far", 4.7, 50, dist=3000), c("near", 4.7, 50, dist=200), c("best", 4.9, 50, dist=9000)]
        r = K.rank(cs, open_at=None, near_found=True)
        self.assertEqual(r["orders"]["rated"], ["best", "near", "far"])
        self.assertEqual(r["orders"]["closest"], ["near", "far", "best"])
        self.assertIn("ties go to the closer place", r["explainers"]["rated"])

    def test_price_cheapest_first_not_listed_last(self):
        cs = [c("unlisted", 4.9, 99), c("dear", 4.9, 99, price=4), c("cheap", 4.0, 99, price=1), c("cheap2", 4.5, 99, price=1)]
        r = K.rank(cs, open_at=None, near_found=False)
        self.assertEqual(r["orders"]["price"], ["cheap2", "cheap", "dear", "unlisted"])
        self.assertEqual((K.price_words(cs[0]), K.price_words(cs[1])), ("price level not listed", "€€€€"))

    def test_a_stated_time_groups_never_removes(self):
        cs = [c("closed", 5.0, 99, open_=False), c("open", 4.1, 99, open_=True), c("unknown", 4.9, 99),
              c("temp", 4.9, 99, open_=True, status="CLOSED_TEMPORARILY"), c("gone", 4.9, 99, open_=True, status="CLOSED_PERMANENTLY")]
        r = K.rank(cs, open_at="2026-10-06T17:00", near_found=False)
        self.assertEqual(r["orders"]["rated"], ["open", "unknown", "closed", "temp"])     # gone: never a card
        self.assertEqual(r["orders"]["open"], ["open", "unknown", "closed", "temp"])
        self.assertEqual(r["groups"], {"closed": "closed_then", "open": "main", "unknown": "hours_unknown", "temp": "closed_temporarily"})
        self.assertEqual(r["count"], "1 of 4 open at 17:00 by their listed hours")
        self.assertIn("Places not open at 17:00 by their listed hours come after.", r["explainers"]["rated"])

    def test_all_closed_is_said_not_hidden(self):
        cs = [c("a", 4.5, 99, open_=False), c("b", 4.9, 99, open_=False)]
        r = K.rank(cs, open_at="2026-10-06T15:00", near_found=False)
        self.assertEqual(r["count"], "0 of 2 open at 15:00 by their listed hours")
        self.assertEqual(r["orders"]["rated"], ["b", "a"])                                # still listed, as closed then
        self.assertEqual(set(r["groups"].values()), {"closed_then"})


if __name__ == "__main__":
    unittest.main()
