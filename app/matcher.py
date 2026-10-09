"""관심사와 딜 대조.

- keywords가 있는 관심사: 키워드의 단어가 제목에 모두 들어 있으면 매칭
- 설명형 관심사(keywords 없음): Gemini가 판단
"""
from . import nl
from .collector import _normalised_title


def keyword_match(keywords: list, title: str) -> bool:
    normalised = _normalised_title(title)
    return any(
        all(token in normalised for token in _normalised_title(keyword).split())
        for keyword in keywords
    )


def within_price(watch: dict, deal: dict) -> bool:
    # 가격을 모르면 놓치지 않도록 통과시키고, 알림에 '가격 확인 필요'를 붙인다
    return not watch["max_price"] or deal.get("price") is None or deal["price"] <= watch["max_price"]


def match(watches: list, deals: list, judge=nl.judge) -> list[tuple[dict, dict, str | None]]:
    """Return (watch, deal, reason) pairs. reason is None for keyword matches."""
    results = []
    for watch in watches:
        if not watch["keywords"]:
            continue
        for deal in deals:
            if keyword_match(watch["keywords"], deal["title"]) and within_price(watch, deal):
                results.append((watch, deal, None))

    descriptive = [w for w in watches if not w["keywords"]]
    by_watch = {w["id"]: w for w in descriptive}
    by_deal = {d["id"]: d for d in deals}
    for m in judge(descriptive, deals):
        watch, deal = by_watch.get(m["watch_id"]), by_deal.get(str(m["deal_id"]))
        if watch and deal and within_price(watch, deal):
            results.append((watch, deal, m["reason"]))
    return results
