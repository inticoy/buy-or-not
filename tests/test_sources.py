import unittest
from datetime import date, datetime

from app.ranking import top
from app.sources import KST, expired, parse_clien, parse_ruliweb

RULIWEB_ROW = """<table><tr class="table_body blocktarget"><td class="divsn"><a>음식</a></td>
<td class="subject"><a class="subject_link deco" href="https://bbs.ruliweb.com/market/board/1020/read/107925?">
[쿠팡] 농심 육개장 사발면 86g 6개 (4,430원/무료)</a><a class="num_reply">(4)</a></td>
<td class="recomd">4</td><td class="hit">3236</td><td class="time">11:38</td></tr>
<tr class="table_body notice"><td class="time">10:00</td></tr></table>"""

CLIEN_ROW = """<div class="list_item symph_row jirum sold_out" data-board-sn="19275765" data-comment-count="2">
<div class="list_symph"><em>1</em></div><a data-role="list-title-text" href="/service/board/jirum/19275765?od=T31">
Knots Live Wallpaper 일시 무료</a><div class="list_thumbnail"><img src="https://edgio.clien.net/a.jpeg"></div>
<div class="list_hit"><span class="hit">3153</span></div><span class="timestamp">2026-10-10 15:54:24</span></div>"""


def deal(id, community, comments, title=None, **kw):
    return {"id": id, "group_key": id, "community": community, "comments": comments, "recommend": None,
            "title": title or id, "posted_at": "2026-10-11T10:00:00+09:00", "category": "food", **kw}


class ParserTests(unittest.TestCase):
    def test_ruliweb_row(self):
        [d] = parse_ruliweb(RULIWEB_ROW, datetime(2026, 10, 11, 13, 0, tzinfo=KST))
        self.assertEqual(("ruliweb:107925", "쿠팡", 4430, 4, 4, "food"),
                         (d["id"], d["shop"], d["price"], d["comments"], d["recommend"], d["category"]))
        self.assertEqual("2026-10-11T11:38:00+09:00", d["posted_at"])

    def test_clien_row(self):
        [d] = parse_clien(CLIEN_ROW)
        self.assertEqual(("clien:19275765", 2, 1, True), (d["id"], d["comments"], d["recommend"], d["ended"]))
        self.assertEqual("https://www.clien.net/service/board/jirum/19275765", d["url"])

    def test_expired_date_range(self):
        today = date(2026, 10, 11)
        self.assertTrue(expired("[롯데리아] 버거 세트 (~10/10)", today))
        self.assertFalse(expired("[버거킹앱] 와퍼 쿠폰 (10/9~11)", today))
        self.assertFalse(expired("삼다수 2리터", today))


class RankingTests(unittest.TestCase):
    def test_more_comments_rank_higher_and_same_event_merges(self):
        deals = [deal("a", "펨코", 100, shop="쿠팡", price=3900, title="사리곰탕면"),
                 deal("b", "펨코", 80, shop="쿠팡와우", price=3350, title="무파마탕면"),
                 deal("c", "뽐뿌", 3), deal("d", "뽐뿌", 1)]
        picks = top(deals, n=3)
        self.assertEqual(["a", "c", "d"], [g["key"] for g in picks])
        self.assertEqual(["b"], [g["key"] for g in picks[0]["same_event"]])

    def test_ended_and_excluded_deals_are_skipped(self):
        deals = [deal("a", "펨코", 100, ended=True), deal("b", "펨코", 50), deal("c", "펨코", 10)]
        self.assertEqual(["c"], [g["key"] for g in top(deals, exclude={"b"})])


if __name__ == "__main__":
    unittest.main()


class GiveawayTest(unittest.TestCase):
    def test_keyword_only_as_extra_is_skipped(self):
        from app.matcher import is_giveaway, match
        self.assertTrue(is_giveaway("메가커피", "[G마켓] 도루코 면도기 + 메가커피 아메리카노 (9,900원)"))
        self.assertTrue(is_giveaway("메가커피", "도루코 면도기 구매시 메가커피 기프티콘 증정"))
        self.assertFalse(is_giveaway("메가커피", "[메가커피] 아메리카노 1+1"))
        self.assertFalse(is_giveaway("메가커피", "[카카오톡] 메가커피 아메리카노 2+1 (6,000원)"))
        self.assertFalse(is_giveaway("메가커피", "[네이버] 메가커피 모바일 금액권 1만원 (9,000원)"))
        watch = {"id": 1, "keywords": ["메가커피"], "max_price": None}
        deals = [{"id": "a", "title": "도루코 면도기 + 메가커피 증정"}, {"id": "b", "title": "[메가커피] 아메리카노 1+1"}]
        self.assertEqual([d["id"] for _, d, _ in match([watch], deals, judge=lambda w, d: [])], ["b"])
