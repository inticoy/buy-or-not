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


def post_daily(date, category_id: int, category_name: str, emoji: str,
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
