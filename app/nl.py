"""Gemini 호출을 한 곳에 모은다. 다른 LLM으로 바꿀 때 이 파일만 고친다."""
import json
import logging
import os

logger = logging.getLogger(__name__)

MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash-lite")

_JUDGE_PROMPT = """친구들이 등록한 관심사(watches)와 새로 올라온 핫딜(deals)이 있어.
각 관심사에 맞는 딜을 골라. 관심사 설명과 같은 종류의 상품이거나 그 상품과 직접 관련된 딜이면 넣어.
max_price가 있으면 그 가격(원) 이하만 넣어. 가격을 알 수 없으면 넣어도 돼.
'괜찮은' 같은 말은 사양이 그 용도에 맞고 댓글이 어느 정도 있는 딜로 판단해.
reason은 왜 맞는지 한국어 한 문장으로 써.

watches: {watches}

deals: {deals}"""

_JUDGE_SCHEMA = {
    "type": "object",
    "properties": {"matches": {"type": "array", "items": {
        "type": "object",
        "properties": {
            "watch_id": {"type": "integer"},
            "deal_id": {"type": "string"},
            "reason": {"type": "string"},
        },
        "required": ["watch_id", "deal_id", "reason"],
    }}},
    "required": ["matches"],
}


_client_instance = None


def _client():
    # 임시 객체로 쓰면 호출 도중 연결이 닫혀서, 한 번 만들어 재사용한다
    global _client_instance
    if _client_instance is None:
        from google import genai
        _client_instance = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    return _client_instance


def judge(watches: list, deals: list) -> list[dict]:
    """Ask Gemini which deals fit which descriptive watches, in one request.

    Returns [] when the API fails (quota, network) so keyword matching still runs.
    """
    if not watches or not deals:
        return []
    from google.genai import types

    prompt = _JUDGE_PROMPT.format(
        watches=json.dumps([{"watch_id": w["id"], "want": w["want"], "max_price": w["max_price"]}
                            for w in watches], ensure_ascii=False),
        deals=json.dumps([{"deal_id": d["id"], "title": d["title"], "price": d.get("price_str"),
                           "category": d.get("category"), "comments": d.get("comments")}
                          for d in deals], ensure_ascii=False),
    )
    try:
        resp = _client().models.generate_content(
            model=MODEL, contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json", response_json_schema=_JUDGE_SCHEMA),
        )
        return json.loads(resp.text)["matches"]
    except Exception as e:  # 한도 초과 등: 키워드 매칭은 계속 돌도록 삼킨다
        logger.error("gemini judge failed: %s", e)
        return []
