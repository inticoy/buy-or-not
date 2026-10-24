"""@멘션 처리: 상주 봇 대신 실행할 때마다 핫딜 thread의 새 메시지를 읽어 봇을 부른 말에 답한다.

봇을 멘션한 메시지는 Message Content 권한 없이도 내용을 읽을 수 있다.
"""
import logging
import re

import requests

from . import nl, people
from . import monitoring
from .commands import HELP, Handler, text
from .notifier import API_BASE, BOT_TOKEN, CHANNEL_ID, THREAD_ID, message_link, push_woojoo, send_dm, send_message
from .store import Store

logger = logging.getLogger(__name__)

HEADERS = {"Authorization": f"Bot {BOT_TOKEN}"}
LAST_KEY = "mentions:last_message_id"


def _get(path: str, **params) -> list | dict:
    resp = requests.get(f"{API_BASE}{path}", headers=HEADERS, params=params, timeout=10)
    resp.raise_for_status()
    return resp.json()


def _name(user: dict) -> str:
    return user.get("global_name") or user.get("username") or "친구"


def process(store: Store, dry_run: bool = False) -> int:
    """지난번 이후 새 메시지 중 봇을 부른 것에 답한다. 답한 개수."""
    channel = THREAD_ID or CHANNEL_ID
    me = _get("/users/@me")["id"]
    last = store.get_meta(LAST_KEY)
    if last is None:  # 처음엔 지난 메시지에 답하지 않고 위치만 잡는다
        latest = _get(f"/channels/{channel}/messages", limit=1)
        store.set_meta(LAST_KEY, latest[0]["id"] if latest else "0")
        return 0

    messages = sorted(_get(f"/channels/{channel}/messages", after=last, limit=100), key=lambda m: int(m["id"]))
    handler, answered = Handler(store), 0
    for msg in messages:
        if not msg["author"].get("bot") and any(u["id"] == me for u in msg.get("mentions", [])):
            try:
                _answer(handler, store, channel, me, msg, dry_run)
                answered += 1
            except Exception as exc:
                if dry_run:
                    raise
                key = f"mentions:attempts:{msg['id']}"
                attempts = int(store.get_meta(key) or "0") + 1
                store.set_meta(key, str(attempts))
                monitoring.error("discord.reply", exc, "멘션 답장 실패")
                if attempts < 3:
                    raise
                logger.warning("giving up reply after %d attempts", attempts)
        if not dry_run:
            store.set_meta(LAST_KEY, msg["id"])  # 하나씩 기록해 실패해도 같은 말에 두 번 답하지 않는다
    return answered


def _answer(handler: Handler, store: Store, channel: str, me: str, msg: dict, dry_run: bool) -> None:
    payloads = None if dry_run else store.handled_replies(msg["id"])
    if payloads is None:
        payloads = _prepare(handler, store, me, msg, dry_run)
        if not dry_run and store.handled_replies(msg["id"]) is None:
            store.mark_handled(msg["id"], payloads)
    for payload in payloads:
        payload = payload.copy()
        dm = payload.pop("_dm", None)
        if dry_run:
            print("[DRY RUN] reply:", payload)
            continue
        message_id = send_message(channel, payload, msg["id"])
        if dm and message_id:
            if people.is_discord(dm[0]):
                send_dm(dm[0], f"{dm[1]}\n→ {message_link(channel, message_id)}")
            elif email := people.woojoo_of(dm[0]):
                push_woojoo(email, "살래말래", dm[1], "https://woojoo.woojoo.workers.dev/")


def _prepare(handler: Handler, store: Store, me: str, msg: dict, dry_run: bool) -> list:
    words = re.sub(rf"<@!?{me}>", "", msg["content"]).strip()
    sender = msg["author"]["id"]
    if not words:
        return [text(HELP)]
    mentions = {f"<@{u['id']}>": _name(u) for u in msg.get("mentions", []) if u["id"] != me}
    try:
        result = nl.parse_command(_name(msg["author"]), words, mentions, store.related_watches(sender))
    except nl.QuotaExceeded as exc:
        monitoring.error("gemini.command", exc, "Gemini 멘션 해석 할당량 초과", "Gemini 할당량·키 확인")
        return [text("오늘 AI 한도를 다 썼어요 😢 내일 다시 말해주세요!")]
    except Exception as exc:
        monitoring.error("gemini.command", exc, "AI 멘션 해석 실패", "Gemini 키·응답 형식 확인")
        logger.exception("parse failed")  # Public Actions logs must not include user chat
        return [text("말을 잘 못 알아들었어요. 다시 한 번 말해주세요!")]

    if not result["calls"]:
        return [text(result["reply"] or HELP)]
    if dry_run:
        return []
    return handler.handle(msg["id"], sender, result["calls"])
