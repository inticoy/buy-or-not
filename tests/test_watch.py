import tempfile
import unittest
from pathlib import Path

from app.matcher import keyword_match, match, within_price
from app.store import Store


def deal(id, title, price=None, price_str=None):
    return {"id": id, "title": title, "price": price, "price_str": price_str}


class KeywordMatchTests(unittest.TestCase):
    def test_all_words_of_a_keyword_must_appear(self):
        self.assertTrue(keyword_match(["에어팟 프로"], "애플 에어팟 프로 2세대 USB-C"))
        self.assertFalse(keyword_match(["에어팟 프로"], "애플 에어팟 4세대"))

    def test_any_keyword_can_match(self):
        self.assertTrue(keyword_match(["메가커피", "메가mgc커피"], "메가MGC커피 아메리카노 쿠폰"))

    def test_price_limit_passes_unknown_prices(self):
        watch = {"max_price": 250000}
        self.assertTrue(within_price(watch, deal("1", "x", 239000)))
        self.assertFalse(within_price(watch, deal("1", "x", 289000)))
        self.assertTrue(within_price(watch, deal("1", "x", None)))


class MatchTests(unittest.TestCase):
    def test_keyword_and_descriptive_watches(self):
        watches = [
            {"id": 1, "want": "메가커피", "keywords": ["메가커피"], "max_price": None},
            {"id": 2, "want": "게이밍 모니터", "keywords": None, "max_price": None},
        ]
        deals = [deal("10", "메가커피 20%할인"), deal("11", "LG 울트라기어 OLED 480Hz", 899000)]
        fake_judge = lambda ws, ds: [{"watch_id": 2, "deal_id": "11", "reason": "게이밍 모니터"}]

        results = match(watches, deals, judge=fake_judge)

        self.assertEqual([(1, "10", None), (2, "11", "게이밍 모니터")],
                         [(w["id"], d["id"], r) for w, d, r in results])


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name) / "test.db")

    def tearDown(self):
        self.store.db.close()
        self.tmp.cleanup()

    def test_records_only_unseen_deals_and_groups_cross_posts(self):
        first = self.store.record_deals("hz", [deal("1", "애플 에어팟 4세대 MXP63KH/A", 109000, "109,000원")])
        second = self.store.record_deals("hz", [
            deal("1", "애플 에어팟 4세대 MXP63KH/A", 109000, "109,000원"),
            deal("2", "에어팟 4세대 MXP63KH/A", 109000, "109,000원"),
        ])

        self.assertEqual(["2"], [d["id"] for d in second])
        self.assertEqual(first[0]["group_key"], second[0]["group_key"])

    def test_notifies_again_only_when_price_drops(self):
        self.assertEqual("new", self.store.notify_kind(1, "g", 100000))
        self.store.mark_notified(1, "g", 100000)

        self.assertIsNone(self.store.notify_kind(1, "g", 100000))
        self.assertEqual("drop", self.store.notify_kind(1, "g", 90000))


if __name__ == "__main__":
    unittest.main()
