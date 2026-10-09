"""Gemini가 친구들 말투의 한국어를 봇 동작(도구 호출)으로 잘 바꾸는지 시험한다.

사용: python scripts/nl_intent_check.py            → 사용 가능한 모델 목록만 출력 (요청 한도 소모 없음)
      python scripts/nl_intent_check.py <model>    → 테스트 문장 10개를 그 모델로 실행 (요청 10회)

필요: pip install google-genai, .env의 GEMINI_API_KEY
"""
import json
import os
import sys
import time

from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()
client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

SYSTEM = (
    "너는 친구들 디스코드 방의 봇이야. 핫딜 알림(살래말래)과 배그 전적 분석(범인찾기)을 한다. "
    "사용자의 말을 보고 맞는 도구를 호출해. 맞는 도구가 없으면 도구를 부르지 말고 짧게 한국어로 답해. "
    "'나', '내'는 메시지를 보낸 사람을 뜻한다. 가격은 원 단위 정수로 바꿔. "
    "다른 사람에게 알려달라고 하면 for_user에 그 사람을 넣고, Discord 멘션(<@숫자>)은 그대로 넣어. "
    "등록된 친구: 윤건우(건우), 박진호(진호), 김철수(철수), 이영희(영희)."
)


def fn(name, description, properties, required=()):
    return types.FunctionDeclaration(
        name=name,
        description=description,
        parameters_json_schema={"type": "object", "properties": properties, "required": list(required)},
    )


TOOLS = [types.Tool(function_declarations=[
    fn("add_watch", "관심사를 등록한다. 맞는 딜이 올라오면 대상자를 태그해 알린다.",
       {"want": {"type": "string", "description": "원하는 것을 설명한 문장"},
        "keywords": {"type": "array", "items": {"type": "string"}, "description": "정확한 상품명이 있으면 그 이름들"},
        "max_price": {"type": "integer", "description": "이 가격(원) 이하일 때만 알림. 언급 없으면 생략"},
        "for_user": {"type": "string", "description": "알림 받을 사람(친구 이름 또는 <@id>). 보낸 사람 본인이면 생략"},
        "once": {"type": "boolean", "description": "한 번만 알리고 해제할지. 언급 없으면 생략"}},
       ["want"]),
    fn("remove_watch", "등록한 관심 상품 키워드를 삭제한다.",
       {"keyword": {"type": "string"}}, ["keyword"]),
    fn("list_watch", "보낸 사람이 등록한 관심 상품 목록을 보여준다.", {}),
    fn("show_deals", "오늘의 핫딜 TOP 목록을 보여준다.",
       {"category": {"type": "string", "enum": ["전체", "게임", "IT", "식품"]}}, ["category"]),
    fn("pubg_stats", "등록된 친구의 최근 배그 전적 분석 카드를 보여준다.",
       {"player": {"type": "string", "description": "친구 이름 또는 배그 닉네임"},
        "matches": {"type": "integer", "description": "분석할 판 수. 언급 없으면 생략"}},
       ["player"]),
])]

CASES = [
    ("윤건우", "에어팟 프로 25만원 아래로 뜨면 알려줘"),
    ("윤건우", "나 뭐 등록해놨더라"),
    ("윤건우", "에어팟 알림 이제 꺼줘"),
    ("김철수", "오늘 IT 핫딜 뭐있어?"),
    ("김철수", "건우 최근 50판 전적 좀"),
    ("김철수", "ㅋㅋ 오늘 배그 ㄱ?"),
    ("이영희", "닌텐도 스위치2나 프로콘 싸게 나오면 알려줘 10만 이하로"),
    ("박진호", "게이밍 모니터 핫딜 뜨면 알림줘"),
    ("윤건우", "게이밍 모니터 핫딜 뜨면 진호한테 알림줘"),
    ("윤건우", "<@412345678901234567> 한테 OLED 모니터 30만 이하로 뜨면 한번만 알려줘"),
]

if len(sys.argv) < 2:
    for m in client.models.list():
        if "generateContent" in (m.supported_actions or []) and "gemini" in m.name:
            print(m.name)
    sys.exit()

model = sys.argv[1]
config = types.GenerateContentConfig(
    system_instruction=SYSTEM,
    tools=TOOLS,
    automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
)
for sender, text in CASES:
    started = time.monotonic()
    try:
        resp = client.models.generate_content(
            model=model, contents=f"보낸 사람: {sender}\n메시지: {text}", config=config,
        )
    except Exception as e:  # 한도 초과 등은 그대로 보여준다
        print(f"[{sender}] {text}\n   → ERROR {e}\n")
        continue
    elapsed = time.monotonic() - started
    calls = [f"{c.name}({json.dumps(c.args, ensure_ascii=False)})" for c in (resp.function_calls or [])]
    result = " + ".join(calls) if calls else f"답장: {resp.text!r}"
    print(f"[{sender}] {text}\n   → {result}  ({elapsed:.1f}s)\n")
