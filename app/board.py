"""핫딜 thread에 고정해 두는 '알림 키워드' 메시지.

알림이 등록·해제될 때마다 같은 메시지를 수정한다. 수정은 알림을 울리지 않는다.
"""
import json
import logging
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

from . import people
from .notifier import API_BASE, BOT_TOKEN, CHANNEL_ID, THREAD_ID, send_message
from .store import Store

logger = logging.getLogger(__name__)

STATE_FILE = Path("data/board.json")  # {channel_id: message_id}
HEADERS = {"Authorization": f"Bot {BOT_TOKEN}"}
USAGE = ("💬 `@살래말래 메가커피 뜨면 알려줘` · `게이밍 모니터 50만원 이하 뜨면 @친구 한테 알려줘`"
         " · `내 알림` · `메가커피 알림 꺼줘`")


def won(price: int) -> str:
    return f"{price // 10000}만원" if price % 10000 == 0 else f"{price:,}원"


def who(discord_id: str) -> str:
    return people.name_of(discord_id) or f"<@{discord_id}>"


def describe(watch: dict) -> str:
    how = f"키워드 {', '.join(watch['keywords'])}" if watch["keywords"] else "AI 판단"
    extra = (f" · {won(watch['max_price'])} 이하" if watch["max_price"] else "") \
        + (" · 한 번만" if watch["once"] else "")
    by = f" · {who(watch['created_by'])}님이 걸어줌" if watch["created_by"] != watch["owner_id"] else ""
    return f"• **{watch['want']}** ({how}{extra}{by})"


def grouped(watches: list) -> str:
    owners = list(dict.fromkeys(w["owner_id"] for w in watches))
    return "\n\n".join(
        f"**{who(o)}**\n" + "\n".join(describe(w) for w in watches if w["owner_id"] == o)
        for o in owners)


def build(watches: list) -> dict:
    now = datetime.now(ZoneInfo("Asia/Seoul"))
    body = grouped(watches) if watches else "아직 걸어둔 알림이 없어요."
    content = (f"## 🔔 알림 키워드\n-# {now.month}/{now.day} {now:%H:%M} 기준 · {len(watches)}개\n\n"
               f"{body}\n\n{USAGE}")
    # 이름 대신 멘션이 들어가도 알림이 가지 않게 한다
    return {"content": content[:2000], "allowed_mentions": {"parse": []}}


def _load_state() -> dict:
    return json.loads(STATE_FILE.read_text()) if STATE_FILE.exists() else {}


def update(store: Store | None = None, channel_id: str | None = None) -> None:
    """Edit the pinned message, or post and pin a new one if it is missing. Never raises."""
    channel_id = channel_id or THREAD_ID or CHANNEL_ID
    try:
        message = build((store or Store()).active_watches())
        state = _load_state()
        message_id = state.get(channel_id)
        if message_id:
            resp = requests.patch(f"{API_BASE}/channels/{channel_id}/messages/{message_id}",
                                  json=message, headers=HEADERS, timeout=10)
            if resp.ok:
                return
            logger.warning("board edit failed (%s), posting a new one", resp.status_code)

        message_id = send_message(channel_id, message)
        state[channel_id] = message_id
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        STATE_FILE.write_text(json.dumps(state))
        pin = requests.put(f"{API_BASE}/channels/{channel_id}/pins/{message_id}",
                           headers=HEADERS, timeout=10)
        if not pin.ok:
            logger.warning("board pin failed (%s): pin message %s by hand", pin.status_code, message_id)
    except Exception:
        logger.exception("board update failed")
