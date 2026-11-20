"""정기 게시용 상품 행. 대표 원문의 상품·가격·조건을 함께 사용한다."""
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
from io import BytesIO
import logging
from pathlib import Path
import re
import subprocess
from time import monotonic
from urllib.parse import urlsplit

import requests
from PIL import Image, ImageDraw, ImageFont, ImageOps

logger = logging.getLogger(__name__)
AVATAR = Path(__file__).resolve().parents[1] / "docs/images/avatar.png"
MONEY = r"(?:\d{1,3}(?:,\d{3})+|\d+)\s*원"
CONDITIONAL = re.compile(r"체감|적립|캐시백|페이백|환급|포인트|할인\s*시|쿠폰|카드\s*할인|멤버십|멤버쉽|청구할인|정가|원가|단위가|당\s*[₩\d]")
PHOTO_DOMAINS = ("whatdeal.kr", "ppomppu.co.kr", "eomisae.co.kr", "quasarzone.com", "fmkorea.com",
                 "coupangcdn.com", "ruliweb.com", "clien.net", "dogdrip.net")
PACK = re.compile(r"\s+(\d+(?:\.\d+)?\s*(?:kg|mg|g|ml|L|팩|개입|개|통|봉|매|병|캔|박스|세트)\b.*)$", re.I)


@dataclass(frozen=True)
class Row:
    title: str
    detail: str
    price: str
    shop: str
    url: str
    image: str | None


def row(group: dict) -> Row:
    head = group["head"]
    title = " ".join(head["title"].split())
    shop = " ".join((head.get("shop") or "").split())
    if shop in {"기타", "미상", "알 수 없음"}:
        shop = ""
    if shop and title.startswith(f"[{shop}]"):
        title = title[len(shop) + 2:].strip()
    raw = " ".join(str(head.get("price_str") or "").split())
    # 숫자만 추출한 price는 통화·옵션·혜택 조건을 잃을 수 있다.
    price = ""
    explicit_sale = raw and re.search(r"(?:실결제가?|판매가|결제가|구매가)\s*[:：]?\s*" + re.escape(raw) + r"(?![\d,])", title)
    amounts = {v.replace(",", "").replace(" ", "") for v in re.findall(MONEY, title)}
    ordinary_price = not CONDITIONAL.search(title) and (not amounts or amounts == {raw.replace(",", "").replace(" ", "")})
    if re.fullmatch(MONEY, raw) and (ordinary_price or explicit_sale):
        price = f"{int(raw[:-1].strip().replace(',', '')):,}원"
    elif re.fullmatch(r"(?:US\$|\$)\s*\d[\d,]*(?:\.\d{1,2})?", raw) and ordinary_price:
        price = raw
    detail = ""
    if price:
        # 원문의 마지막에 반복된 게시가와 그 뒤의 배송 표기만 분리한다.
        amount = re.escape(raw)
        if raw.endswith("원"):
            amount += "|" + re.escape("₩" + raw[:-1].strip())
        tail = re.search(r"(?:\s*\(|\s+(?:/\s*)?)(?:" + amount
                         + r")(?:\s*/\s*([^()]+))?\)?\s*$", title)
        if tail and ordinary_price:
            title = title[:tail.start()].strip()
            shipping = (tail[1] or "").strip()
            detail = "무료배송" if shipping == "무료" else shipping
    condition = re.search(r"\s+(?=(?:실결제가?|판매가|결제가|구매가|적립 후 체감가|체감가|캐시백 후)\s*[:：]?\s*\d)", title)
    if condition:
        detail = " · ".join(filter(None, (title[condition.end():], detail)))
        title = title[:condition.start()].strip()
    pack = PACK.search(title)
    if pack:
        detail = " · ".join(filter(None, (pack[1], detail)))
        title = title[:pack.start()].rstrip(" ,·")
    # 조건이 붙은 원문 가격 필드는 원문 그대로 보조 줄에 보존한다.
    if raw and not price and CONDITIONAL.search(raw) and raw not in title:
        detail = " · ".join(filter(None, (detail, raw)))
    return Row(title or head["title"], detail, price, shop, head["url"], head.get("image_url"))


def date_label(now: datetime) -> str:
    return f"{now.month}월 {now.day}일 {'월화수목금토일'[now.weekday()]}요일 | {'오전' if now.hour < 12 else '오후'}"


@lru_cache(maxsize=2)
def _font_file(bold):
    pattern = "Noto Sans CJK KR,Apple SD Gothic Neo,sans-serif:lang=ko:weight=" + ("bold" if bold else "regular")
    match = subprocess.check_output(["fc-match", "-f", "%{file}\n%{index}", pattern], text=True, timeout=5)
    path, index = match.splitlines()
    return path, int(index)


@lru_cache(maxsize=16)
def _font(size, bold=False):
    path, index = _font_file(bold)
    return ImageFont.truetype(path, size, index=index)


def _fit(text, font, width, lines):
    """너비에 맞춰 긴 한글·모델명을 접고 마지막 줄에만 말줄임표를 쓴다."""
    result = []
    text = text[:1000]
    for i in range(lines):
        if font.getlength(text) <= width:
            return result + [text] if text else result
        last = i == lines - 1
        suffix = "…" if last else ""
        low, high = 0, len(text)
        while low < high:
            mid = (low + high + 1) // 2
            if font.getlength(text[:mid] + suffix) <= width:
                low = mid
            else:
                high = mid - 1
        cut = low
        if not last and (space := text.rfind(" ", 0, cut + 1)) > cut // 2:
            cut = space
        result.append(text[:cut].rstrip() + suffix)
        text = text[cut:].lstrip()
    return result


def photo(url):
    if not url:
        return None
    try:
        parsed = urlsplit(url)
        host = parsed.hostname or ""
        if (parsed.scheme not in ("http", "https") or parsed.username or parsed.port not in (None, 80, 443)
                or not any(host == domain or host.endswith("." + domain) for domain in PHOTO_DOMAINS)):
            return None
        start = monotonic()
        data = BytesIO()
        with requests.get(url, timeout=(2, 2), stream=True, allow_redirects=False) as response:
            if response.status_code != 200:
                return None
            for chunk in response.iter_content(65536):
                if data.tell() + len(chunk) > 4_000_000 or monotonic() - start > 5:
                    return None
                data.write(chunk)
        with Image.open(data) as image:
            if image.width * image.height > 12_000_000:
                return None
            image.thumbnail((210, 192))
            return ImageOps.exif_transpose(image).convert("RGBA")
    except Exception:
        logger.info("상품 사진을 읽을 수 없어 빈 사진 칸 사용")
        return None


def render(name, date, rows):
    # 먼저 행 높이를 계산해 긴 상품명이나 조건이 가격을 밀어내도 잘리지 않게 한다.
    layout = []
    for item in rows:
        shop = _fit(item.shop, _font(26, True), 170, 1)
        reserved = int(_font(26, True).getlength(shop[0])) + 20 if shop else 0
        title = _fit(item.title, _font(44, True), 742 - reserved, 2)
        detail = _fit(item.detail, _font(28), 742, 2)
        height = max(224, 40 + len(title) * 52 + len(detail) * 36 + (68 if item.price else 0))
        layout.append((item, title, detail, shop, height))
    canvas = Image.new("RGB", (1080, 178 + sum(entry[-1] for entry in layout) + 28), "white")
    draw = ImageDraw.Draw(canvas)

    def label(x, y, text, size, bold=False, color="#181b1d", anchor="lt"):
        draw.text((x, y), text, font=_font(size, bold), fill=color, anchor=anchor)

    with Image.open(AVATAR) as avatar:
        badge = ImageOps.fit(avatar.convert("RGBA"), (92, 92))
        mask = Image.new("L", badge.size)
        ImageDraw.Draw(mask).rounded_rectangle((0, 0, 91, 91), radius=20, fill=255)
        canvas.paste(badge, (48, 46), mask)
    label(164, 46, "살래말래", 24, True, "#53585e")
    label(164, 79, f"{name} 핫딜", 60, True)
    label(1032, 83, date, 26, color="#53585e", anchor="rt")
    y = 178
    draw.line((48, y, 1032, y), fill="#313638", width=2)
    for item, title, detail, shop, height in layout:
        top = y + (height - 192) // 2
        draw.rounded_rectangle((48, top, 257, top + 191), radius=14, fill="#f6f7f8")
        image = photo(item.image)
        if image is not None:
            canvas.paste(image, (48 + (210 - image.width) // 2, top + (192 - image.height) // 2), image)
        else:
            label(153, top + 96, "사진 없음", 22, color="#697177", anchor="mm")
        ty = y + 28
        if shop:
            label(1032, ty + 3, shop[0], 26, True, "#414950", "rt")
        for line in title:
            label(290, ty, line, 44, True)
            ty += 52
        for line in detail:
            label(290, ty, line, 28, color="#454b51")
            ty += 36
        if item.price:
            label(290, ty + 4, item.price, 54, True)
        y += height
        if y < canvas.height - 28:
            draw.line((48, y, 1032, y), fill="#e6e7e9", width=2)
    out = BytesIO()
    canvas.save(out, format="PNG")
    return out.getvalue()
