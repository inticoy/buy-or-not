"""@멘션 말을 Gemini가 바꾼 동작(알림 걸기·끄기·목록·검색)으로 실행한다."""
import logging
from datetime import datetime

from . import board, nl, people
from .matcher import keyword_match
from .notifier import BOARD_COLOR, build_board
from .ranking import groups
from .store import Store

logger = logging.getLogger(__name__)

HELP = ("이렇게 말해주세요 🙂\n"
        "• `메가커피 핫딜 뜨면 알려줘`\n"
        "• `에어팟 프로 25만원 이하로 뜨면 알려줘`\n"
        "• `괜찮은 게이밍 모니터 나오면 @친구 한테 알려줘`\n"
        "• `지금 뭐 알림 받게 되어있어?` / `다들 뭐 걸어놨어?`\n"
        "• `메가커피 알림 꺼줘`\n"
        "• `최근에 받은 알림 보여줘` / `다들 무슨 알림 받았어?`\n"
        "• `메가커피 올라왔어?` (최근 3일 딜 검색)\n"
        "-# 15분마다 확인해서 답이 조금 늦을 수 있어요")
SEARCH_LIMIT = 5


def text(content: str, mention_ids: list | None = None) -> dict:
    return {"content": content, "allowed_mentions": {"users": mention_ids or []}}


def _ago(iso: str) -> str:
    minutes = int((datetime.now().astimezone() - datetime.fromisoformat(iso)).total_seconds() // 60)
    if minutes < 60:
        return f"{max(minutes, 1)}분 전"
    return f"{minutes // 60}시간 전" if minutes < 24 * 60 else f"{minutes // 1440}일 전"


class Handler:
    def __init__(self, store: Store):
        self.store = store
    def add_watch(self, sender: str, args: dict) -> dict:
        owner = people.resolve(args["for_user"]) if args.get("for_user") else sender
        if owner is None:
            return text(f"'{args['for_user']}'님이 누군지 몰라서 못 걸었어요. @멘션으로 다시 말해주세요!")
        want, keywords = args["want"], args.get("keywords") or None
        max_price, once = args.get("max_price"), bool(args.get("once"))
        self.store.add_watch(owner, want, keywords, max_price, once, created_by=sender)
        board.update(self.store)

        target = f"'{'/'.join(keywords)}' 키워드로" if keywords else f"'{want}'에 맞는"
        price = f" {board.won(max_price)} 이하" if max_price else ""
        tail = " 한 번 알려드리면 자동으로 꺼져요." if once else ""
        if owner == sender:
            head = f"<@{owner}>님, 알림 설정 완료!"
        else:
            head = f"<@{owner}>님, <@{sender}>님이 알림을 걸어줬어요!"
        payload = text(f"🔔 {head} {target}{price} 핫딜이 올라오면 바로 알려드릴게요.{tail}", [owner])
        if owner != sender:
            # 스레드 글은 조용히 가므로, 대신 걸린 사람에게는 DM으로 알린다
            payload["_dm"] = (owner, f"🔔 {board.who(sender)}님이 '{want}' 알림을 걸어줬어요! "
                                     f"{target}{price} 핫딜이 올라오면 DM으로 알려드릴게요.{tail}")
        return payload

    def remove_watch(self, sender: str, args: dict) -> dict:
        mine = {w["id"]: w for w in self.store.related_watches(sender)}
        removed = [mine[i] for i in args.get("watch_ids", []) if i in mine]
        for w in removed:
            self.store.deactivate(w["id"])
        if removed:
            board.update(self.store)
        if not removed:
            return text("어떤 알림을 끌지 못 찾았어요. `내 알림 목록`으로 확인해 주세요!")
        return text("🔕 " + ", ".join(f"'{w['want']}'" for w in removed) + " 알림을 껐어요.")

    def list_watch(self, sender: str, args: dict) -> dict:
        # 목록 안의 멘션은 이름처럼 보이기만 하고 알림은 가지 않는다 (allowed_mentions 비움)
        watches = self.store.active_watches()
        if args.get("everyone"):
            if not watches:
                return text("아직 아무도 알림을 걸어두지 않았어요.")
            return text(f"🔔 지금 걸려 있는 알림 {len(watches)}개예요\n\n" + board.grouped(watches))

        who = people.resolve(args["for_user"]) if args.get("for_user") else sender
        if who is None:
            return text(f"'{args['for_user']}'님이 누군지 모르겠어요.")
        mine = [w for w in watches if w["owner_id"] == who]
        if not mine:
            return text(f"{board.who(who)}님은 아직 걸어둔 알림이 없어요.")
        return text(f"🔔 {board.who(who)}님이 받는 알림이에요\n" + "\n".join(board.describe(w) for w in mine))

    def history_watch(self, sender: str, args: dict) -> dict:
        everyone = bool(args.get("everyone"))
        who = None if everyone else (people.resolve(args["for_user"]) if args.get("for_user") else sender)
        if not everyone and who is None:
            return text(f"'{args['for_user']}'님이 누군지 모르겠어요.")
        rows = [r for r in self.store.notified_history(limit=200) if everyone or r["owner_id"] == who][:10]
        whose = "다들" if everyone else f"{board.who(who)}님이"
        if not rows:
            return text(f"최근 7일 동안 {whose} 받은 알림이 없어요.")
        lines = []
        for r in rows:
            title = r["title"][:50].replace("[", "［").replace("]", "］")
            link = f"[{title}](<{r['url']}>)" if r.get("url") else title
            tag = f" · {board.who(r['owner_id'])}" if everyone else ""
            lines.append(f"• {_ago(r['notified_at'])} · '{r['want']}'{tag}\n  {link}")
        return text(f"📬 최근 7일 동안 {whose} 받은 알림 {len(rows)}개예요\n" + "\n".join(lines))

    def search_deals(self, sender: str, args: dict) -> dict:
        query, max_price = args["query"], args.get("max_price")
        recent = self.store.recent_deals(days=3)
        if max_price:
            recent = [d for d in recent if d.get("price") is None or d["price"] <= max_price]
        found = [d for d in recent if keyword_match([query], d["title"])]
        reasons = {}
        if not found and recent:
            # 제목에 그 단어가 없으면 '게이밍 모니터' 같은 종류로 보고 Gemini에 판단을 맡긴다
            picks = nl.judge([{"id": 0, "want": query, "max_price": max_price}], recent[:150])
            by_id = {d["id"]: d for d in recent}
            found = [by_id[str(m["deal_id"])] for m in picks if str(m["deal_id"]) in by_id]
            reasons = {str(m["deal_id"]): m["reason"] for m in picks}

        unique = list({d["group_key"]: d for d in reversed(found)}.values())[::-1][:SEARCH_LIMIT]
        if not unique:
            return text(f"최근 3일 동안 '{query}' 핫딜은 안 보였어요. "
                        f"`{query} 뜨면 알려줘`라고 하면 올라올 때 알려드릴게요!")
        keys = {d["group_key"] for d in unique}
        found_groups = [g for g in groups([d for d in recent if d["group_key"] in keys])]
        found_groups.sort(key=lambda g: g["head"]["first_seen"], reverse=True)
        for g in found_groups:
            g["communities"] = g["communities"] + [_ago(g["head"]["first_seen"])]
        title = f"🔎 '{query}' 최근 핫딜 {len(found_groups)}개"
        subtitle = "최근 3일 동안 올라온 딜이에요" + (" (AI가 고름)" if reasons else "")
        return build_board(title, subtitle, found_groups, BOARD_COLOR["hot"], None, ranked=False)
