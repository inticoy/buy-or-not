import unittest
from pathlib import Path

from bs4 import BeautifulSoup

from app.collector import _deduplicate_deals, _parse_hydration_deals, parse_rank_html
from app.hotdealzip import parse_deals, parse_price

FIXTURES = Path(__file__).parent / "fixtures"


class HydrationParserTests(unittest.TestCase):
    def test_parses_all_hydration_deals_not_only_rendered_cards(self):
        soup = BeautifulSoup(
            '''<script>
            kit.start(app, element, {data:[{deals:{contents:[
              {id:101,siteName:"퀘이사존",storeName:"네이버",rankNum:1,title:"상품 A",thumbnailUrl:"https://img.example/a.webp?d=200x200",price:"10,000원",originalLikes:3,originalComments:4},
              {id:102,siteName:"루리웹",storeName:"쿠팡",rankNum:2,title:"상품 B",thumbnailUrl:null,price:"20,000원",originalLikes:5,originalComments:6}
            ],endCursor:null,hasNext:false}}]});
            </script>''',
            "html.parser",
        )

        deals = _parse_hydration_deals(soup)

        self.assertEqual(2, len(deals))
        self.assertEqual("https://www.algumon.com/n/deal/101", deals[0]["url"])
        self.assertEqual("https://img.example/a.webp?d=512x512", deals[0]["image_url"])
        self.assertEqual("20,000원", deals[1]["price_str"])


class RankPageFixtureTests(unittest.TestCase):
    def test_parses_saved_rank_page_from_chrome(self):
        html = (FIXTURES / "algumon_rank_6.html").read_text(encoding="utf-8")

        deals = parse_rank_html(html, category_id=6)

        self.assertEqual(10, len(deals))
        self.assertTrue(all(deal["url"].startswith("https://www.algumon.com/n/deal/") for deal in deals))
        self.assertTrue(all(deal["title"] for deal in deals))


class HotdealZipTests(unittest.TestCase):
    def test_parses_popular_and_latest_pages(self):
        for name in ("hotdeal_popular", "hotdeal_latest"):
            deals = parse_deals((FIXTURES / f"{name}.html").read_text(encoding="utf-8"))

            self.assertEqual(25, len(deals), name)
            self.assertTrue(all(deal["url"].startswith("https://hotdeal.zip/") for deal in deals))
            self.assertTrue(all(deal["title"] and deal["id"] for deal in deals))

    def test_parses_won_prices_only(self):
        self.assertEqual(12000, parse_price("12,000원"))
        self.assertEqual(2744400, parse_price("2,744,400원"))
        self.assertIsNone(parse_price("우리$64.57"))
        self.assertIsNone(parse_price("가격별상이"))
        self.assertIsNone(parse_price("0원"))
        self.assertIsNone(parse_price(None))


class DeduplicationTests(unittest.TestCase):
    def test_removes_high_confidence_cross_post(self):
        deals = [
            {"title": "Out of Sight / TerraScape 무료 (에픽게임즈)", "price_str": "무료"},
            {"title": "Out of Sight, TerraScape", "price_str": "무료"},
            {"title": "Pony Island", "price_str": "무료"},
        ]

        unique = _deduplicate_deals(deals)

        self.assertEqual(["Out of Sight / TerraScape 무료 (에픽게임즈)", "Pony Island"], [
            deal["title"] for deal in unique
        ])


if __name__ == "__main__":
    unittest.main()
