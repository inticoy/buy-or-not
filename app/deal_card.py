"""정기 게시용 상품 행. 대표 원문의 상품·가격·조건을 함께 사용한다."""
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
from io import BytesIO
import logging
import re
import subprocess
from time import monotonic
from urllib.parse import urlsplit

import requests
from PIL import Image, ImageDraw, ImageFont, ImageOps

logger = logging.getLogger(__name__)
THEMES = {
    # 인기 점심은 흰색, 저녁 인기만 어둡게. 카테고리와 개인 알림은 아주 연한 색.
    "day": {"bg": "#ffffff", "ink": "#1c1d1e", "sub": "#454b51", "store": "#414950", "rule": "#313638", "row": "#e6e7e9", "tile": "#f6f7f8"},
    "night": {"bg": "#17181c", "ink": "#f2f3f5", "sub": "#b5bac1", "store": "#a8adb4", "rule": "#3a3d44", "row": "#2e3138", "tile": "#26282e"},
    "food": {"bg": "#fff6d8", "ink": "#1c1d1e", "sub": "#454b51", "store": "#414950", "rule": "#e4d7a4", "row": "#efe3b4", "tile": "#fffdf6"},
    "game": {"bg": "#fde8e8", "ink": "#1c1d1e", "sub": "#454b51", "store": "#414950", "rule": "#f0c8c8", "row": "#f3d0d0", "tile": "#fff7f7"},
    "it": {"bg": "#e7f6fe", "ink": "#1c1d1e", "sub": "#454b51", "store": "#414950", "rule": "#c9e6f4", "row": "#d4ebf6", "tile": "#f5fcff"},
}
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


def date_label(now: datetime, when: str | None = None) -> str:
    period = when or ("오전" if now.hour < 12 else "오후")
    return f"{now.month}월 {now.day}일 {'월화수목금토일'[now.weekday()]}요일 | {period}"


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


def _layout(item, text_width):
    shop = _fit(item.shop, _font(26, True), 170, 1)
    reserved = int(_font(26, True).getlength(shop[0])) + 20 if shop else 0
    title = _fit(item.title, _font(44, True), text_width - reserved, 2)
    detail = _fit(item.detail, _font(28), text_width, 2)
    height = max(224, 40 + len(title) * 52 + len(detail) * 36 + (68 if item.price else 0))
    return title, detail, shop, height


def _paint_row(canvas, draw, colors, item, title, detail, shop, box, text_at):
    def label(x, y, text, size, bold=False, color=None, anchor="lt"):
        draw.text((x, y), text, font=_font(size, bold), fill=color or colors["ink"], anchor=anchor)

    left, top = box
    draw.rounded_rectangle((left, top, left + 209, top + 191), radius=14, fill=colors["tile"])
    image = photo(item.image)
    if image is not None:
        canvas.paste(image, (left + (210 - image.width) // 2, top + (192 - image.height) // 2), image)
    else:
        label(left + 105, top + 96, "사진 없음", 22, color="#697177", anchor="mm")
    x, ty = text_at
    if shop:
        label(1032, ty + 3, shop[0], 26, True, colors["store"], "rt")
    for line in title:
        label(x, ty, line, 44, True)
        ty += 52
    for line in detail:
        label(x, ty, line, 28, color=colors["sub"])
        ty += 36
    if item.price:
        label(x, ty + 4, item.price, 54, True)


def render(name, date, rows, theme="day"):
    # 먼저 행 높이를 계산해 긴 상품명이나 조건이 가격을 밀어내도 잘리지 않게 한다.
    colors = THEMES[theme]
    layout = [_layout(item, 742) for item in rows]
    header, bottom = 132, 48  # 아래 여백은 좌우(48)와 같다.
    canvas = Image.new("RGB", (1080, header + sum(entry[-1] for entry in layout) + bottom), colors["bg"])
    draw = ImageDraw.Draw(canvas)

    def label(x, y, text, size, bold=False, color=None, anchor="lt"):
        draw.text((x, y), text, font=_font(size, bold), fill=color or colors["ink"], anchor=anchor)

    label(48, 36, f"{name} 핫딜", 60, True)
    label(1032, 58, date, 26, color=colors["sub"], anchor="rt")
    y = header
    draw.line((48, y, 1032, y), fill=colors["rule"], width=2)
    for item, (title, detail, shop, height) in zip(rows, layout):
        _paint_row(canvas, draw, colors, item, title, detail, shop, (48, y + (height - 192) // 2), (290, y + 28))
        y += height
        if y < canvas.height - bottom:
            draw.line((48, y, 1032, y), fill=colors["row"], width=2)
    out = BytesIO()
    canvas.save(out, format="PNG")
    return out.getvalue()


def render_personal(item, theme="day"):
    """개인 알림. 제목 줄 없이 상품 하나, 상하좌우 여백은 같다."""
    colors = THEMES[theme]
    pad = 56
    title, detail, shop, height = _layout(item, 1080 - pad * 2 - 242)
    row_h = max(height, 224)
    canvas = Image.new("RGB", (1080, pad + row_h + pad), colors["bg"])
    draw = ImageDraw.Draw(canvas)
    top = pad + (row_h - 192) // 2
    _paint_row(canvas, draw, colors, item, title, detail, shop, (pad, top), (pad + 242, pad + 28))
    out = BytesIO()
    canvas.save(out, format="PNG")
    return out.getvalue()
