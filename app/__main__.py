"""살래말래: GitHub Actions에서 15분마다 `cycle`을 실행한다 (cron-job.org가 workflow를 부름).

한 번 실행할 때: 딜 모으기 → 관심사 알림 → @멘션 답하기 → 정해진 시간이면 인기·카테고리 글.
"""
import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime, timedelta

from dotenv import load_dotenv
load_dotenv()

from . import board, matcher, mentions, ranking, sources
from .notifier import BOARD_COLOR, board_header, build_board, post_alert, post_board
from .store import KST, Store
from . import monitoring

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# 게시판: 순위를 매길 범위(시간), 올리는 시각(KST), 맨 아래 더 보기 링크
BOARDS = {
    "hot": {"name": "인기", "emoji": "🔥", "category": None, "hours": 16, "slots": (12, 21),
            "more": ("hotdeal.zip 인기 더 보기", "https://hotdeal.zip/%EC%9D%B8%EA%B8%B0")},
    "game": {"name": "게임", "emoji": "🎮", "category": "game", "hours": 24, "slots": (12,),
             "more": ("알구몬 게임 랭킹 더 보기", "https://www.algumon.com/n/deal/rank?categoryId=6")},
    "digital": {"name": "IT", "emoji": "💻", "category": "digital", "hours": 24, "slots": (12,),
                "more": ("알구몬 IT 랭킹 더 보기", "https://www.algumon.com/n/deal/rank?categoryId=2")},
    "food": {"name": "식품", "emoji": "🍜", "category": "food", "hours": 24, "slots": (12,),
             "more": ("알구몬 식품 랭킹 더 보기", "https://www.algumon.com/n/deal/rank?categoryId=3")},
}
TOP_N = 5
LATE_LIMIT = timedelta(hours=3)  # Actions가 늦게 돌아도 이 안이면 그 시간대 글을 올린다
COLLECT_HOURS = 24  # 반응 수를 새로 고치려고 매번 하루치를 다시 읽는다


def collect_and_alert(store: Store, dry_run: bool) -> bool:
    """딜을 모으고 새 딜로 알림. 처음 실행(DB가 비었음)이면 True."""
    first_run = store.is_empty()
    deals, failed = sources.collect(datetime.now(KST) - timedelta(hours=COLLECT_HOURS))
    if len(failed) == len(sources.SOURCES):
        monitoring.observe("collect", "failure", "all-sources-failed", "모든 딜 수집원 조회 실패", "출처 접근 제한·실행 로그 확인")
    new = []
    for source in sources.SOURCES:
        new += store.record_deals(source, [d for d in deals if d["source"] == source])
    logger.info("collect: %d deals, %d new, failed=%s", len(deals), len(new), failed)
    if first_run:  # 지난 딜이 한꺼번에 알림으로 가지 않도록 처음엔 기록만
        logger.info("first run — recorded only")
        return True
    alert(store, [d for d in new if not d.get("ended")], dry_run)
    return False


def alert(store: Store, new: list, dry_run: bool) -> None:
    # 같은 딜에 걸린 관심사(여러 사람 포함)는 메시지 하나로 모은다
    hits_by_deal = {}
    for watch, deal, reason in matcher.match(store.active_watches(), new):
        kind = store.notify_kind(watch["id"], deal["group_key"], deal.get("price"))
        if kind is None:
            continue
        _, hits = hits_by_deal.setdefault(deal["group_key"], (deal, []))
        if all(h["watch"]["id"] != watch["id"] for h in hits):  # 한 번에 들어온 크로스포스트
            hits.append({"watch": watch, "owner_id": watch["owner_id"], "want": watch["want"],
                         "reason": reason, "price_drop": kind == "drop"})

    for deal, hits in hits_by_deal.values():
        post_alert(hits, deal, dry_run)
        if dry_run:
            continue
        for hit in hits:
            store.mark_notified(hit["watch"]["id"], deal["group_key"], deal.get("price"))
            if hit["watch"]["once"]:
                store.deactivate(hit["watch"]["id"])
                board.update(store)


def post(store: Store, board_id: str, dry_run: bool) -> bool:
    cfg = BOARDS[board_id]
    now = datetime.now(KST)
    exclude = store.posted_keys(board_id)
    if cfg["category"]:  # 오늘 인기에 이미 나온 딜은 카테고리 글에서 뺀다
        exclude |= store.posted_keys("hot", days=1)
    picks = ranking.top(store.recent_deals(hours=cfg["hours"]), TOP_N, cfg["category"], exclude=exclude)
    if not picks:
        logger.warning("%s — 올릴 딜 없음", cfg["name"])
        return False
    when = "저녁" if now.hour >= 18 else "점심" if now.hour >= 11 else "오늘"
    message = build_board(board_header(now, cfg["name"], cfg["emoji"]), f"{when} TOP {len(picks)}", picks,
                          BOARD_COLOR[board_id], cfg["more"])
    post_board(message, dry_run)
    if not dry_run:
        store.mark_posted(board_id, [key for g in picks for key in [g["key"]] + [e["key"] for e in g.get("same_event", [])]])
    logger.info("%s — %s", cfg["name"], [g["head"]["title"][:30] for g in picks])
    return True


def due_boards(store: Store, now: datetime) -> list[tuple[str, str]]:
    """지금 올려야 하는 (게시판, 시간대 키). 시간대마다 한 번만."""
    due = []
    for board_id, cfg in BOARDS.items():
        for hour in cfg["slots"]:
            slot = now.replace(hour=hour, minute=0, second=0, microsecond=0)
            key = f"posted:{board_id}:{slot:%Y-%m-%d-%H}"
            if slot <= now < slot + LATE_LIMIT and store.get_meta(key) is None:
                due.append((board_id, key))
    return due


def cycle(dry_run: bool = False) -> bool:
    monitoring.begin()
    if not dry_run:
        for component, present, description in [
            ("gemini.config", bool(os.environ.get("GEMINI_API_KEY")), "Gemini 키"),
            ("discord.config", bool(os.environ.get("DISCORD_BOT_TOKEN") and (os.environ.get("DISCORD_THREAD_PROD") or os.environ.get("DISCORD_CHANNEL_PROD"))), "Discord 봇 토큰·게시 목적지"),
        ]:
            monitoring.observe(component, "ok" if present else "degraded", "ok" if present else "missing-config", "정상 확인" if present else description + " 설정 누락", "ENV_FILE 확인")
    store = Store()
    seed_if_empty(store)
    ok, first_run = True, False
    try:
        first_run = collect_and_alert(store, dry_run)
        monitoring.observe("collect")
    except Exception as exc:
        monitoring.error("collect", exc, "딜 수집 또는 관심사 알림 실패", severity="failure")
        logger.exception("collect failed")
        ok = False
    try:
        logger.info("mentions answered: %d", mentions.process(store, dry_run))
        monitoring.observe("mentions")
    except Exception as exc:
        monitoring.error("mentions", exc, "Discord 멘션 처리 실패")
        logger.exception("mentions failed")
        ok = False
    for board_id, key in due_boards(store, datetime.now(KST)):
        if first_run:  # 옮겨 온 첫 실행은 그 시간대 글을 이미 올린 것으로 친다 (중복 방지)
            store.set_meta(key, "skipped: first run")
            continue
        try:
            if post(store, board_id, dry_run) and not dry_run:
                store.set_meta(key, datetime.now(KST).isoformat(timespec="seconds"))
                monitoring.observe("board." + board_id)
        except Exception as exc:  # 한 게시판이 실패해도 나머지는 올리고, 다음 실행에서 다시 시도한다
            monitoring.error("board." + board_id, exc, "게시판 글 전송 실패")
            logger.exception("post %s failed", board_id)
            ok = False
        time.sleep(2)
    if not dry_run and os.environ.get("MONITOR_ENDPOINT") and not monitoring.finish("buy-or-not"):
        ok = False
    return ok


# ── 처음 Actions로 옮길 때: 맥에서 쓰던 알림 목록을 비밀값(SEED_JSON)으로 넘긴다 ──
def export_seed(store: Store) -> str:
    watches = [dict(r) for r in store.db.execute("SELECT * FROM watches")]
    board_state = json.loads(board.STATE_FILE.read_text()) if board.STATE_FILE.exists() else {}
    return json.dumps({"watches": watches, "board": board_state}, ensure_ascii=False, separators=(",", ":"))


def seed_if_empty(store: Store) -> None:
    raw = os.environ.get("SEED_JSON")
    if not raw or store.db.execute("SELECT 1 FROM watches LIMIT 1").fetchone():
        return
    seed = json.loads(raw)
    for w in seed.get("watches", []):
        store.db.execute(f"INSERT INTO watches ({', '.join(w)}) VALUES ({', '.join('?' * len(w))})", list(w.values()))
    store.db.commit()
    if seed.get("board") and not board.STATE_FILE.exists():
        board.STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        board.STATE_FILE.write_text(json.dumps(seed["board"]))
    logger.info("seeded %d watches", len(seed.get("watches", [])))


def main():
    parser = argparse.ArgumentParser(prog="app")
    sub = parser.add_subparsers(dest="cmd")
    p = sub.add_parser("cycle", help="모으기·알림·멘션·정해진 시간 글 (15분마다)")
    p.add_argument("--dry-run", action="store_true")
    p = sub.add_parser("post", help="지금 바로 게시판 글 올리기 (시험용)")
    p.add_argument("boards", nargs="*", help=f"{', '.join(BOARDS)} 중 (없으면 전부)")
    p.add_argument("--dry-run", action="store_true")
    p = sub.add_parser("watch-add", help="관심사 직접 등록")
    p.add_argument("--owner", required=True, help="알림 받을 사람 Discord ID")
    p.add_argument("--want", required=True, help="관심사 설명")
    p.add_argument("--keywords", nargs="+", help="정확한 상품명. 없으면 Gemini가 판단")
    p.add_argument("--max-price", type=int)
    p.add_argument("--once", action="store_true")
    p.add_argument("--by", help="등록한 사람 Discord ID (대신 등록할 때)")
    sub.add_parser("watch-list")
    sub.add_parser("board", help="고정된 '알림 키워드' 메시지 갱신")
    sub.add_parser("export-seed", help="알림 목록을 SEED_JSON 비밀값용 한 줄 JSON으로")
    args = parser.parse_args()

    if args.cmd == "cycle":
        if not cycle(dry_run=args.dry_run):
            sys.exit(1)
    elif args.cmd == "post":
        store = Store()
        for board_id in args.boards or BOARDS:
            post(store, board_id, args.dry_run)
            time.sleep(2)
    elif args.cmd == "board":
        board.update()
    elif args.cmd == "export-seed":
        print(export_seed(Store()))
    elif args.cmd == "watch-add":
        watch_id = Store().add_watch(args.owner, args.want, args.keywords, args.max_price,
                                     args.once, args.by)
        print(f"watch #{watch_id} added")
    elif args.cmd == "watch-list":
        for w in Store().active_watches():
            print(f"#{w['id']} <@{w['owner_id']}> {w['want']} keywords={w['keywords']}"
                  f" max_price={w['max_price']} once={bool(w['once'])}")
    else:
        parser.print_help()


main()
