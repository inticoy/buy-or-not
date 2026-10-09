import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
load_dotenv()

import requests

from . import hotdealzip
from .browser import BrowserFetchError, fetch_html
from .collector import _deduplicate_deals, fetch_rank
from .notifier import post_daily

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)

def _hotdeal_top10() -> list:
    try:
        deals = hotdealzip.fetch_popular()
    except BrowserFetchError as e:
        logger.error("hotdeal.zip fetch failed: %s", e)
        return []
    return _deduplicate_deals(deals)[:10]


# 게시판마다 한 메시지. id는 메시지 컬러 키로 쓴다.
BOARDS = {
    "hotdeal": [
        {"id": "hot", "name": "인기", "emoji": "🔥", "fetch": _hotdeal_top10},
    ],
    "algumon": [
        {"id": 6, "name": "게임", "emoji": "🎮", "fetch": lambda: fetch_rank(6)},
        {"id": 2, "name": "IT",   "emoji": "💻", "fetch": lambda: fetch_rank(2)},
        {"id": 3, "name": "식품", "emoji": "🍜", "fetch": lambda: fetch_rank(3)},
    ],
}
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


def _post_boards(boards: list, now, dry_run: bool) -> list:
    """Post each board and return the ones that failed to fetch."""
    failed = []
    for board in boards:
        deals = board["fetch"]()
        if not deals:
            logger.error("%s — 딜 없음", board["name"])
            failed.append(board)
            continue

        post_daily(now, board["id"], board["name"], board["emoji"], deals, dry_run)
        logger.info("%s — 완료", board["name"])
        time.sleep(2)
    return failed


def run_once(source: str = "hotdeal", dry_run: bool = False) -> bool:
    now = datetime.now(ZoneInfo("Asia/Seoul"))
    failed = _post_boards(BOARDS[source], now, dry_run)

    # 챌린지는 요청이 몰렸을 때 잠시 걸렸다 풀리므로, 실패한 게시판만 한 번 더 시도한다.
    # 그사이 Chrome에 열어둔 챌린지 탭을 직접 통과시켜도 재시도가 성공한다.
    if failed and not dry_run:
        logger.warning("%d개 게시판 실패 — %d분 뒤 재시도", len(failed), RETRY_DELAY_S // 60)
        time.sleep(RETRY_DELAY_S)
        failed = _post_boards(failed, now, dry_run)

    return not failed


def snapshot(out_dir: str = "data/snapshots"):
    """hotdeal.zip 인기·최신 HTML을 저장한다 (v3 소스 특성 조사용)."""
    stamp = datetime.now(ZoneInfo("Asia/Seoul")).strftime("%Y%m%d-%H%M")
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / f"{stamp}-popular.html").write_text(fetch_html(hotdealzip.POPULAR_URL), encoding="utf-8")
    time.sleep(3)
    latest = hotdealzip.fetch_latest(pages=3)
    # 파싱 결과만 남겨도 충분해 최신 목록은 JSON으로 저장한다
    (out / f"{stamp}-latest.json").write_text(json.dumps(latest, ensure_ascii=False, indent=1), encoding="utf-8")
    logger.info("snapshot saved: %s (latest %d deals)", stamp, len(latest))


def main():
    parser = argparse.ArgumentParser(prog="app")
    sub = parser.add_subparsers(dest="cmd")
    p = sub.add_parser("run-once")
    p.add_argument("--source", choices=BOARDS, default="hotdeal")
    p.add_argument("--dry-run", action="store_true")
    sub.add_parser("snapshot")
    args = parser.parse_args()

    if args.cmd == "snapshot":
        snapshot()
    elif args.cmd == "run-once":
        ok = run_once(source=args.source, dry_run=args.dry_run)
        if not args.dry_run:
            _ping_healthcheck(failed=not ok)
        if not ok:
            sys.exit(1)
    else:
        parser.print_help()


main()
