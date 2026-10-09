import argparse
import logging
import os
import sys
import time
from datetime import datetime
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
load_dotenv()

import requests

from .collector import fetch_rank
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
RETRY_DELAY_S = 60 * 60


def _ping_healthcheck(failed: bool):
    """Best-effort Healthchecks.io signal; a monitoring outage must not fail the run."""
    url = os.environ.get("HEALTHCHECK_BUY_OR_NOT_URL", "")
    if not url:
        return
    try:
        requests.get(f"{url.rstrip('/')}/fail" if failed else url, timeout=10)
    except requests.RequestException as e:
        logger.error("healthcheck ping failed: %s", e)


def _post_categories(categories: list, now, dry_run: bool) -> list:
    """Post each category and return the ones that failed to fetch."""
    failed = []
    for cat in categories:
        cat_id, cat_name, emoji = cat["id"], cat["name"], cat["emoji"]

        deals = fetch_rank(cat_id)
        if not deals:
            logger.error("%s — 딜 없음", cat_name)
            failed.append(cat)
            continue

        post_daily(now, cat_id, cat_name, emoji, deals, dry_run)
        logger.info("%s — 완료", cat_name)
        time.sleep(2)
    return failed


def run_once(dry_run: bool = False) -> bool:
    now = datetime.now(ZoneInfo("Asia/Seoul"))
    failed = _post_categories(CATEGORIES, now, dry_run)

    # 챌린지는 요청이 몰렸을 때 잠시 걸렸다 풀리므로, 실패한 카테고리만 한 번 더 시도한다.
    # 그사이 Chrome에 열어둔 챌린지 탭을 직접 통과시켜도 재시도가 성공한다.
    if failed and not dry_run:
        logger.warning("%d개 카테고리 실패 — %d분 뒤 재시도", len(failed), RETRY_DELAY_S // 60)
        time.sleep(RETRY_DELAY_S)
        failed = _post_categories(failed, now, dry_run)

    return not failed


def main():
    parser = argparse.ArgumentParser(prog="app")
    sub = parser.add_subparsers(dest="cmd")
    p = sub.add_parser("run-once")
    p.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if args.cmd == "run-once":
        ok = run_once(dry_run=args.dry_run)
        if not args.dry_run:
            _ping_healthcheck(failed=not ok)
        if not ok:
            sys.exit(1)
    else:
        parser.print_help()


main()
