"""@멘션으로 말하면 Gemini가 동작으로 바꿔 실행하는 상주 Discord 봇."""
import asyncio
import logging
import os
import re

import discord

from . import hotdealzip, nl, people
from .collector import fetch_rank
from .notifier import CATEGORY_COLOR, _build_message, _mentions, send_message
from .store import Store

logger = logging.getLogger(__name__)

ALGUMON_CATEGORY = {"게임": 6, "IT": 2, "식품": 3}
HELP = ("이렇게 말해주세요 🙂\n"
        "• `메가커피 핫딜 뜨면 알려줘`\n"
        "• `에어팟 프로 25만원 이하로 뜨면 알려줘`\n"
        "• `괜찮은 게이밍 모니터 나오면 @친구 한테 알려줘`\n"
        "• `내 알림 목록` / `메가커피 알림 꺼줘`\n"
        "• `오늘 게임 핫딜 뭐 있어?`")


def _text(content: str, mention_ids: list | None = None) -> dict:
    return {"content": content, "allowed_mentions": {"users": mention_ids or []}}


def _won(price: int) -> str:
    return f"{price // 10000}만원" if price % 10000 == 0 else f"{price:,}원"


class Handler:
    def __init__(self, store: Store):
        self.store = store

    def add_watch(self, sender: str, args: dict) -> dict:
        owner = people.resolve(args["for_user"]) if args.get("for_user") else sender
        if owner is None:
            return _text(f"'{args['for_user']}'님이 누군지 몰라서 못 걸었어요. @멘션으로 다시 말해주세요!")
        want, keywords = args["want"], args.get("keywords") or None
        max_price, once = args.get("max_price"), bool(args.get("once"))
        self.store.add_watch(owner, want, keywords, max_price, once, created_by=sender)

        target = f"'{'/'.join(keywords)}' 키워드로" if keywords else f"'{want}'에 맞는"
        price = f" {_won(max_price)} 이하" if max_price else ""
        tail = " 한 번 알려드리면 자동으로 꺼져요." if once else ""
        if owner == sender:
            head = f"<@{owner}>님, 알림 설정 완료!"
        else:
            head = f"<@{owner}>님, <@{sender}>님이 알림을 걸어줬어요!"
        return _text(f"🔔 {head} {target}{price} 핫딜이 올라오면 바로 알려드릴게요.{tail}", [owner])

    def remove_watch(self, sender: str, args: dict) -> dict:
        mine = {w["id"]: w for w in self.store.related_watches(sender)}
        removed = [mine[i] for i in args.get("watch_ids", []) if i in mine]
        for w in removed:
            self.store.deactivate(w["id"])
        if not removed:
            return _text("어떤 알림을 끌지 못 찾았어요. `내 알림 목록`으로 확인해 주세요!")
        return _text("🔕 " + ", ".join(f"'{w['want']}'" for w in removed) + " 알림을 껐어요.")

    def list_watch(self, sender: str, args: dict) -> dict:
        who = people.resolve(args["for_user"]) if args.get("for_user") else sender
        if who is None:
            return _text(f"'{args['for_user']}'님이 누군지 모르겠어요.")
        watches = [w for w in self.store.active_watches() if w["owner_id"] == who]
        if not watches:
            return _text(f"<@{who}>님은 아직 걸어둔 알림이 없어요.")
        lines = []
        for i, w in enumerate(watches, 1):
            how = f"키워드 {', '.join(w['keywords'])}" if w["keywords"] else "AI 판단"
            extra = (f" · {_won(w['max_price'])} 이하" if w["max_price"] else "") + (" · 한 번만" if w["once"] else "")
            lines.append(f"{i}. **{w['want']}** ({how}{extra})")
        return _text(f"🔔 <@{who}>님이 받는 알림이에요\n" + "\n".join(lines))

    def show_deals(self, sender: str, args: dict) -> dict:
        category = args.get("category", "인기")
        if category in ALGUMON_CATEGORY:
            deals = fetch_rank(ALGUMON_CATEGORY[category])
            color = CATEGORY_COLOR.get(ALGUMON_CATEGORY[category])
        else:
            deals, color = hotdealzip.top10(), CATEGORY_COLOR["hot"]
        if not deals:
            return _text("지금은 핫딜을 못 가져왔어요. 잠시 후 다시 물어봐 주세요!")
        return _build_message(deals, color, header=f"{category} 핫딜")


def run():
    store = Store()
    handler = Handler(store)
    client = discord.Client(intents=discord.Intents.default())

    @client.event
    async def on_ready():
        logger.info("bot ready as %s", client.user)

    @client.event
    async def on_message(msg: discord.Message):
        # 멘션된 메시지는 Message Content 권한 없이도 내용을 읽을 수 있다
        if msg.author.bot or client.user not in msg.mentions:
            return
        text = re.sub(rf"<@!?{client.user.id}>", "", msg.content).strip()
        sender = str(msg.author.id)
        channel, reply_to = str(msg.channel.id), str(msg.id)
        send = lambda payload: asyncio.to_thread(send_message, channel, payload, reply_to)

        if not text:
            await send(_text(HELP))
            return
        mentions = {f"<@{u.id}>": u.display_name for u in msg.mentions if u != client.user}
        async with msg.channel.typing():
            try:
                result = await asyncio.to_thread(
                    nl.parse_command, msg.author.display_name, text, mentions,
                    store.related_watches(sender))
            except nl.QuotaExceeded:
                await send(_text("오늘 AI 한도를 다 썼어요 😢 내일 다시 말해주세요!"))
                return
            except Exception:
                logger.exception("parse failed: %s", text)
                await send(_text("말을 잘 못 알아들었어요. 다시 한 번 말해주세요!"))
                return

            if not result["calls"]:
                await send(_text(result["reply"] or HELP))
                return
            for name, args in result["calls"]:
                logger.info("%s → %s(%s)", msg.author.display_name, name, args)
                action = getattr(handler, name, None)
                if action is None:
                    continue
                payload = await asyncio.to_thread(action, sender, args)
                await send(payload)

    client.run(os.environ["DISCORD_BOT_TOKEN"], log_handler=None)
