"""GitHub Actions(데이터센터 IP)에서도 읽히는 핫딜 출처.

- 왓딜(whatdeal.kr) API: 뽐뿌·펨코·아카라이브·퀘이사존·어미새 등 여러 커뮤니티 새 딜, 댓글 수·상품 링크·카테고리
- 루리웹 핫딜, 클리앙 알뜰구매: 목록을 직접 읽어 추천·조회 수까지

hotdeal.zip·알구몬·펨코·퀘이사존·아카라이브는 Actions에서 Cloudflare/Turnstile에 막힌다 (2026-10-11 시험).
딜 하나는 dict: id, source, community, title, price_str, price, shop, category, comments, recommend, views,
url(원문), product_url, product_key, image_url, posted_at(KST ISO), ended.
"""
import logging
import re
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from .dedupe import parse_price
from . import monitoring

logger = logging.getLogger(__name__)

KST = ZoneInfo("Asia/Seoul")
HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                         "(KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36",
           "Accept-Language": "ko-KR,ko;q=0.9"}
GAP_S = 1.5  # 같은 사이트에 연달아 요청하지 않는다

COMMUNITY_KO = {"ppomppu": "뽐뿌", "fmkorea": "펨코", "arca": "아카", "quasarzone_sale": "퀘이사존",
                "quasarzone": "퀘이사존", "ruliweb": "루리웹", "clien": "클리앙", "eomisae": "어미새",
                "dogdrip": "개드립", "coolenjoy": "쿨엔조이", "dcinside": "디시"}
# 카테고리는 왓딜 이름(game·digital·food·living …)으로 맞춘다
RULIWEB_CATEGORY = {"게임S/W": "game", "게임H/W": "game", "PC/하드웨어": "digital", "A/V": "digital",
                    "휴대폰": "digital", "가전": "digital", "음식": "food", "상품권": "etc"}


def _get(url: str) -> requests.Response:
    resp = requests.get(url, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    return resp


def _num(text: str | None) -> int:
    m = re.search(r"\d[\d,]*", text or "")
    return int(m.group().replace(",", "")) if m else 0


def whatdeal(since: datetime, max_pages: int = 5) -> list:
    """since 이후 처음 본 딜. 100개씩 최신순."""
    deals = []
    for page in range(1, max_pages + 1):
        items = _get(f"https://whatdeal.kr/api/deals?per_page=100&page={page}").json().get("data", [])
        for x in items:
            seen = datetime.fromisoformat(x["first_seen_at"]).replace(tzinfo=KST)
            if seen < since or x["community"] == "추천":  # '추천'은 왓딜 자체 쿠팡 추천
                continue
            deals.append({
                "id": f"whatdeal:{x['id']}", "source": "whatdeal",
                "community": COMMUNITY_KO.get(x["community"], x["community"]),
                "title": x.get("clean_title") or x["title"], "price_str": x.get("price"),
                "price": x.get("price_num") or parse_price(x.get("price")), "shop": x.get("shop"),
                "category": x.get("category"), "comments": x.get("comment_count") or 0,
                "recommend": None, "views": None, "url": x["post_url"],
                "product_url": x.get("product_url"), "product_key": x.get("product_url_key") or None,
                "image_url": urljoin("https://whatdeal.kr", x["thumbnail"]) if x.get("thumbnail") else None,
                "posted_at": seen.isoformat(timespec="seconds"),
                "ended": bool(x.get("is_ended")),
            })
        if not items or datetime.fromisoformat(items[-1]["first_seen_at"]).replace(tzinfo=KST) < since:
            break
        time.sleep(GAP_S)
    return deals


def parse_ruliweb(html: str, now: datetime) -> list:
    """루리웹 핫딜 목록. 오늘 글은 시각만, 지난 글은 날짜만 보여서 날짜만 있으면 그날 18시로 둔다."""
    deals = []
    for row in BeautifulSoup(html, "html.parser").select("tr.table_body"):
        if {"notice", "best"} & set(row.get("class", [])):
            continue
        link, when = row.select_one("a.subject_link"), row.select_one(".time")
        if not link or not when:
            continue
        stamp = when.get_text(strip=True)
        if ":" in stamp:
            posted = datetime.combine(now.date(), datetime.strptime(stamp, "%H:%M").time(), KST)
            if posted > now:
                posted -= timedelta(days=1)
        else:
            posted = datetime.strptime(stamp, "%Y.%m.%d").replace(hour=18, tzinfo=KST)
        title = re.sub(r"\s*\(\d+\)$", "", link.get_text(" ", strip=True))
        shop = re.match(r"\[([^\]]+)\]", title)
        price = re.search(r"\(([\d,]+원)", title)
        reply = row.select_one(".num_reply")
        url = link["href"].split("?")[0]
        category = row.select_one(".divsn").get_text(strip=True) if row.select_one(".divsn") else ""
        deals.append({
            "id": f"ruliweb:{url.rsplit('/', 1)[-1]}", "source": "ruliweb", "community": "루리웹",
            "title": title, "price_str": price.group(1) if price else None,
            "price": parse_price(price.group(1)) if price else None, "shop": shop.group(1) if shop else None,
            "category": RULIWEB_CATEGORY.get(category), "comments": _num(reply.get_text()) if reply else 0,
            "recommend": _num(row.select_one(".recomd").get_text()) if row.select_one(".recomd") else None,
            "views": _num(row.select_one(".hit").get_text()) if row.select_one(".hit") else None,
            "url": url, "product_url": None, "product_key": None, "image_url": None,
            "posted_at": posted.isoformat(timespec="seconds"), "ended": "종료" in title,
        })
    return deals


def ruliweb(since: datetime, max_pages: int = 3) -> list:
    now = datetime.now(KST)
    deals = []
    for page in range(1, max_pages + 1):
        rows = parse_ruliweb(_get(f"https://bbs.ruliweb.com/market/board/1020?page={page}").text, now)
        fresh = [d for d in rows if datetime.fromisoformat(d["posted_at"]) >= since]
        deals += fresh
        if len(fresh) < len(rows):
            break
        time.sleep(GAP_S)
    return deals


def parse_clien(html: str) -> list:
    deals = []
    for row in BeautifulSoup(html, "html.parser").select("div.list_item.symph_row"):
        stamp, link = row.select_one(".timestamp"), row.select_one("a[data-role=list-title-text]")
        if not stamp or not link:
            continue
        posted = datetime.fromisoformat(stamp.get_text(strip=True)).replace(tzinfo=KST)
        img = row.select_one(".list_thumbnail img")
        title = link.get_text(" ", strip=True)
        url = "https://www.clien.net" + link["href"].split("?")[0]
        price = re.search(r"([\d,]+원)", title)
        deals.append({
            "id": f"clien:{row.get('data-board-sn')}", "source": "clien", "community": "클리앙",
            "title": title, "price_str": price.group(1) if price else None,
            "price": parse_price(price.group(1)) if price else None, "shop": None, "category": None,
            "comments": int(row.get("data-comment-count") or 0),
            "recommend": _num(row.select_one(".list_symph").get_text()) if row.select_one(".list_symph") else None,
            "views": _num(row.select_one(".list_hit").get_text()) if row.select_one(".list_hit") else None,
            "url": url, "product_url": None, "product_key": None,
            "image_url": img["src"] if img and "noimage" not in img["src"] else None,
            "posted_at": posted.isoformat(timespec="seconds"),
            "ended": "sold_out" in row.get("class", []),
        })
    return deals


def clien(since: datetime) -> list:
    # 알뜰구매는 하루 몇 개뿐이라 첫 쪽이면 충분하다
    return [d for d in parse_clien(_get("https://www.clien.net/service/board/jirum").text)
            if datetime.fromisoformat(d["posted_at"]) >= since]


SOURCES = {"whatdeal": whatdeal, "ruliweb": ruliweb, "clien": clien}


def expired(title: str, today) -> bool:
    """제목의 기간 '(~10/10)', '(10/9~11)' 같은 끝 날짜가 지났는지."""
    m = re.search(r"~\s*(?:(\d{1,2})/)?(\d{1,2})\s*\)", title)
    if not m:
        return False
    start_month = re.search(r"(\d{1,2})/\d{1,2}\s*~", title)
    month = int(m.group(1) or (start_month.group(1) if start_month else today.month))
    try:
        end = today.replace(month=month, day=int(m.group(2)))
    except ValueError:
        return False
    if end > today + timedelta(days=180):  # 12/31 같은 작년 날짜
        end = end.replace(year=end.year - 1)
    return end < today


def collect(since: datetime) -> tuple[list, list]:
    """모든 출처에서 since 이후 딜. 한 곳이 실패해도 나머지는 쓴다. (딜, 실패한 출처)"""
    deals, failed = [], []
    for name, fetch in SOURCES.items():
        try:
            got = fetch(since)
            today = datetime.now(KST).date()
            for d in got:
                d["ended"] = d["ended"] or expired(d["title"], today)
            logger.info("source %s: %d deals", name, len(got))
            deals += got
            monitoring.observe("source." + name)
        except Exception as e:
            monitoring.error("source." + name, e, name + " 수집 실패", "출처 접근 제한·HTTP 상태·파서 확인")
            logger.error("source %s failed: %s", name, e)
            failed.append(name)
    return deals, failed
