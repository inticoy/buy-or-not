import argparse
import logging
import time
from datetime import datetime, timezone

from .collector import fetch_rank
from .db import get_thread_id, init_db, save_thread_id
from .notifier import post_daily

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)

CATEGORIES = [
    {"id": 6, "name": "게임", "emoji": "🎮"},
    {"id": 2, "name": "IT",   "emoji": "💻"},
    {"id": 3, "name": "식품", "emoji": "🍜"},
]


def run_once(dry_run: bool = False):
    init_db()
    now = datetime.now()
    today = now.strftime("%Y-%m-%d")
    now_iso = datetime.now(timezone.utc).isoformat()

    for cat in CATEGORIES:
        cat_id, cat_name, emoji = cat["id"], cat["name"], cat["emoji"]

        # 오늘 이미 올렸으면 스킵
        if get_thread_id(today, cat_id):
            logger.info("%s — 오늘 이미 포스팅됨", cat_name)
            continue

        deals = fetch_rank(cat_id)
        if not deals:
            logger.warning("%s — 딜 없음", cat_name)
            continue

        thread_id = post_daily(now, cat_id, cat_name, emoji, deals, dry_run)

        if not dry_run:
            save_thread_id(today, cat_id, cat_name, thread_id, now_iso)

        logger.info("%s — 완료", cat_name)
        time.sleep(2)


def main():
    parser = argparse.ArgumentParser(prog="app")
    sub = parser.add_subparsers(dest="cmd")
    p = sub.add_parser("run-once")
    p.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if args.cmd == "run-once":
        run_once(dry_run=args.dry_run)
    else:
        parser.print_help()


main()
