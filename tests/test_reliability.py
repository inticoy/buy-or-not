import importlib
from datetime import datetime
from unittest.mock import Mock

import pytest
import requests

from app import commands, mentions, notifier
from app.store import KST, Store


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    monkeypatch.setattr(requests.sessions.Session, "request", Mock(side_effect=AssertionError("unexpected network call")))


@pytest.fixture
def main(monkeypatch):
    monkeypatch.setattr("dotenv.load_dotenv", lambda: None)
    return importlib.import_module("app.__main__")


@pytest.fixture
def store(tmp_path):
    db = Store(tmp_path / "test.db")
    yield db
    db.db.close()


def deal(price=100):
    return {"id": "1", "source": "test", "title": "coffee", "price": price,
            "price_str": str(price), "url": "https://example.com/deal", "group_key": "test:1"}


def test_alert_records_only_reached_recipients(store, main, monkeypatch):
    for owner in ("woojoo:failed", "woojoo:ok", "123", "456"):
        store.add_watch(owner, "coffee", ["coffee"], once=True)
    monkeypatch.setattr(notifier.people, "woojoo_of", lambda owner: owner if owner.startswith("woojoo:") else None)
    monkeypatch.setattr(notifier, "push_woojoo", lambda email, *args: email == "woojoo:ok")
    monkeypatch.setattr(notifier, "send_dm", lambda owner, payload: owner == "123")
    fallback = Mock(return_value="posted")
    monkeypatch.setattr(notifier, "send_message", fallback)
    monkeypatch.setattr(main.board, "update", Mock())

    main.alert(store, [deal()], False)

    assert [w["owner_id"] for w in store.active_watches()] == ["woojoo:failed"]
    assert [dict(r)["watch_id"] for r in store.db.execute("SELECT watch_id FROM notified ORDER BY watch_id")] == [2, 3, 4]
    fallback.assert_called_once()


def test_fallback_failure_preserves_other_delivery_outcomes(monkeypatch):
    monkeypatch.setattr(notifier.people, "woojoo_of", lambda owner: "test@example.com" if owner == "123" else None)
    monkeypatch.setattr(notifier, "push_woojoo", Mock(return_value=True))
    monkeypatch.setattr(notifier, "send_dm", Mock(return_value=False))
    monkeypatch.setattr(notifier, "send_message", Mock(side_effect=requests.RequestException("failed")))
    hits = [{"owner_id": owner, "want": "coffee"} for owner in ("123", "456")]
    assert notifier.post_alert(hits, deal()) == {"123": True, "456": False}


@pytest.mark.parametrize("failure", ["comment", "board"])
def test_slot_completed_before_commentary(store, main, monkeypatch, failure):
    now = datetime(2026, 10, 25, 21, 0, tzinfo=KST)
    key = "posted:hot:2026-10-25-21"
    pick = {"key": "test:1", "head": deal()}
    monkeypatch.setattr(main.ranking, "top", Mock(return_value=[pick]))
    monkeypatch.setattr(main.ranking, "groups", Mock(return_value=[]))
    monkeypatch.setattr(main, "build_board", Mock(return_value={}))
    posted = Mock(side_effect=RuntimeError("board failed") if failure == "board" else None)
    monkeypatch.setattr(main, "post_board", posted)
    monkeypatch.setattr(main.voice, "standouts", Mock(return_value=[]))
    monkeypatch.setattr(main.voice, "comment", Mock(return_value=["comment"]))
    monkeypatch.setattr(main.time, "sleep", Mock())
    monkeypatch.setattr(main, "send_message", Mock(side_effect=RuntimeError("comment failed")))

    with pytest.raises(RuntimeError):
        main.post(store, "hot", False, slot_key=key)
    due = main.due_boards(store, now)
    if failure == "comment":
        assert store.get_meta(key) is not None
        assert ("hot", key) not in due
        assert store.posted_keys("hot") == {"test:1"}
    else:
        assert store.get_meta(key) is None
        assert ("hot", key) in due
    posted.assert_called_once()


def mention(message_id):
    return {"id": message_id, "author": {"id": "123", "username": "tester"},
            "mentions": [{"id": "999"}], "content": "<@999> coffee alert"}


def mock_mentions(monkeypatch, messages):
    monkeypatch.setattr(mentions, "_get", lambda path, **params: {"id": "999"} if path == "/users/@me" else messages)
    parsed = Mock(return_value={"calls": [("add_watch", {"want": "coffee", "keywords": ["coffee"]})]})
    monkeypatch.setattr(mentions.nl, "parse_command", parsed)
    monkeypatch.setattr(commands.board, "update", Mock())
    return parsed


def test_failed_reply_retries_saved_result_after_reopen(store, monkeypatch):
    store.set_meta(mentions.LAST_KEY, "0")
    parsed = mock_mentions(monkeypatch, [mention("1")])
    send = Mock(side_effect=requests.RequestException("failed"))
    monkeypatch.setattr(mentions, "send_message", send)
    with pytest.raises(requests.RequestException):
        mentions.process(store)
    assert len(store.active_watches()) == 1
    assert store.get_meta(mentions.LAST_KEY) == "0"
    reopened = Store(store.db.execute("PRAGMA database_list").fetchone()[2])
    try:
        send.side_effect = None
        send.return_value = "reply"
        assert mentions.process(reopened) == 1
        assert len(reopened.active_watches()) == 1
        assert reopened.get_meta(mentions.LAST_KEY) == "1"
    finally:
        reopened.db.close()
    parsed.assert_called_once()
    assert send.call_args_list[0] == send.call_args_list[1]


def test_three_failed_replies_do_not_block_later_mentions(store, monkeypatch):
    store.set_meta(mentions.LAST_KEY, "0")
    parsed = mock_mentions(monkeypatch, [mention("1"), mention("2")])

    def send(channel, payload, message_id):
        if message_id == "1":
            raise requests.RequestException("failed")
        return "reply"

    monkeypatch.setattr(mentions, "send_message", send)
    for _ in range(2):
        with pytest.raises(requests.RequestException):
            mentions.process(store)
    assert mentions.process(store) == 1
    assert store.get_meta(mentions.LAST_KEY) == "2"
    assert len(store.active_watches()) == 2
    assert parsed.call_count == 2


def test_command_batch_rolls_back_without_handled_record(store, monkeypatch):
    monkeypatch.setattr(commands.board, "update", Mock())
    handler = commands.Handler(store)
    with pytest.raises(KeyError):
        handler.handle("1", "123", [("add_watch", {"want": "coffee"}), ("add_watch", {})])
    assert store.active_watches() == []
    assert store.handled_replies("1") is None
    handler.handle("1", "123", [("add_watch", {"want": "coffee"})])
    handler.handle("1", "123", [("add_watch", {"want": "coffee"})])
    assert len(store.active_watches()) == 1


def test_existing_price_drop_reaches_alert_pipeline(store, main, monkeypatch):
    store.add_watch("123", "coffee", ["coffee"])
    store.record_deals("test", [deal()])
    store.mark_notified(1, "test:1", 100)
    monkeypatch.setattr(main.sources, "SOURCES", ["test"])
    collect = Mock(return_value=([deal(80)], []))
    monkeypatch.setattr(main.sources, "collect", collect)
    send = Mock(return_value={"123": True})
    monkeypatch.setattr(main, "post_alert", send)

    main.collect_and_alert(store, False)
    send.assert_called_once()
    hits, candidate, _ = send.call_args.args
    assert hits[0]["price_drop"] is True
    assert candidate["group_key"] == "test:1"
    assert store.notify_kind(1, "test:1", 80) is None
    main.collect_and_alert(store, False)
    collect.return_value = ([deal(90)], [])
    main.collect_and_alert(store, False)
    collect.return_value = ([deal(80)], [])
    main.collect_and_alert(store, False)
    send.assert_called_once()


@pytest.mark.parametrize("old,new", [(100, 100), (100, 110), (None, 80), (100, None)])
def test_non_drops_are_not_candidates(store, old, new):
    store.record_deals("test", [deal(old)])
    assert store.record_deals("test", [deal(new)]) == []
    assert store.recent_deals()[0]["price"] == new


def test_multiple_commands_are_not_reapplied_when_second_reply_fails(store, monkeypatch):
    store.set_meta(mentions.LAST_KEY, "0")
    parsed = mock_mentions(monkeypatch, [mention("1")])
    parsed.return_value["calls"].append(("add_watch", {"want": "tea", "keywords": ["tea"]}))
    send = Mock(side_effect=["reply", requests.RequestException("failed")])
    monkeypatch.setattr(mentions, "send_message", send)
    with pytest.raises(requests.RequestException):
        mentions.process(store)
    assert len(store.active_watches()) == 2
    send.side_effect = None
    send.return_value = "reply"
    assert mentions.process(store) == 1
    assert len(store.active_watches()) == 2
    parsed.assert_called_once()


def test_dry_run_does_not_apply_or_cache_commands(store, monkeypatch):
    store.set_meta(mentions.LAST_KEY, "0")
    mock_mentions(monkeypatch, [mention("1")])
    send = Mock()
    monkeypatch.setattr(mentions, "send_message", send)
    mentions.process(store, dry_run=True)
    assert store.active_watches() == []
    assert store.handled_replies("1") is None
    assert store.get_meta(mentions.LAST_KEY) == "0"
    send.assert_not_called()
