"""Gemini 호출을 한 곳에 모은다. 다른 LLM으로 바꿀 때 이 파일만 고친다."""
import json
import logging
import os

from . import people

logger = logging.getLogger(__name__)

MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash-lite")

_JUDGE_PROMPT = """친구들이 등록한 관심사(watches)와 새로 올라온 핫딜(deals)이 있어.
각 관심사에 맞는 딜을 골라. 상품 종류가 관심사와 같아야 해. 예: '게이밍 모니터'에 게이밍 헤드셋·마우스는 넣지 마.
관심사에 '관련'이라는 말이 있을 때만 주변기기·액세서리까지 넣어. 예: '스위치 관련 할인'에는 프로콘, 스위치용 SD카드도 넣어.
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


_COMMAND_SYSTEM = """너는 친구들 디스코드 방의 핫딜 봇 '살래말래'야.
사용자의 말을 보고 맞는 도구를 호출해. 맞는 도구가 없으면 도구 없이 한두 문장으로 친근하게 답해.
- '나', '내'는 보낸 사람이다. 다른 사람에게 알려달라고 하면 for_user에 그 사람을 넣어. 멘션(<@숫자>)은 그대로 넣어.
- 브랜드·상품명이 있으면 keywords에 넣어. 예: 메가커피 → ["메가커피"], 에어팟 프로 → ["에어팟 프로"], 스위치2나 프로콘 → ["스위치2", "프로콘"].
  '게이밍 모니터', '괜찮은 노트북'처럼 상품 종류나 조건으로만 말하면 keywords를 비워.
- 가격은 원 단위 정수로 바꿔.
- 알림을 끄거나 지워달라고 하면 아래 목록에서 맞는 watch_id를 골라 remove_watch를 불러.
- "메가커피 올라왔어?", "에어팟 핫딜 있었어?"처럼 특정 상품이 떴는지 물으면 search_deals(query=상품). 알림을 걸어달라는 말이 없으면 add_watch를 부르지 마.
- show_deals는 "오늘 핫딜/랭킹/TOP 보여줘"처럼 목록 자체를 원할 때만 불러.
- "지금 뭐 알림 받게 되어있어?", "내 알림"은 list_watch. "다들/전체/모두 뭐 걸어놨어?"처럼 모든 사람 것을 물으면 list_watch(everyone=true).

등록된 친구: {people}
메시지 속 멘션: {mentions}
보낸 사람이 관련된 알림 목록: {watches}"""


def _fn(name, description, properties, required=()):
    from google.genai import types
    return types.FunctionDeclaration(
        name=name, description=description,
        parameters_json_schema={"type": "object", "properties": properties, "required": list(required)},
    )


def _command_tools():
    from google.genai import types
    return [types.Tool(function_declarations=[
        _fn("add_watch", "핫딜 알림을 건다. 맞는 딜이 올라오면 대상자를 태그해 알린다.",
            {"want": {"type": "string", "description": "원하는 상품을 짧게 설명 (예: 메가커피, 게이밍 모니터)"},
             "keywords": {"type": "array", "items": {"type": "string"}, "description": "정확한 상품명들. 종류로 말하면 생략"},
             "max_price": {"type": "integer", "description": "이 가격(원) 이하만. 언급 없으면 생략"},
             "for_user": {"type": "string", "description": "알림 받을 사람(이름 또는 <@id>). 본인이면 생략"},
             "once": {"type": "boolean", "description": "한 번만 알리고 끌지. 언급 없으면 생략"}},
            ["want"]),
        _fn("remove_watch", "걸어둔 알림을 끈다.",
            {"watch_ids": {"type": "array", "items": {"type": "integer"}}}, ["watch_ids"]),
        _fn("list_watch", "걸어둔 알림 목록을 보여준다.",
            {"for_user": {"type": "string", "description": "다른 사람 목록을 볼 때만"},
             "everyone": {"type": "boolean", "description": "모든 사람의 알림을 볼 때 true"}}),
        _fn("search_deals", "최근 3일 동안 올라온 핫딜 중에서 특정 상품을 찾아 보여준다.",
            {"query": {"type": "string", "description": "찾을 상품 (예: 메가커피, 게이밍 모니터)"},
             "max_price": {"type": "integer", "description": "이 가격(원) 이하만. 언급 없으면 생략"}},
            ["query"]),
        _fn("show_deals", "지금 핫딜 TOP 목록(랭킹)을 보여준다.",
            {"category": {"type": "string", "enum": ["인기", "게임", "IT", "식품"],
                          "description": "카테고리 언급이 없으면 인기"}},
            ["category"]),
    ])]


class QuotaExceeded(Exception):
    pass


def parse_command(sender: str, text: str, mentions: dict, watches: list) -> dict:
    """Turn a chat message into tool calls. Returns {"calls": [(name, args)], "reply": str | None}."""
    from google.genai import errors, types

    system = _COMMAND_SYSTEM.format(
        people=people.names_for_prompt(),
        mentions=json.dumps(mentions, ensure_ascii=False) or "없음",
        watches=json.dumps([{"watch_id": w["id"], "owner": f"<@{w['owner_id']}>", "want": w["want"]}
                            for w in watches], ensure_ascii=False),
    )
    try:
        resp = _client().models.generate_content(
            model=MODEL, contents=f"보낸 사람: {sender}\n메시지: {text}",
            config=types.GenerateContentConfig(
                system_instruction=system, tools=_command_tools(),
                automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True)),
        )
    except errors.ClientError as e:
        if e.code == 429:
            raise QuotaExceeded() from e
        raise
    calls = [(c.name, dict(c.args or {})) for c in (resp.function_calls or [])]
    return {"calls": calls, "reply": None if calls else (resp.text or "").strip()}
