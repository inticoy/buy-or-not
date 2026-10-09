"""hotdeal.zip 인기·최신 딜 수집.

여러 커뮤니티(루리웹, FM코리아, 퀘이사존, 뽐뿌 등)의 핫딜을 모아 보여주는 사이트.
목록은 서버 렌더링 HTML이라 a.deal-item만 읽으면 된다.
"""
import logging
import re
from urllib.parse import quote

from bs4 import BeautifulSoup

from .browser import BrowserFetchError, ChromeTab
from .collector import _deduplicate_deals

logger = logging.getLogger(__name__)

BASE = "https://hotdeal.zip"
POPULAR_URL = f"{BASE}/{quote('인기')}"
_ITEMS_JS = "document.querySelectorAll('a.deal-item').length"


def fetch_popular() -> list:
    """오늘 인기 딜 (첫 화면 약 25개)."""
    with ChromeTab(POPULAR_URL) as tab:
        if not tab.wait_until(f"{_ITEMS_JS} > 0"):
            logger.warning("hotdeal.zip popular: no deal items on page")
        return parse_deals(tab.html())


def top10() -> list:
    """오늘 인기에서 크로스포스트를 뺀 상위 10개. 못 가져오면 []."""
    try:
        deals = fetch_popular()
    except BrowserFetchError as e:
        logger.error("hotdeal.zip fetch failed: %s", e)
        return []
    return _deduplicate_deals(deals)[:10]


def fetch_latest(pages: int = 3) -> list:
    """전체 최신 딜. 첫 화면 25개가 약 35분 분량이라 '더보기'로 pages번까지 늘린다."""
    with ChromeTab(f"{BASE}/") as tab:
        tab.wait_until(f"{_ITEMS_JS} > 0")
        for _ in range(pages - 1):
            before = int(tab.js(_ITEMS_JS))
            # AppleScript JS는 페이지 함수에 접근할 수 없어 '더보기' 버튼을 클릭한다
            tab.js("(document.getElementById('load-more-btn') || {click() {}}).click(), ''")
            if not tab.wait_until(f"{_ITEMS_JS} > {before}"):
                logger.warning("hotdeal.zip load more stopped at %d items", before)
                break
        return parse_deals(tab.html())


def parse_deals(html: str) -> list:
    soup = BeautifulSoup(html, "html.parser")
    deals = []
    for item in soup.select("a.deal-item[data-id]"):
        def text(selector):
            el = item.select_one(selector)
            return el.get_text(" ", strip=True) if el else None

        title = text("h3.deal-title")
        if not title:
            continue
        price_str = text(".current-price") or text(".deal-price-description")
        community = item.select_one(".community-favicon")
        image = item.select_one(".deal-image img")
        deals.append({
            "id": item["data-id"],
            "url": BASE + item["href"],
            "title": title,
            "price_str": price_str,
            "price": parse_price(price_str),
            "shop": text(".deal-site"),
            "community": community.get("title") if community else None,
            "category": text(".deal-category"),
            "recommend": None,
            "comments": _to_int(text(".deal-comment-count")),
            "posted_at": text(".deal-time"),
            "ago": text(".relative-time"),  # 예: "3분전"
            "image_url": image.get("src") if image else None,
        })
    return deals


def parse_price(price_str: str | None) -> int | None:
    """'12,000원' → 12000. 달러·'가격별상이'·0원처럼 원화 금액이 아니면 None."""
    if not price_str or "$" in price_str:
        return None
    match = re.search(r"(\d[\d,]*)\s*원", price_str)
    if not match:
        return None
    value = int(match.group(1).replace(",", ""))
    return value or None


def _to_int(value: str | None) -> int | None:
    try:
        return int(value) if value else None
    except ValueError:
        return None
