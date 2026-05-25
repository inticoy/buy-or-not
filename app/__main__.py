import argparse
import logging
import time
from datetime import datetime

from dotenv import load_dotenv
load_dotenv()

from .collector import fetch_rank
from .notifier import post_daily, STYLES

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


def run_once(dry_run: bool = False, style: str = "thumb1"):
    now = datetime.now()

    for cat in CATEGORIES:
        cat_id, cat_name, emoji = cat["id"], cat["name"], cat["emoji"]

        deals = fetch_rank(cat_id)
        if not deals:
            logger.warning("%s — 딜 없음", cat_name)
            continue

        post_daily(now, cat_id, cat_name, emoji, deals, dry_run, style)
        logger.info("%s — 완료", cat_name)
        time.sleep(2)


def main():
    parser = argparse.ArgumentParser(prog="app")
    sub = parser.add_subparsers(dest="cmd")
    p = sub.add_parser("run-once")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--style", choices=STYLES, default="thumb1")
    args = parser.parse_args()

    if args.cmd == "run-once":
        run_once(dry_run=args.dry_run, style=args.style)
    else:
        parser.print_help()


main()
