import re
import time
import logging
from bs4 import BeautifulSoup, NavigableString
import requests

logger = logging.getLogger(__name__)

BASE = "https://www.algumon.com"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ko-KR,ko;q=0.9",
}


def fetch_rank(category_id: int) -> list:
    url = f"{BASE}/n/deal/rank?categoryId={category_id}"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
    except requests.RequestException as e:
        logger.error("fetch failed (categoryId=%s): %s", category_id, e)
        return []

    soup = BeautifulSoup(resp.content, "html.parser", from_encoding="utf-8")
    deals = []
    for card in soup.select("div.deal-card-content"):
        try:
            deal = _parse_card(card)
            if deal:
                deals.append(deal)
        except Exception as e:
            logger.warning("card parse error: %s", e)

    logger.info("categoryId=%s → %d deals", category_id, len(deals))
    return deals


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
        image_url = re.sub(r'\?d=\d+x\d+$', '?d=1024x1024', img_el["src"])
    else:
        image_url = None

    # 랭킹 순위
    rank_el = card.find("span", class_=lambda c: c and "badge-warning" in c)
    try:
        rank = int(rank_el.get_text(strip=True)) if rank_el else None
    except ValueError:
        rank = None

    # 제목
    title_el = card.select_one("h3")
    title = title_el.get_text(strip=True) if title_el else None

    # 가격 (첫 텍스트 노드만 — "(24 x 804원)" 제외)
    price_el = card.select_one("p.deal-price-text")
    price_str = None
    if price_el:
        first = next((str(c) for c in price_el.children if isinstance(c, NavigableString)), "")
        price_str = first.strip() or None

    # 쇼핑몰
    shop_el = card.select_one("a.badge")
    shop = shop_el.get_text(strip=True) if shop_el else None

    # 커뮤니티
    comm_el = card.select_one("span.badge:not(.badge-warning)")
    community = comm_el.get_text(strip=True) if comm_el else None

    # 추천수 / 댓글수 (font-medium span 순서)
    fm_spans = card.find_all("span", class_=lambda c: c and "font-medium" in c)
    recommend = _to_int(fm_spans[0].get_text(strip=True)) if len(fm_spans) > 0 else None
    comments  = _to_int(fm_spans[1].get_text(strip=True)) if len(fm_spans) > 1 else None

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
