import logging
import os

import requests
from . import monitoring, people

logger = logging.getLogger(__name__)

_ENV = os.environ.get("BOT_ENV", "dev")
BOT_TOKEN = os.environ.get("DISCORD_BOT_TOKEN", "")
CHANNEL_ID = os.environ.get(f"DISCORD_CHANNEL_{_ENV.upper()}", "")
THREAD_ID = os.environ.get(f"DISCORD_THREAD_{_ENV.upper()}", "")

API_BASE = "https://discord.com/api/v10"
# 우주(둘만 쓰는 웹앱)의 푸시 경로. 토큰이 없으면 우주 알림은 건너뛴다
WOOJOO_PUSH_URL = "https://woojoo.woojoo.workers.dev/api/push"
WOOJOO_PUSH_TOKEN = os.environ.get("WOOJOO_PUSH_TOKEN", "")
PLACEHOLDER_IMG = "https://raw.githubusercontent.com/inticoy/buy-or-not/main/assets/placeholder.png"

RANK_EMOJI = {1: "🥇", 2: "🥈", 3: "🥉"}
# @silent: 스레드 글은 아무에게도 푸시가 가지 않게 한다. 관심사 알림은 DM으로만 간다
SUPPRESS_NOTIFICATIONS = 1 << 12
DAYS_KO = ["월", "화", "수", "목", "금", "토", "일"]

BOARD_COLOR = {"hot": 0xED4245, "game": 0x5865F2, "digital": 0x00B0F4, "food": 0xFEE75C}
MAX_TITLE = 70


def _title(text: str) -> str:
    text = text.replace("[", "［").replace("]", "］")  # 링크 문법이 깨지지 않게
    return text if len(text) <= MAX_TITLE else text[:MAX_TITLE - 1] + "…"


def _deal_text(i: int | None, g: dict) -> str:
    """한 딜: 순위·제목(원문 링크) / 가격·쇼핑몰 / 출처·반응."""
    head = g["head"]
    rank = RANK_EMOJI.get(i, f"**{i}위**") + " " if i else ""
    lines = [f"{rank}**[{_title(head['title'])}]({head['url']})**"]
    price = " · ".join(x for x in (f"**{head['price_str']}**" if head.get("price_str") else None, head.get("shop")) if x)
    if price:
        lines.append(price)
    meta = [" · ".join(g["communities"])]
    if g.get("comments"):
        meta.append(f"💬 {g['comments']}")
    if g.get("recommend"):
        meta.append(f"👍 {g['recommend']}")
    if g.get("same_event"):
        meta.append(f"외 {len(g['same_event'])}개 같은 행사")
    lines.append("-# " + " · ".join(m for m in meta if m))
    return "\n".join(lines)


def _media(url: str | None) -> str:
    """디스코드가 받는 이미지 주소로: http(s)만, 한글·공백은 퍼센트 인코딩."""
    from urllib.parse import quote
    if not url or not url.startswith(("http://", "https://")):
        return PLACEHOLDER_IMG
    return quote(url, safe=":/?&=%#+,;@~!$'()*[]")


def _link_button(label: str, url: str) -> dict:
    from urllib.parse import quote
    return {"type": 2, "style": 5, "label": label, "url": quote(url, safe=":/?&=%#+,;@~!$'()*[]")}


def build_board(header: str, subtitle: str, groups: list, color: int, more: tuple[str, str] | None,
                ranked: bool = True) -> dict:
    """딜마다 제목(원문 링크)·가격·출처 + 썸네일. 맨 아래 더 보기 링크 버튼."""
    items = []
    for i, g in enumerate(groups, 1):
        if items:
            items.append({"type": 14, "divider": True, "spacing": 1})
        items.append({"type": 9, "components": [{"type": 10, "content": _deal_text(i if ranked else None, g)}],
                      "accessory": {"type": 11, "media": {"url": _media(g.get("image_url"))}}})
    if more:
        items += [{"type": 14, "divider": False, "spacing": 1}, {"type": 1, "components": [_link_button(*more)]}]
    return {"flags": 32768, "components": [  # IS_COMPONENTS_V2 (@silent는 보낼 때 붙는다)
        {"type": 10, "content": f"## {header}\n-# {subtitle}"},
        {"type": 17, "accent_color": color, "components": items},
    ]}


def board_header(date, name: str, emoji: str) -> str:
    return f"{emoji} {date.month}/{date.day}({DAYS_KO[date.weekday()]}) {name} 핫딜"


def post_board(message: dict, dry_run: bool = False) -> str | None:
    """핫딜 thread(없으면 채널)에 조용히 올린다."""
    if dry_run:
        import json
        print(json.dumps(message, ensure_ascii=False, indent=1)[:3000])
        return None
    return send_message(THREAD_ID or CHANNEL_ID, message)


ALERT_COLOR = 0xF0B232  # 관심사 알림 — 주황


def _silent(message: dict) -> dict:
    return message | {"flags": message.get("flags", 0) | SUPPRESS_NOTIFICATIONS}


_guild_ids = {}


def message_link(channel_id: str, message_id: str) -> str:
    if channel_id not in _guild_ids:
        resp = requests.get(f"{API_BASE}/channels/{channel_id}",
                            headers={"Authorization": f"Bot {BOT_TOKEN}"}, timeout=10)
        _guild_ids[channel_id] = resp.json().get("guild_id", "@me") if resp.ok else "@me"
    return f"https://discord.com/channels/{_guild_ids[channel_id]}/{channel_id}/{message_id}"


def push_woojoo(email: str, title: str, body: str, url: str) -> bool:
    """우주 앱 푸시. 실패해도 디스코드 알림은 그대로 간다."""
    if not WOOJOO_PUSH_TOKEN:
        return False
    try:
        resp = requests.post(WOOJOO_PUSH_URL, json={"to": [email], "title": title, "body": body, "url": url, "category": "hotdeal"},
                             headers={"Authorization": f"Bearer {WOOJOO_PUSH_TOKEN}"}, timeout=15)
        resp.raise_for_status()
        if not resp.json().get("sent"):
            # 기기가 없거나, 받는 사람이 핫딜 알림·조용한 시간을 꺼 뒀을 때. 알림함에는 남는다.
            logger.info("woojoo push: stored in inbox, no device rang")
        return True
    except requests.RequestException as e:
        logger.warning("woojoo push failed: %s", e)
        return False


def send_dm(user_id: str, content: str | dict) -> bool:
    """DM으로 푸시를 보낸다. content는 글 또는 메시지 payload. 상대가 서버 멤버 DM을 막았으면 False."""
    headers = {"Authorization": f"Bot {BOT_TOKEN}"}
    try:
        dm = requests.post(f"{API_BASE}/users/@me/channels", json={"recipient_id": user_id},
                           headers=headers, timeout=10)
        dm.raise_for_status()
        resp = requests.post(f"{API_BASE}/channels/{dm.json()['id']}/messages",
                             json=content if isinstance(content, dict)
                             else {"content": content, "flags": 4},  # 4: 링크 미리보기 숨김
                             headers=headers, timeout=10)
        resp.raise_for_status()
        monitoring.observe("discord.dm")
        return True
    except requests.RequestException as e:
        # 50007 is a recipient's privacy preference, not a service incident.
        response = getattr(e, "response", None)
        blocked = False
        if response is not None:
            try:
                blocked = response.json().get("code") == 50007
            except ValueError:
                pass
        if not blocked:
            monitoring.error("discord.dm", e, "Discord DM 전송 실패")
        detail = e.response.text[:200] if getattr(e, "response", None) is not None else e
        logger.warning("DM failed: %s", detail)
        return False


def send_message(channel_id: str, message: dict, reply_to: str | None = None,
                 silent: bool = True) -> str:
    """Post a raw message payload and return its id. Silent by default."""
    if silent:
        message = _silent(message)
    # 긁어 온 딜 제목에 @everyone·역할 멘션이 섞여 와도 아무도 불리지 않게, 부를 사람은 호출하는 쪽이 정한다
    if "allowed_mentions" not in message:
        message = message | {"allowed_mentions": {"parse": [], "replied_user": bool(reply_to)}}
    if reply_to:
        message = message | {"message_reference": {"message_id": reply_to, "fail_if_not_exists": False}}
    resp = requests.post(
        f"{API_BASE}/channels/{channel_id}/messages",
        json=message,
        headers={"Authorization": f"Bot {BOT_TOKEN}"},
        timeout=10,
    )
    if not resp.ok:
        logger.error("Discord error: %s", resp.text)
    resp.raise_for_status()
    return resp.json()["id"]


def _mentions(user_ids: list) -> str:
    return ", ".join(f"{people.mention(uid)}님" for uid in user_ids)


def build_alert(hits: list, deal: dict, mention: bool = True) -> dict:
    """hits: [{"owner_id", "want", "reason", "price_drop"}] — 같은 딜에 걸린 관심사들.

    mention=False는 DM용: 태그 없이 받는 사람에게 바로 말한다.
    """
    owners = list(dict.fromkeys(h["owner_id"] for h in hits))
    where = deal.get("shop") or deal.get("community") or "커뮤니티"
    drop = " 가격이 더 내려갔어요!" if any(h.get("price_drop") for h in hits) else ""
    to = f"{_mentions(owners)}, " if mention else "🔔 "
    headline = f"{to}{where}에서 **{_title(deal['title'])}** 핫딜이 떴어요!{drop}"

    price = deal.get("price_str") or "가격 미확인"
    if deal.get("price") is None and deal.get("price_str"):
        price += " (가격 확인 필요)"
    meta = " · ".join(x for x in (deal.get("shop"), deal.get("community")) if x)
    if deal.get("comments"):
        meta += f" · 💬 {deal['comments']}"
    body = f"### [{_title(deal['title'])}]({deal['url']})\n💰 **{price}**" + (f"\n-# {meta}" if meta else "")
    watched = " / ".join(dict.fromkeys(f"'{h['want']}'" for h in hits))
    reasons = [f"💬 {h['reason']}" for h in hits if h.get("reason")]
    footer = "\n".join(reasons + [f"-# 🔔 {watched} 알림 · 끄려면 `@살래말래 {hits[0]['want']} 알림 꺼줘`"])

    card = {"type": 9, "components": [{"type": 10, "content": body}],
            "accessory": {"type": 11, "media": {"url": _media(deal.get("image_url"))}}}
    buttons = [_link_button("보러 가기", deal.get("product_url") or deal["url"])]
    if deal.get("product_url"):
        buttons.append(_link_button("원문 보기", deal["url"]))
    return {
        "flags": 32768,  # IS_COMPONENTS_V2
        "components": [
            {"type": 10, "content": headline},
            {"type": 17, "accent_color": ALERT_COLOR, "components": [
                card, {"type": 1, "components": buttons}, {"type": 14}, {"type": 10, "content": footer},
            ]},
        ],
        "allowed_mentions": {"users": [o for o in owners if people.is_discord(o)] if mention else []},  # 대상자만 알림이 가게
    }


def post_alert(hits: list, deal: dict, dry_run: bool = False) -> dict[str, bool]:
    """DM·우주로 알리고 수신자별 성공 여부를 돌려준다. DM을 막은 사람은 thread에서 태그한다."""
    if dry_run:
        print(f"\n[DRY RUN] alert → {build_alert(hits, deal)['components'][0]['content']}")
        return {}
    outcomes = dict.fromkeys((h["owner_id"] for h in hits), False)
    blocked = []
    for owner in dict.fromkeys(h["owner_id"] for h in hits):
        mine = [h for h in hits if h["owner_id"] == owner]
        if email := people.woojoo_of(owner):
            watched = " / ".join(dict.fromkeys(f"'{h['want']}'" for h in mine))
            price = " · ".join(x for x in (deal.get("price_str"), deal.get("shop") or deal.get("community")) if x)
            outcomes[owner] = push_woojoo(email, f"🔔 {deal['title'][:60]}", f"{price}\n{watched} 알림", deal.get("product_url") or deal["url"])
        if people.is_discord(owner):
            if send_dm(owner, build_alert(mine, deal, mention=False)):
                outcomes[owner] = True
            else:
                blocked += mine
    if blocked:
        try:
            send_message(THREAD_ID or CHANNEL_ID, build_alert(blocked, deal), silent=False)
            for hit in blocked:
                outcomes[hit["owner_id"]] = True
        except requests.RequestException as exc:
            logger.warning("alert fallback failed: %s", exc)
    logger.info("alert reached: %d/%d recipient(s) → %s", sum(outcomes.values()), len(outcomes), deal["title"])
    return outcomes
