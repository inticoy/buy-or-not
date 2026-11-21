from datetime import datetime
from io import BytesIO
import json
from unittest.mock import Mock

import pytest
import requests
from PIL import Image

from app import __main__ as main, deal_card, notifier
from app.store import KST, Store


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.setattr(requests.sessions.Session, "request", Mock(side_effect=AssertionError("network disabled")))
    monkeypatch.setattr(main.voice, "_client", Mock(side_effect=AssertionError("LLM disabled")))


def group(i, **kwargs):
    return {"key": f"test:{i}", "head": {"title": f"상품 {i}", "url": f"https://example.com/{i}", **kwargs}}


def test_card_rows_and_prices():
    item = deal_card.row(group(1, title="[판매처] 통밀 과자 300g × 2팩 (4,000원/무료)", shop="판매처", price_str="4,000원"))
    assert (item.title, item.detail, item.price) == ("통밀 과자", "300g × 2팩 · 무료배송", "4,000원")
    item = deal_card.row(group(1, title="무선 충전기 4,000원/무료", price_str="4,000원"))
    assert (item.title, item.detail, item.price) == ("무선 충전기", "무료배송", "4,000원")
    assert not deal_card.row(group(1, title="상품 적립 후 체감가 3,000원", price_str="3,000원")).price
    assert deal_card.row(group(1, title="실결제가 5,000원 / 적립 후 체감가 3,000원", price_str="5,000원")).price == "5,000원"
    assert not deal_card.row(group(1, price=9000, price_str="옵션별 상이")).price
    assert not deal_card.row(group(1, price=9000)).price


def test_five_rows_render_with_long_korean_and_missing_photo(monkeypatch):
    now = datetime(2026, 11, 21, 12, tzinfo=KST)
    assert deal_card.date_label(now) == "11월 21일 토요일 | 오후"
    assert deal_card.date_label(now.replace(hour=0)).endswith("오전")
    src = BytesIO()
    Image.new("RGB", (80, 140), "red").save(src, format="PNG")
    resp = Mock(status_code=200)
    resp.iter_content.return_value = [src.getvalue()]
    from contextlib import nullcontext
    get = Mock(side_effect=[nullcontext(resp), requests.Timeout()])
    monkeypatch.setattr(deal_card.requests, "get", get)
    rows = [deal_card.row(group(i, title="긴한글상품명" * 30, shop="판매처" * 12,
                                image_url="https://whatdeal.kr/thumb" if i < 2 else None)) for i in range(5)]
    image = Image.open(BytesIO(deal_card.render("게임", deal_card.date_label(now), rows)))
    assert image.format == "PNG" and image.width == 1080 and image.height >= 1300
    assert (255, 0, 0) in image.get_flattened_data()
    personal = Image.open(BytesIO(deal_card.render_personal(rows[-1], "food")))
    assert personal.width == 1080
    assert personal.getpixel((0, 0)) == (255, 246, 216)
    assert personal.getpixel((0, personal.height - 1)) == personal.getpixel((personal.width - 1, 0))
    assert get.call_count == 2
    assert "Mozilla" in get.call_args.kwargs["headers"]["User-Agent"]
    assert deal_card.photo("http://127.0.0.1/test") is None


def test_row_uses_the_group_photo_when_the_head_has_none():
    shared = "https://i1.ruliweb.com/img/a.jpg"
    item = deal_card.row({"head": {"title": "상품", "url": "https://example.com/1"}, "image_url": shared})
    assert item.image == shared
    own = "https://whatdeal.kr/own.jpg"
    item = deal_card.row({"head": {"title": "상품", "url": "https://example.com/1", "image_url": own},
                          "image_url": shared})
    assert item.image == own


def test_image_first_multipart_links_and_silent_send(monkeypatch):
    rows = [deal_card.row(group(i, title=f"[{i}] 시험(옵션)", price_str="2,000원" if i else None)) for i in range(5)]
    payload = notifier.scheduled_message("인기", "날짜", rows, True)
    post = Mock()
    post.return_value.json.return_value = {"id": "offline-id"}
    monkeypatch.setattr(notifier.requests, "post", post)
    assert notifier.post_board(payload, png=b"image") == "offline-id"
    body = post.call_args.kwargs
    message = json.loads(body["data"]["payload_json"])
    assert message["flags"] == 32768 | 4096 | 4
    assert message["allowed_mentions"] == {"parse": []}
    gallery, links = message["components"]
    assert gallery["type"] == 12 and gallery["items"][0]["media"] == {"url": "attachment://deals.png"}
    assert "description" not in gallery["items"][0]
    assert message["attachments"] == [{"id": 0, "filename": "deals.png"}]
    assert body["files"] == {"files[0]": ("deals.png", b"image", "image/png")}
    assert links["type"] == 1
    assert [button["label"] for button in links["components"]] == ["1", "2", "3", "4", "5"]


def test_personal_alert_is_the_image_card(monkeypatch):
    monkeypatch.setattr(deal_card, "render_personal", Mock(return_value=b"png"))
    deal = {"title": "프로 마우스", "url": "https://example.com/1", "product_url": "https://shop.example/1",
            "price_str": "1,000원", "category": "식품"}
    alert = notifier.build_alert([{"owner_id": "1", "want": "단백질", "reason": "맞아요"}], deal, mention=False)
    assert alert["_png"] == b"png"
    gallery, links = alert["components"]
    assert gallery["items"][0]["media"] == {"url": "attachment://alert.png"}
    assert [button["label"] for button in links["components"]] == ["보러 가기", "원문 보기"]
    assert deal_card.render_personal.call_args.args[1] == "food"


def test_search_reply_uses_the_image_card(tmp_path, monkeypatch):
    store = Store(tmp_path / "test.db")
    from app.commands import Handler

    def deal(i, title):
        return {"id": str(i), "source": "test", "title": title, "price": 1000 * i,
                "price_str": f"{1000 * i:,}원", "url": f"https://example.com/{i}", "shop": "시험몰"}

    store.record_deals("test", [deal(1, "프로 마우스"), deal(2, "다른 상품")])
    monkeypatch.setattr(deal_card, "render", Mock(return_value=b"png-bytes"))
    reply = Handler(store).search_deals("123", {"query": "프로"})
    assert reply["flags"] == 32768 | 4
    gallery, links = reply["components"]
    assert gallery["items"][0]["media"] == {"url": "attachment://deals.png"}
    assert "description" not in gallery["items"][0]
    assert [button["label"] for button in links["components"]] == ["1"]
    assert reply["_png"]
    _, date, rows, theme = deal_card.render.call_args.args
    assert deal_card.render.call_args.kwargs["heading"] == "'프로' 검색"
    assert date == "최근 3일 · 1개" and theme == "day" and rows[0].url.endswith("/1")


def test_search_card_falls_back_when_rendering_fails(tmp_path, monkeypatch):
    store = Store(tmp_path / "test.db")
    from app.commands import Handler
    store.record_deals("test", [{"id": "1", "source": "test", "title": "프로 마우스", "price": 1000,
                                 "price_str": "1,000원", "url": "https://example.com/1"}])
    monkeypatch.setattr(deal_card, "render", Mock(side_effect=OSError("font failed")))
    reply = Handler(store).search_deals("123", {"query": "프로"})
    assert "_png" not in reply
    assert reply["components"][1]["type"] == 17


def test_render_fallback_and_slot_retry(tmp_path, monkeypatch):
    store = Store(tmp_path / "test.db")
    picks = [group(1, price_str="800원", shop="시험몰")]
    monkeypatch.setattr(main.ranking, "top", Mock(return_value=picks))
    monkeypatch.setattr(main.deal_card, "render", Mock(side_effect=OSError("font failed")))
    send = Mock()
    monkeypatch.setattr(main, "post_board", send)
    now = datetime(2026, 11, 21, 12, tzinfo=KST)
    due = main.due_boards(store, now)
    assert [board for board, key in due] == ["hot", "game", "digital", "food"]
    [(board, key)] = [(b, k) for b, k in due if b == "game"]
    assert main.post(store, board, False, key) is False
    assert store.get_meta(key) is None and not store.posted_keys(board)
    assert (board, key) in main.due_boards(store, now)
    assert [b for b, _ in main.due_boards(store, now.replace(hour=21))] == ["hot"]
    send.assert_not_called()


def test_board_state_rolls_back_atomically(tmp_path, monkeypatch):
    store = Store(tmp_path / "test.db")
    monkeypatch.setattr(main.ranking, "top", Mock(return_value=[group(1)]))
    monkeypatch.setattr(main.deal_card, "render", Mock(return_value=b"image"))
    monkeypatch.setattr(main, "post_board", Mock(return_value="delivered"))
    store.db.execute("CREATE TRIGGER fail BEFORE INSERT ON posted BEGIN SELECT RAISE(ABORT, 'test'); END")
    import sqlite3
    with pytest.raises(sqlite3.IntegrityError):
        main.post(store, "game", False, "slot")
    assert store.get_meta("slot") is None and not store.posted_keys("game")


def test_dry_run_posts_nothing_and_keeps_slot_due(tmp_path, monkeypatch, capsys):
    store = Store(tmp_path / "test.db")
    monkeypatch.setattr(main.ranking, "top", Mock(return_value=[group(1)]))
    monkeypatch.setattr(notifier, "send_message", Mock(side_effect=AssertionError("unexpected send")))
    assert main.post(store, "food", True, "slot")
    assert "attachment://deals.png" in capsys.readouterr().out
    assert store.get_meta("slot") is None and not store.posted_keys("food")
