import logging
import os

import requests

logger = logging.getLogger(__name__)

_ENV = os.environ.get("BOT_ENV", "dev")
BOT_TOKEN = os.environ.get("DISCORD_BOT_TOKEN", "")
CHANNEL_ID = os.environ.get(f"DISCORD_CHANNEL_{_ENV.upper()}", "")

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


def _build_description(deals: list) -> str:
    lines = []
    for i, deal in enumerate(deals, 1):
        line, meta = _deal_line(i, deal)
        lines.append(line)
        if meta:
            lines.append(meta)
        lines.append("")
    return "\n".join(lines).strip()


# ── 스타일별 message 빌더 (thread_name 제외한 message 객체 반환) ──────────────

def _msg_text(deals):
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
        lines.append(f"<{url}>")
        lines.append("")
    return {"content": "👉 오늘 TOP 10\n\n" + "\n".join(lines).strip()}


def _msg_thumb1(deals, color):
    description = _build_description(deals)
    embed = {"description": description, "color": color}
    if deals and deals[0].get("image_url"):
        embed["thumbnail"] = {"url": deals[0]["image_url"]}
    return {"content": "👉 오늘 TOP 10", "embeds": [embed]}


def _msg_thumb3(deals, color):
    embeds = []
    for i, deal in enumerate(deals[:3], 1):
        line, meta = _deal_line(i, deal)
        embed = {"description": line + (f"\n{meta}" if meta else ""), "color": color}
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
        embeds.append({"description": "\n".join(rest_lines).strip(), "color": color})

    return {"content": "👉 오늘 TOP 10", "embeds": embeds}


def _msg_cards(deals, color):
    embeds = []
    for i, deal in enumerate(deals, 1):
        line, meta = _deal_line(i, deal)
        embed = {"description": line + (f"\n{meta}" if meta else ""), "color": color}
        if deal.get("image_url"):
            embed["thumbnail"] = {"url": deal["image_url"]}
        embeds.append(embed)
    return {"content": "👉 오늘 TOP 10", "embeds": embeds}


def _msg_v2(deals, color):
    """Components V2 — Container + Section (좌측 정보 + 우측 썸네일, 일정한 폭)."""
    items = []
    for i, deal in enumerate(deals, 1):
        line, meta = _deal_line(i, deal)
        content = line + (f"\n{meta}" if meta else "")

        items.append({
            "type": 9,  # Section
            "components": [{"type": 10, "content": content}],
            "accessory": {"type": 11, "media": {"url": deal.get("image_url") or PLACEHOLDER_IMG}},
        })


    return {
        "flags": 32768,  # IS_COMPONENTS_V2
        "components": [
            {"type": 10, "content": "👉 오늘 TOP 10"},
            {
                "type": 17,  # Container
                "accent_color": color,
                "components": items,
            },
        ],
    }


# ── 공개 인터페이스 ────────────────────────────────────────────────────────

STYLES = ("text", "thumb1", "thumb3", "cards", "v2")


def post_daily(date, category_id: int, category_name: str, emoji: str,
               deals: list, dry_run: bool = False, style: str = "v2") -> str:
    name = _thread_name(date, category_name, emoji)
    color = CATEGORY_COLOR.get(category_id, 0x99AAB5)

    if style == "text":
        message = _msg_text(deals)
    elif style == "thumb3":
        message = _msg_thumb3(deals, color)
    elif style == "cards":
        message = _msg_cards(deals, color)
    elif style == "v2":
        message = _msg_v2(deals, color)
    else:  # thumb1
        message = _msg_thumb1(deals, color)

    if dry_run:
        import json
        print(f"\n[DRY RUN / style={style}] {name}")
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
    logger.info("posted: %s (thread_id=%s, style=%s)", name, thread_id, style)
    return thread_id
