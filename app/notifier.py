import logging
import os

import requests

logger = logging.getLogger(__name__)

WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL", "")

RANK_EMOJI = {1: "🥇", 2: "🥈", 3: "🥉"}
DAYS_KO = ["월", "화", "수", "목", "금", "토", "일"]

CATEGORY_COLOR = {
    6: 0x5865F2,  # 게임/앱  — 블루퍼플
    2: 0x00B0F4,  # 전자/IT  — 하늘
    3: 0xFEE75C,  # 식품/영양제 — 노랑
}


def _thread_name(date, category_name: str, emoji: str) -> str:
    day = DAYS_KO[date.weekday()]
    return f"{emoji} {date.month}/{date.day}({day}) {category_name} 핫딜"


def _build_description(deals: list) -> str:
    lines = []
    for i, deal in enumerate(deals, 1):
        rank = RANK_EMOJI.get(i, f"**{i}위**")
        price = deal.get("price_str") or "가격 미확인"
        title = deal.get("title", "")
        url = deal.get("url", "")

        lines.append(f"{rank} **[{title}]({url})** — {price}")

        meta = []
        if deal.get("shop"):      meta.append(deal["shop"])
        if deal.get("community"): meta.append(deal["community"])
        if deal.get("recommend") is not None: meta.append(f"👍{deal['recommend']}")
        if deal.get("comments")  is not None: meta.append(f"💬{deal['comments']}")
        if meta:
            lines.append(" · ".join(meta))

        lines.append("")  # 딜 사이 빈 줄

    return "\n".join(lines).strip()


def post_daily(date, category_id: int, category_name: str, emoji: str,
               deals: list, dry_run: bool = False) -> str:
    """포럼 게시글 생성 + embed 한 장에 10개 딜. thread_id 반환."""
    thread_name = _thread_name(date, category_name, emoji)
    description = _build_description(deals)
    color = CATEGORY_COLOR.get(category_id, 0x99AAB5)

    payload = {
        "thread_name": thread_name,
        "content": "👉 오늘 TOP 10",
        "embeds": [{
            "description": description,
            "color": color,
        }],
    }

    if dry_run:
        print(f"\n[DRY RUN] 게시글: {thread_name}")
        print(f"[DRY RUN] embed 내용:\n{description}\n")
        return "DRY_THREAD_ID"

    resp = requests.post(
        f"{WEBHOOK_URL}?wait=true",
        json=payload,
        timeout=10,
    )
    resp.raise_for_status()
    thread_id = resp.json()["channel_id"]
    logger.info("posted: %s (thread_id=%s)", thread_name, thread_id)
    return thread_id
