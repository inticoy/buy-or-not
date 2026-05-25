import logging
import os

import requests

logger = logging.getLogger(__name__)

_ENV = os.environ.get("BOT_ENV", "dev")
WEBHOOK_URL = os.environ.get(f"DISCORD_WEBHOOK_{_ENV.upper()}", "")

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


def _build_description(deals: list) -> str:
    lines = []
    for i, deal in enumerate(deals, 1):
        line, meta = _deal_line(i, deal)
        lines.append(line)
        if meta:
            lines.append(meta)
        lines.append("")
    return "\n".join(lines).strip()


# ── 스타일별 payload 빌더 ──────────────────────────────────────────────────

def _payload_text(thread_name, deals):
    """embed 없이 텍스트만. 제목은 bare URL."""
    lines = []
    for i, deal in enumerate(deals, 1):
        rank = RANK_EMOJI.get(i, f"{i}위")
        price = deal.get("price_str") or "가격 미확인"
        title = deal.get("title", "")
        url = deal.get("url", "")
        meta = []
        if deal.get("shop"):      meta.append(deal["shop"])
        if deal.get("community"): meta.append(deal["community"])
        if deal.get("recommend") is not None: meta.append(f"👍{deal['recommend']}")
        if deal.get("comments")  is not None: meta.append(f"💬{deal['comments']}")
        lines.append(f"{rank} {title} — {price}")
        if meta:
            lines.append(" · ".join(meta))
        lines.append(f"<{url}>")  # 꺽쇠로 auto-embed 억제
        lines.append("")
    return {
        "thread_name": thread_name,
        "content": "👉 오늘 TOP 10\n\n" + "\n".join(lines).strip(),
    }


def _payload_thumb1(thread_name, deals, color):
    """단일 embed + 1위 썸네일."""
    description = _build_description(deals)
    embed = {"description": description, "color": color}
    if deals and deals[0].get("image_url"):
        embed["thumbnail"] = {"url": deals[0]["image_url"]}
    return {
        "thread_name": thread_name,
        "content": "👉 오늘 TOP 10",
        "embeds": [embed],
    }


def _payload_thumb3(thread_name, deals, color):
    """1~3위 각각 embed+이미지, 4~10위 텍스트 embed."""
    embeds = []
    for i, deal in enumerate(deals[:3], 1):
        line, meta = _deal_line(i, deal)
        embed = {
            "description": line + (f"\n{meta}" if meta else ""),
            "color": color,
        }
        if deal.get("image_url"):
            embed["image"] = {"url": deal["image_url"]}
        embeds.append(embed)

    if len(deals) > 3:
        rest_lines = []
        for i, deal in enumerate(deals[3:], 4):
            line, meta = _deal_line(i, deal)
            rest_lines.append(line)
            if meta:
                rest_lines.append(meta)
            rest_lines.append("")
        embeds.append({
            "description": "\n".join(rest_lines).strip(),
            "color": color,
        })

    return {
        "thread_name": thread_name,
        "content": "👉 오늘 TOP 10",
        "embeds": embeds,
    }


def _payload_cards(thread_name, deals, color):
    """딜마다 embed 하나 — 좌측 정보 + 우측 썸네일."""
    embeds = []
    for i, deal in enumerate(deals, 1):
        line, meta = _deal_line(i, deal)
        embed = {
            "description": line + (f"\n{meta}" if meta else ""),
            "color": color,
        }
        if deal.get("image_url"):
            embed["thumbnail"] = {"url": deal["image_url"]}
        embeds.append(embed)
    return {
        "thread_name": thread_name,
        "content": "👉 오늘 TOP 10",
        "embeds": embeds,
    }


# ── 공개 인터페이스 ────────────────────────────────────────────────────────

STYLES = ("text", "thumb1", "thumb3", "cards")


def post_daily(date, category_id: int, category_name: str, emoji: str,
               deals: list, dry_run: bool = False, style: str = "thumb1") -> str:
    thread_name = _thread_name(date, category_name, emoji)
    color = CATEGORY_COLOR.get(category_id, 0x99AAB5)

    if style == "text":
        payload = _payload_text(thread_name, deals)
    elif style == "thumb3":
        payload = _payload_thumb3(thread_name, deals, color)
    elif style == "cards":
        payload = _payload_cards(thread_name, deals, color)
    else:  # thumb1 (기본)
        payload = _payload_thumb1(thread_name, deals, color)

    if dry_run:
        import json
        print(f"\n[DRY RUN / style={style}] 게시글: {thread_name}")
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return "DRY_THREAD_ID"

    resp = requests.post(
        f"{WEBHOOK_URL}?wait=true",
        json=payload,
        timeout=10,
    )
    resp.raise_for_status()
    thread_id = resp.json()["channel_id"]
    logger.info("posted: %s (thread_id=%s, style=%s)", thread_name, thread_id, style)
    return thread_id
