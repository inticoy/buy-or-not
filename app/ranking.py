"""모은 딜로 인기·카테고리 순위를 매긴다.

점수 = 커뮤니티 안에서 댓글(추천) 수가 상위 몇 %인지 60% + 댓글 절대 수 40% (댓글 많은 펨코가 위로 오는 편)
     + 여러 커뮤니티에 같이 올라오면 곳마다 0.12.
같은 딜(group_key)은 한 줄, 같은 커뮤니티·쇼핑몰에서 30분 안에 비슷한 가격으로 올라온 딜은 '같은 행사'로 한 줄.
"""
import math
from collections import defaultdict
from datetime import datetime

CATEGORIES = ("game", "digital", "food")
EVENT_WINDOW_S = 30 * 60


def _scores(deals: list) -> None:
    by_community = defaultdict(list)
    for d in deals:
        by_community[d.get("community")].append(d)
    for items in by_community.values():
        for key in ("comments", "recommend"):
            values = sorted(x.get(key) or 0 for x in items)
            for x in items:
                v = x.get(key) or 0
                x[f"_pct_{key}"] = sum(1 for y in values if y < v) / max(len(values) - 1, 1)
    for d in deals:
        pct = d["_pct_comments"] if d.get("recommend") is None else (d["_pct_comments"] + d["_pct_recommend"]) / 2
        d["_score"] = 0.6 * pct + 0.4 * min(math.log1p(d.get("comments") or 0) / math.log1p(60), 1)


def _shop(name: str | None) -> str:
    return (name or "").replace("와우", "").replace("로켓", "").strip()


def same_event(a: dict, b: dict) -> bool:
    if a.get("community") != b.get("community") or not _shop(a.get("shop")) or _shop(a["shop"]) != _shop(b.get("shop")):
        return False
    if a.get("category") != b.get("category") or not a.get("price") or not b.get("price"):
        return False
    gap = abs((datetime.fromisoformat(a["posted_at"]) - datetime.fromisoformat(b["posted_at"])).total_seconds())
    return gap <= EVENT_WINDOW_S and 0.5 <= a["price"] / b["price"] <= 2


def groups(deals: list) -> list[dict]:
    """같은 딜끼리 묶어 점수순. 각 묶음: head(대표 딜), members, communities, comments, score, category, image_url."""
    _scores(deals)
    by_key = defaultdict(list)
    for d in deals:
        by_key[d["group_key"]].append(d)
    result = []
    for members in by_key.values():
        members.sort(key=lambda d: -d["_score"])
        head = members[0]
        if head.get("ended"):
            continue
        communities = list(dict.fromkeys(m["community"] for m in members if m.get("community")))
        result.append({
            "key": head["group_key"], "head": head, "members": members, "communities": communities,
            "comments": sum(m.get("comments") or 0 for m in members),
            "recommend": max((m["recommend"] for m in members if m.get("recommend") is not None), default=None),
            "score": head["_score"] + 0.12 * (len(communities) - 1),
            "category": next((m["category"] for m in members if m.get("category") in CATEGORIES), head.get("category")),
            "image_url": next((m["image_url"] for m in members if m.get("image_url")), None),
            "product_url": next((m["product_url"] for m in members if m.get("product_url")), None),
        })
    return sorted(result, key=lambda g: -g["score"])


def top(deals: list, n: int = 5, category: str | None = None, exclude: set = frozenset()) -> list[dict]:
    picked = []
    for g in groups(deals):
        if g["key"] in exclude or (category and g["category"] != category):
            continue
        event = next((p for p in picked if any(same_event(g["head"], m) for m in p["members"])), None)
        if event:  # 같은 행사는 대표 한 줄에 '외 n개'로
            event.setdefault("same_event", []).append(g)
            continue
        picked.append(g)
        if len(picked) == n:
            break
    return picked
