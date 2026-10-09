import json
import re
import logging
import unicodedata
from difflib import SequenceMatcher
from bs4 import BeautifulSoup, NavigableString

from .browser import BrowserFetchError, fetch_html

logger = logging.getLogger(__name__)

BASE = "https://www.algumon.com"
_HYDRATION_MARKER = "deals:{contents:["

_HYDRATION_FIELDS = {
    "id", "siteName", "storeName", "rankNum", "title", "thumbnailUrl", "price",
    "originalLikes", "originalComments",
}
_TITLE_NOISE = {
    "무료", "할인", "특가", "역대가", "쿠폰", "코드", "리딤", "행사", "배송",
    "에픽게임즈", "스팀", "steam", "gog", "네이버", "쿠팡", "알리", "aliexpress",
}


def fetch_rank(category_id: int) -> list:
    url = f"{BASE}/n/deal/rank?categoryId={category_id}"
    try:
        # requests는 Turnstile 챌린지(403)에 막혀 실제 Chrome으로 읽는다
        html = fetch_html(url)
    except BrowserFetchError as e:
        logger.error("fetch failed (categoryId=%s): %s", category_id, e)
        return []

    return parse_rank_html(html, category_id)


def parse_rank_html(html: str, category_id: int) -> list:
    soup = BeautifulSoup(html, "html.parser")
    # Svelte hydration data에는 로그인 없이도 랭킹 20개가 들어 있다. 화면의 HTML
    # 카드가 일부만 SSR되는 경우가 있어, 이 데이터를 우선 사용한다.
    deals = _parse_hydration_deals(soup)
    source = "hydration"
    if not deals:
        source = "html fallback"
        for card in soup.select("div.deal-card-content"):
            try:
                deal = _parse_card(card)
                if deal:
                    deals.append(deal)
            except Exception as e:
                logger.warning("card parse error: %s", e)

    unique_deals = _deduplicate_deals(deals)
    logger.info(
        "categoryId=%s → %d raw / %d unique (%s)",
        category_id, len(deals), len(unique_deals), source,
    )
    return unique_deals[:10]


def _parse_hydration_deals(soup) -> list:
    """Parse the inline Svelte payload without needing a browser runtime."""
    for script in soup.find_all("script"):
        script_text = script.string or script.get_text()
        marker_at = script_text.find(_HYDRATION_MARKER)
        if marker_at < 0:
            continue

        array_at = marker_at + len(_HYDRATION_MARKER) - 1
        contents = _extract_balanced(script_text, array_at, "[", "]")
        if contents is None:
            continue

        deals = []
        for raw_deal in _split_objects(contents[1:-1]):
            values = {field: _read_js_field(raw_deal, field) for field in _HYDRATION_FIELDS}
            deal_id = values["id"]
            title = values["title"]
            if not isinstance(deal_id, int) or not title:
                continue
            thumbnail_url = values["thumbnailUrl"]
            deals.append({
                "rank": values["rankNum"],
                "url": f"{BASE}/n/deal/{deal_id}",
                "title": title,
                "price_str": values["price"] or None,
                "shop": values["storeName"] or None,
                "community": values["siteName"] or None,
                "recommend": values["originalLikes"],
                "comments": values["originalComments"],
                "viewers": None,
                "image_url": _upscale_image(thumbnail_url),
            })
        if deals:
            return deals
    return []


def _extract_balanced(text: str, start: int, opening: str, closing: str) -> str | None:
    """Return a balanced JS array/object while respecting quoted strings."""
    depth = 0
    quoted = False
    escaped = False
    for index in range(start, len(text)):
        char = text[index]
        if quoted:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                quoted = False
            continue
        if char == '"':
            quoted = True
        elif char == opening:
            depth += 1
        elif char == closing:
            depth -= 1
            if depth == 0:
                return text[start:index + 1]
    return None


def _split_objects(text: str) -> list[str]:
    objects = []
    start = None
    depth = 0
    quoted = False
    escaped = False
    for index, char in enumerate(text):
        if quoted:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                quoted = False
            continue
        if char == '"':
            quoted = True
        elif char == "{":
            if depth == 0:
                start = index
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0 and start is not None:
                objects.append(text[start:index + 1])
    return objects


def _read_js_field(raw_deal: str, field: str):
    match = re.search(
        rf"(?:[{{,]){re.escape(field)}:(\"(?:\\.|[^\"\\])*\"|null|true|false|-?\d+(?:\.\d+)?)",
        raw_deal,
    )
    if not match:
        return None
    value = match.group(1)
    if value.startswith('"'):
        return json.loads(value)
    if value == "null":
        return None
    if value == "true":
        return True
    if value == "false":
        return False
    return float(value) if "." in value else int(value)


def _upscale_image(image_url: str | None) -> str | None:
    if not image_url:
        return None
    return re.sub(r"\?d=\d+x\d+$", "?d=512x512", image_url)


def _deduplicate_deals(deals: list) -> list:
    """Keep the higher-ranked result when cross-posts describe the same deal."""
    unique = []
    for deal in deals:
        duplicate = next((kept for kept in unique if _same_deal(deal, kept)), None)
        if duplicate:
            logger.info("duplicate skipped: %s ≈ %s", deal["title"], duplicate["title"])
            continue
        unique.append(deal)
    return unique


def _same_deal(left: dict, right: dict) -> bool:
    left_title = _normalised_title(left.get("title", ""))
    right_title = _normalised_title(right.get("title", ""))
    if not left_title or not right_title:
        return False
    if left_title == right_title:
        return True

    title_similarity = SequenceMatcher(None, left_title, right_title).ratio()
    left_price = (left.get("price_str") or "").strip().lower()
    right_price = (right.get("price_str") or "").strip().lower()
    return title_similarity >= 0.90 or (
        bool(left_price) and left_price == right_price and title_similarity >= 0.84
    )


def _normalised_title(title: str) -> str:
    text = unicodedata.normalize("NFKC", title).lower()
    tokens = re.findall(r"[0-9a-z가-힣]+", text)
    return " ".join(token for token in tokens if token not in _TITLE_NOISE)


def _parse_card(card):
    # URL
    url = None
    for a in card.find_all("a", href=True):
        if re.match(r"/n/deal/\d+", a["href"]):
            url = BASE + a["href"]
            break
    if not url:
        return None

    # 상품 이미지 (512x512로 업스케일)
    img_el = card.select_one("div.avatar img")
    if img_el and img_el.get("src"):
        image_url = re.sub(r'\?d=\d+x\d+$', '?d=512x512', img_el["src"])
    else:
        image_url = None

    # 랭킹 순위
    rank_el = card.select_one(".deal-card-rank, span.badge-warning")
    rank_match = re.search(r"\d+", rank_el.get_text(" ", strip=True)) if rank_el else None
    rank = int(rank_match.group()) if rank_match else None

    # 제목
    title_el = card.select_one("h3")
    title = title_el.get_text(strip=True) if title_el else None

    # 가격 (첫 텍스트 노드만 — "(24 x 804원)" 제외)
    # 알구몬의 새 카드 구조에서는 가격이 .deal-price-amount 안에 있다.
    price_el = card.select_one(".deal-price-amount") or card.select_one("p.deal-price-text")
    price_str = None
    if price_el:
        first = next((str(c) for c in price_el.children if isinstance(c, NavigableString)), "")
        price_str = first.strip() or None

    # 쇼핑몰
    shop_el = card.select_one(".deal-card-store a, .deal-card-store > span, a.badge")
    shop = shop_el.get_text(strip=True) if shop_el else None

    # 커뮤니티
    comm_el = card.select_one(
        ".deal-source-site .deal-site-name-full, span.badge:not(.badge-warning)"
    )
    community = comm_el.get_text(strip=True) if comm_el else None

    # 추천수 / 댓글수 (새 구조의 의미 있는 클래스 우선, 구 구조 호환 fallback)
    recommend_el = card.select_one(".deal-source-likes .font-medium")
    comments_el = card.select_one(".deal-source-comments .font-medium")
    if recommend_el or comments_el:
        recommend = _to_int(recommend_el.get_text(strip=True)) if recommend_el else None
        comments = _to_int(comments_el.get_text(strip=True)) if comments_el else None
    else:
        fm_spans = card.find_all("span", class_=lambda c: c and "font-medium" in c)
        recommend = _to_int(fm_spans[0].get_text(strip=True)) if len(fm_spans) > 0 else None
        comments = _to_int(fm_spans[1].get_text(strip=True)) if len(fm_spans) > 1 else None

    # 보는중
    viewers = None
    for span in card.select("span.text-primary"):
        t = span.get_text(strip=True)
        if "보는중" in t or "보는 중" in t:
            viewers = _to_int(re.search(r"(\d+)", t).group(1) if re.search(r"(\d+)", t) else None)
            break

    return {
        "rank": rank,
        "url": url,
        "title": title,
        "price_str": price_str,
        "shop": shop,
        "community": community,
        "recommend": recommend,
        "comments": comments,
        "viewers": viewers,
        "image_url": image_url,
    }


def _to_int(val):
    try:
        return int(val) if val is not None else None
    except (ValueError, TypeError):
        return None
