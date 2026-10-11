"""같은 딜(크로스포스트) 판단: 제목이 거의 같거나, 가격이 같고 제목이 비슷하면 같은 딜."""
import re
import unicodedata
from difflib import SequenceMatcher

_TITLE_NOISE = {
    "무료", "할인", "특가", "역대가", "쿠폰", "코드", "리딤", "행사", "배송",
    "에픽게임즈", "스팀", "steam", "gog", "네이버", "쿠팡", "알리", "aliexpress",
}


def same_deal(left: dict, right: dict) -> bool:
    if left.get("url") and left.get("url") == right.get("url"):  # 왓딜이 모은 루리웹 글 = 직접 읽은 루리웹 글
        return True
    if left.get("product_key") and left.get("product_key") == right.get("product_key"):
        return True
    left_title = normalised_title(left.get("title", ""))
    right_title = normalised_title(right.get("title", ""))
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


def normalised_title(title: str) -> str:
    text = unicodedata.normalize("NFKC", title).lower()
    tokens = re.findall(r"[0-9a-z가-힣]+", text)
    return " ".join(token for token in tokens if token not in _TITLE_NOISE)


def parse_price(price_str: str | None) -> int | None:
    """'12,000원' → 12000. 달러·'가격별상이'·0원처럼 원화 금액이 아니면 None."""
    if not price_str or "$" in price_str:
        return None
    match = re.search(r"(\d[\d,]*)\s*원", price_str)
    if not match:
        return None
    value = int(match.group(1).replace(",", ""))
    return value or None
