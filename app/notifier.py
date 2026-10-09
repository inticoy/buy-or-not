import logging
import os

import requests

logger = logging.getLogger(__name__)

_ENV = os.environ.get("BOT_ENV", "dev")
BOT_TOKEN = os.environ.get("DISCORD_BOT_TOKEN", "")
CHANNEL_ID = os.environ.get(f"DISCORD_CHANNEL_{_ENV.upper()}", "")
THREAD_ID = os.environ.get(f"DISCORD_THREAD_{_ENV.upper()}", "")

API_BASE = "https://discord.com/api/v10"
PLACEHOLDER_IMG = "https://raw.githubusercontent.com/inticoy/buy-or-not/main/assets/placeholder.png"

RANK_EMOJI = {1: "🥇", 2: "🥈", 3: "🥉"}
DAYS_KO = ["월", "화", "수", "목", "금", "토", "일"]

CATEGORY_COLOR = {
    "hot": 0xED4245,  # hotdeal.zip 인기 — 빨강
    6: 0x5865F2,  # 게임  — 블루퍼플
    2: 0x00B0F4,  # IT   — 하늘
    3: 0xFEE75C,  # 식품  — 노랑
}


def _thread_name(date, category_name: str, emoji: str) -> str:
    day = DAYS_KO[date.weekday()]
    return f"{emoji} {date.month}/{date.day}({day}) {category_name} 핫딜"


def _deal_line(i, deal):
    rank = RANK_EMOJI.get(i, f"**{i}위**")
    price = deal.get("price_str") or "가격 미확인"
    title = deal.get("title", "")
    url = deal.get("url", "")
    line = f"{rank} **[{title}]({url})** — {price}"
    meta = []
    if deal.get("shop"):      meta.append(deal["shop"])
    if deal.get("community"): meta.append(deal["community"])
    if deal.get("recommend") is not None: meta.append(f"👍{deal['recommend']}")
    if deal.get("comments")  is not None: meta.append(f"💬{deal['comments']}")
    return line, " · ".join(meta)


def _build_message(deals, color, header: str | None = None):
    items = []
    for i, deal in enumerate(deals, 1):
        line, meta = _deal_line(i, deal)
        items.append({
            "type": 9,  # Section
            "components": [{"type": 10, "content": line + (f"\n{meta}" if meta else "")}],
            "accessory": {"type": 11, "media": {"url": deal.get("image_url") or PLACEHOLDER_IMG}},
        })

    components = []
    if header:
        components.append({"type": 10, "content": f"## {header}"})
    components += [
        {"type": 10, "content": "👉 오늘 TOP 10"},
        {"type": 17, "accent_color": color, "components": items},
    ]

    return {"flags": 32768, "components": components}  # IS_COMPONENTS_V2


def post_daily(date, category_id: int | str, category_name: str, emoji: str,
               deals: list, dry_run: bool = False) -> str:
    name = _thread_name(date, category_name, emoji)
    color = CATEGORY_COLOR.get(category_id, 0x99AAB5)

    if THREAD_ID:
        # 고정 thread에 댓글로 전송
        message = _build_message(deals, color, header=name)
        if dry_run:
            import json
            print(f"\n[DRY RUN] reply to thread {THREAD_ID}: {name}")
            print(json.dumps(message, ensure_ascii=False, indent=2))
            return THREAD_ID

        resp = requests.post(
            f"{API_BASE}/channels/{THREAD_ID}/messages",
            json=message,
            headers={"Authorization": f"Bot {BOT_TOKEN}"},
            timeout=10,
        )
        if not resp.ok:
            logger.error("Discord error: %s", resp.text)
        resp.raise_for_status()
        msg_id = resp.json()["id"]
        logger.info("posted reply: %s (msg_id=%s, thread_id=%s)", name, msg_id, THREAD_ID)
        return THREAD_ID

    # 포럼 채널에 새 thread 생성
    message = _build_message(deals, color)
    if dry_run:
        import json
        print(f"\n[DRY RUN] {name}")
        print(json.dumps({"name": name, "message": message}, ensure_ascii=False, indent=2))
        return "DRY_THREAD_ID"

    resp = requests.post(
        f"{API_BASE}/channels/{CHANNEL_ID}/threads",
        json={"name": name, "message": message},
        headers={"Authorization": f"Bot {BOT_TOKEN}"},
        timeout=10,
    )
    if not resp.ok:
        logger.error("Discord error: %s", resp.text)
    resp.raise_for_status()
    thread_id = resp.json()["id"]
    logger.info("posted: %s (thread_id=%s)", name, thread_id)
    return thread_id


def post_alert(owner_id: str, watch_want: str, deal: dict, reason: str | None = None,
               price_drop: bool = False, dry_run: bool = False) -> None:
    """관심사에 맞는 딜을 핫딜 thread에 대상자 태그와 함께 보낸다."""
    price = deal.get("price_str") or "가격 미확인"
    if deal.get("price") is None and deal.get("price_str"):
        price += " (가격 확인 필요)"
    meta = " · ".join(x for x in (deal.get("shop"), deal.get("community")) if x)
    lines = [
        f"<@{owner_id}> 🔔 **{watch_want}**" + (" — 가격 인하" if price_drop else ""),
        f"**[{deal['title']}]({deal['url']})** — {price}",
    ]
    if meta:
        lines.append(meta)
    if reason:
        lines.append(f"💬 {reason}")
    message = {
        "content": "\n".join(lines),
        "allowed_mentions": {"users": [owner_id]},  # 대상자만 알림이 가게
        "flags": 4,  # SUPPRESS_EMBEDS: 링크 미리보기 카드 숨김
    }
    if dry_run:
        print(f"\n[DRY RUN] alert → {message['content']}")
        return

    resp = requests.post(
        f"{API_BASE}/channels/{THREAD_ID or CHANNEL_ID}/messages",
        json=message,
        headers={"Authorization": f"Bot {BOT_TOKEN}"},
        timeout=10,
    )
    if not resp.ok:
        logger.error("Discord error: %s", resp.text)
    resp.raise_for_status()
    logger.info("alert sent: %s → %s", watch_want, deal["title"])
