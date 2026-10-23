"""살래말래 한마디: 인기 핫딜 글 아래에, 진짜 살 만한 딜이 있을 때만 친구처럼 부추긴다."""
import json
import logging

from . import monitoring
from .nl import JUDGE_MODEL, MODEL, _client

logger = logging.getLogger(__name__)

# 지난 일주일 인기 TOP에 올랐던 딜들 중 반응 상위 이 비율 안에 들어야 '살 만하다'고 말한다 (평범한 날은 조용히)
TOP_SHARE = 0.15

_PROMPT = """너는 친구들 디스코드 핫딜 스레드의 살래말래야. 방금 올린 인기 핫딜 중 이번 주에 손꼽히게 반응이 좋은 딜들이야.
이 중 진짜 사야 되는 딜 1~2개만 골라 사라고 부추기는 한 줄씩 써. 가격이 왜 좋은지, 누구한테 좋은지 같은 이유를 짧게.
각 줄은 그 딜의 n을 그대로 써서 "3번 "처럼 시작해 (새로 1, 2로 매기지 마). 최대 2줄. 정말 살 만한 게 없으면 빈 배열.
가격은 price에 적힌 그대로만 말하고, 직접 계산하거나 바꿔 읽지 마.

말투 규칙:
- 디시·커뮤니티 친구 말투. 반말 음슴체. 한 줄에 25자 안팎, 짧게.
- ㄷㄷ ㅋㅋ ;; ㄹㅇ 실화냐 미쳤다 갓 무조건 쟁여라 지르셈 같은 표현을 자연스럽게. 매 줄에 다 넣지는 마.
- 가격은 말해도 되지만 추천 수·댓글 수·커뮤니티 이름(루리웹, 펨코 등)은 말하지 마.
- '역대가', '역대 최저', '최저가'처럼 가격 기록이 있어야 하는 말은 쓰지 마. 우리는 가격 기록이 없어.
- "무엇이 왜" 좋은지 꼭 넣어. "개이득", "미쳤다"처럼 내용 없는 감탄만 하면 안 돼.
- 사람·회사를 향한 욕설, 비하는 쓰지 마. '~충' 같은 말도 쓰지 마. 이모지 쓰지 마.

deals: {deals}"""

_SCHEMA = {"type": "object", "properties": {"lines": {"type": "array", "items": {"type": "string"}}},
           "required": ["lines"]}


def heat(g: dict) -> float:
    """묶음의 절대 반응 크기. 순위 점수는 그 회차 안의 상대값이라, 주간 비교에는 댓글·추천 수를 직접 쓴다."""
    return (g["comments"] + (g["recommend"] or 0)) * (1 + 0.3 * (len(g["communities"]) - 1))


def standouts(picks: list, week: list) -> list[int]:
    """picks 중, 지난 일주일 인기 TOP에 올랐던 딜(week)의 반응 상위 TOP_SHARE 안에 드는 것의 순위(1부터)."""
    heats = sorted((heat(g) for g in week), reverse=True)
    if len(heats) < 20:  # 기록이 너무 적으면 판단하지 않는다
        return []
    cut = heats[int(len(heats) * TOP_SHARE)]
    return [rank for rank, g in enumerate(picks, 1) if heat(g) > cut]


def comment(picks: list, ranks: list[int]) -> list[str]:
    if not ranks:
        return []
    deals = [{"n": r, "title": picks[r - 1]["head"]["title"], "price": picks[r - 1]["head"].get("price_str"),
              "shop": picks[r - 1]["head"].get("shop")} for r in ranks]
    prompt = _PROMPT.format(deals=json.dumps(deals, ensure_ascii=False))
    for model in (JUDGE_MODEL, MODEL):
        try:
            resp = _client().models.generate_content(model=model, contents=prompt, config={
                "response_mime_type": "application/json", "response_schema": _SCHEMA})
            return json.loads(resp.text)["lines"][:2]
        except Exception as exc:
            logger.warning("comment with %s failed: %s", model, str(exc)[:200])
    monitoring.error("gemini.comment", RuntimeError("all models failed"), "살래말래 한마디 생성 실패", "Gemini 할당량·키 확인")
    return []
