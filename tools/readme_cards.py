"""README용: 실제 카드 메시지를 디스코드에 올라온 모습처럼 한 장으로 (다크 테마, 2배 해상도).

지금 딜을 출처에서 한 번 읽어 임시 DB로 인기 카드와 알림 카드를 만들고, docs/images/에 PNG로 저장한다.
알림 카드의 멘션은 가명, 커뮤니티 이름은 "커뮤니티"로 가린다. 실행: .venv/bin/python -m tools.readme_cards  (Pillow 필요, 실행용 의존성 아님)
"""
from __future__ import annotations

import re
import tempfile
import urllib.request
from datetime import datetime, timedelta
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from app import ranking, sources
from app.notifier import BOARD_COLOR, board_header, build_alert, build_board
from app.store import KST, Store

OUT = Path("docs/images")
AVATAR = OUT / "avatar.png"  # 캐릭터 (디스코드 봇 프로필과 같음)
CACHE = Path(tempfile.gettempdir()) / "sallae-readme"
FONT = "/System/Library/Fonts/AppleSDGothicNeo.ttc"  # 4 SemiBold, 6 Bold
TWEMOJI = "https://cdn.jsdelivr.net/gh/jdecked/twemoji@15.1.0/assets/72x72"
S = 2
BG, CARD, TEXT, MUTED = (49, 51, 56), (43, 45, 49), (219, 222, 225), (148, 155, 164)
NAME, LINK, LINE = (242, 243, 245), (0, 168, 252), (63, 65, 71)
MENTION_BG, MENTION, BUTTON, BLURPLE = (60, 66, 112), (201, 205, 251), (78, 80, 88), (88, 101, 242)
W, LEFT, CARD_W, PAD, THUMB = 600, 72, 512, 14, 72
EMOJI = re.compile(r"[\U0001F000-\U0001FAFF☀-➿⭐]️?")


def _f(size: float, bold: bool = False) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(FONT, round(size * S), index=6 if bold else 4)


def _fetch(url: str) -> bytes | None:
    path = CACHE / re.sub(r"[^A-Za-z0-9._-]", "_", url)[-150:]
    if path.exists():
        return path.read_bytes()
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        data = urllib.request.urlopen(req, timeout=15).read()
    except Exception:
        return None
    CACHE.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return data


def _emoji(ch: str, size: int) -> Image.Image | None:
    code = "-".join(f"{ord(c):x}" for c in ch if c != "️")
    data = _fetch(f"{TWEMOJI}/{code}.png")
    return Image.open(BytesIO(data)).convert("RGBA").resize((size, size), Image.LANCZOS) if data else None


def _runs(line: str) -> list[tuple[str, bool, bool]]:
    """**굵게**와 [링크](주소)를 (글자, 굵게, 링크) 조각으로."""
    out = []
    for part in re.split(r"(\*\*.+?\*\*)", line):
        bold = part.startswith("**") and part.endswith("**") and len(part) > 4
        part = part[2:-2] if bold else part
        for piece in re.split(r"(\[[^\]]+\]\([^)]+\))", part):
            link = re.fullmatch(r"\[([^\]]+)\]\([^)]+\)", piece)
            if piece:
                out.append((link.group(1) if link else piece, bold or bool(link), bool(link)))
    return out


def _line_style(raw: str) -> tuple[str, float, bool, tuple]:
    if raw.startswith("## "):
        return raw[3:], 19, True, NAME
    if raw.startswith("### "):
        return raw[4:], 16.5, True, NAME
    if raw.startswith("-# "):
        return raw[3:], 12.5, False, MUTED
    return raw, 14.5, False, TEXT


def _draw_line(img: Image.Image, x: float, y: float, raw: str, width: float) -> float:
    """한 줄을 그리고 줄 높이를 돌려준다. 넓으면 끝을 …로 줄인다."""
    text, size, bold_line, color = _line_style(raw.replace("`", ""))
    d = ImageDraw.Draw(img)
    h = (size + 7) * S
    cx, limit = x, x + width
    for piece, bold, link in _runs(text):
        f = _f(size, bold or bold_line)
        fill = LINK if link else (NAME if bold else color)
        for token in re.split(f"({EMOJI.pattern})", piece):
            if not token:
                continue
            if EMOJI.fullmatch(token):
                em = _emoji(token, round(size * 1.15 * S))
                if em and cx + em.width <= limit:
                    img.paste(em, (round(cx), round(y + h / 2 - em.height / 2)), em)
                    cx += em.width + 2 * S
                continue
            if cx + d.textlength(token, font=f) > limit:
                while token and cx + d.textlength(token + "…", font=f) > limit:
                    token = token[:-1]
                d.text((cx, y + h / 2), token + "…", font=f, fill=fill, anchor="lm")
                return h
            d.text((cx, y + h / 2), token, font=f, fill=fill, anchor="lm")
            cx += d.textlength(token, font=f)
    return h


def _thumb(url: str) -> Image.Image | None:
    data = _fetch(url)
    if not data:
        return None
    im = Image.open(BytesIO(data)).convert("RGB")
    side = min(im.size)
    im = im.crop(((im.width - side) // 2, (im.height - side) // 2, (im.width + side) // 2, (im.height + side) // 2))
    im = im.resize((THUMB * S, THUMB * S), Image.LANCZOS)
    mask = Image.new("L", im.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, im.width - 1, im.height - 1), radius=6 * S, fill=255)
    return Image.composite(im, Image.new("RGB", im.size, CARD), mask)


def _item_height(item: dict, probe: Image.Image, width: float) -> float:
    if item["type"] == 9:
        lines = item["components"][0]["content"].split("\n")
        return max(sum(_draw_line(probe, 0, 0, l, width) for l in lines), THUMB * S) + 8 * S
    if item["type"] == 10:
        return sum(_draw_line(probe, 0, 0, l, width) for l in item["content"].split("\n")) + 6 * S
    if item["type"] == 14:
        return 14 * S if item.get("divider", True) else 6 * S
    if item["type"] == 1:
        return 40 * S
    return 0


def render(payload: dict, channel: str, mentions: list[str] = (), time: str = "오늘 오후 9:00") -> Image.Image:
    probe = Image.new("RGB", (W * S, 400 * S))
    top_texts = [c["content"] for c in payload["components"] if c["type"] == 10]
    container = next(c for c in payload["components"] if c["type"] == 17)
    inner = (CARD_W - PAD * 2) * S
    text_w = inner - (THUMB + 12) * S
    header_h = sum(_draw_line(probe, 0, 0, l, (W - LEFT - 16) * S) for t in top_texts for l in t.split("\n"))
    card_h = PAD * 2 * S + sum(_item_height(i, probe, text_w if i["type"] == 9 else inner) for i in container["components"])
    bar, top = 48 * S, 64 * S
    card_y = top + 26 * S + header_h + 6 * S
    img = Image.new("RGB", (W * S, round(card_y + card_h + 18 * S)), BG)
    d = ImageDraw.Draw(img)

    d.text((16 * S, bar / 2), "#", font=_f(22), fill=MUTED, anchor="lm")
    _draw_line(img, 40 * S, bar / 2 - 12 * S, f"**{channel}**", (W - 60) * S)
    d.line((0, bar, W * S, bar), fill=(31, 32, 35), width=S)
    avatar = Image.open(AVATAR).convert("RGB").resize((40 * S, 40 * S), Image.LANCZOS)  # 봇 프로필 사진
    ring = Image.new("L", (160 * S, 160 * S), 0)
    ImageDraw.Draw(ring).ellipse((0, 0, ring.width - 1, ring.height - 1), fill=255)
    img.paste(avatar, (16 * S, top), ring.resize(avatar.size, Image.LANCZOS))
    d.text((LEFT * S, top + 10 * S), "살래말래", font=_f(16, True), fill=NAME, anchor="lm")
    x = LEFT * S + d.textlength("살래말래", font=_f(16, True)) + 6 * S
    d.rounded_rectangle((x, top + 3 * S, x + 26 * S, top + 17 * S), radius=3 * S, fill=BLURPLE)
    d.text((x + 13 * S, top + 10 * S), "앱", font=_f(10, True), fill=(255, 255, 255), anchor="mm")
    d.text((x + 34 * S, top + 10 * S), time, font=_f(12), fill=MUTED, anchor="lm")

    y = top + 26 * S
    for t in top_texts:
        for line in t.split("\n"):
            if mentions and "<@" in line:  # 멘션은 가명 배지로
                mx = LEFT * S
                for name in mentions:
                    label = f"@{name}"
                    w = d.textlength(label, font=_f(14.5)) + 4 * S
                    d.rounded_rectangle((mx, y + 2 * S, mx + w, y + 22 * S), radius=3 * S, fill=MENTION_BG)
                    d.text((mx + 2 * S, y + 12 * S), label, font=_f(14.5), fill=MENTION, anchor="lm")
                    mx += w + 4 * S
                rest = re.sub(r"<@\d+>님?,?\s*", "", line).strip()
                y += _draw_line(img, mx + 2 * S, y, rest, (W - 16) * S - mx)
            else:
                y += _draw_line(img, LEFT * S, y, line, (W - LEFT - 16) * S)

    accent = container.get("accent_color", 0)
    cx0, cy0 = LEFT * S, card_y
    d.rounded_rectangle((cx0, cy0, cx0 + CARD_W * S, cy0 + card_h), radius=8 * S, fill=CARD)
    d.rounded_rectangle((cx0, cy0, cx0 + 8 * S, cy0 + card_h), radius=8 * S,
                        fill=((accent >> 16) & 255, (accent >> 8) & 255, accent & 255))
    d.rectangle((cx0 + 4 * S, cy0, cx0 + 8 * S, cy0 + card_h), fill=CARD)
    x0, y = cx0 + PAD * S, cy0 + PAD * S
    for item in container["components"]:
        h = _item_height(item, probe, text_w if item["type"] == 9 else inner)
        if item["type"] == 9:
            ly = y
            for line in item["components"][0]["content"].split("\n"):
                ly += _draw_line(img, x0, ly, line, text_w)
            th = _thumb(item["accessory"]["media"]["url"])
            if th:
                img.paste(th, (x0 + inner - th.width, round(y)))
        elif item["type"] == 10:
            ly = y
            for line in item["content"].split("\n"):
                ly += _draw_line(img, x0, ly, line, inner)
        elif item["type"] == 14 and item.get("divider", True):
            d.line((x0, y + h / 2, x0 + inner, y + h / 2), fill=LINE, width=S)
        elif item["type"] == 1:
            bx = x0
            for b in item["components"]:
                label = f"{b['label']}  ↗"
                w = d.textlength(label, font=_f(14, True)) + 32 * S
                d.rounded_rectangle((bx, y + 4 * S, bx + w, y + 36 * S), radius=4 * S, fill=BUTTON)
                d.text((bx + w / 2, y + 20 * S), label, font=_f(14, True), fill=NAME, anchor="mm")
                bx += w + 8 * S
        y += h
    return img


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        store = Store(Path(tmp) / "readme.db")
        deals, _ = sources.collect(datetime.now(KST) - timedelta(hours=16))
        for source in sources.SOURCES:
            store.record_deals(source, [d for d in deals if d["source"] == source])
        recent = store.recent_deals(hours=16)
        now = datetime.now(KST).replace(hour=21)
        picks = ranking.top(recent, 5)
        for g in picks:  # README에는 커뮤니티 이름을 쓰지 않는다
            g["communities"] = ["커뮤니티"] if len(g["communities"]) < 2 else [f"커뮤니티 {len(g['communities'])}곳"]
        hot = build_board(board_header(now, "인기", "🔥"), "저녁 TOP 5", picks, BOARD_COLOR["hot"],
                          ("인기 핫딜 더 보기", "https://example.com/"))
        usable = [d for d in recent if d.get("image_url") and d.get("product_url") and d.get("price_str")]
        deal = next((d for d in usable if "모니터" in d["title"]), None)
        hit = {"owner_id": "1", "want": "게이밍 모니터", "price_drop": False, "reason": "사양이 게임용에 맞고 반응도 많아요."}
        if deal is None:  # 모니터 딜이 없으면 키워드 알림 예시로
            deal = usable[0]
            hit |= {"want": deal["title"].split()[0], "reason": None}
        alert = build_alert([hit], deal | {"community": "커뮤니티"})
        store.db.close()
    OUT.mkdir(parents=True, exist_ok=True)
    for name, payload, mentions in (("card-hot", hot, ()), ("card-alert", alert, ["민수"])):
        render(payload, "🔥 핫딜", mentions).save(OUT / f"{name}.png", optimize=True)
        print(OUT / f"{name}.png")


if __name__ == "__main__":
    main()
