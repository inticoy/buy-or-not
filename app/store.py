"""관심사·딜·알림 기록 (SQLite)."""
import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from .dedupe import same_deal

DB_PATH = Path("data/sallae.db")
KST = ZoneInfo("Asia/Seoul")
# 이 기간 안에 본 딜과 제목·가격이 같으면 같은 딜(크로스포스트)로 묶는다
GROUP_WINDOW = timedelta(days=3)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS watches (
  id          INTEGER PRIMARY KEY,
  owner_id    TEXT NOT NULL,
  created_by  TEXT NOT NULL,
  want        TEXT NOT NULL,
  keywords    TEXT,
  max_price   INTEGER,
  once        INTEGER NOT NULL DEFAULT 0,
  active      INTEGER NOT NULL DEFAULT 1,
  created_at  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS deals (
  source      TEXT NOT NULL,
  deal_id     TEXT NOT NULL,
  group_key   TEXT NOT NULL,
  title       TEXT NOT NULL,
  price       INTEGER,
  data        TEXT NOT NULL,
  first_seen  TEXT NOT NULL,
  PRIMARY KEY (source, deal_id)
);
CREATE TABLE IF NOT EXISTS posted (
  board       TEXT NOT NULL,
  group_key   TEXT NOT NULL,
  posted_at   TEXT NOT NULL,
  PRIMARY KEY (board, group_key)
);
CREATE TABLE IF NOT EXISTS meta (
  key         TEXT PRIMARY KEY,
  value       TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS notified (
  watch_id    INTEGER NOT NULL,
  group_key   TEXT NOT NULL,
  price       INTEGER,
  notified_at TEXT NOT NULL,
  PRIMARY KEY (watch_id, group_key)
);
"""


def _now() -> str:
    return datetime.now(KST).isoformat(timespec="seconds")


class Store:
    def __init__(self, path: Path | str = DB_PATH):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, timeout=10, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(_SCHEMA)

    # ── 관심사 ──────────────────────────────────────────
    def add_watch(self, owner_id: str, want: str, keywords: list | None = None,
                  max_price: int | None = None, once: bool = False,
                  created_by: str | None = None) -> int:
        cur = self.db.execute(
            "INSERT INTO watches (owner_id, created_by, want, keywords, max_price, once, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (owner_id, created_by or owner_id, want,
             json.dumps(keywords, ensure_ascii=False) if keywords else None,
             max_price, int(once), _now()),
        )
        self.db.commit()
        return cur.lastrowid

    def active_watches(self) -> list[dict]:
        rows = self.db.execute("SELECT * FROM watches WHERE active = 1 ORDER BY id").fetchall()
        return [{**dict(row), "keywords": json.loads(row["keywords"]) if row["keywords"] else None}
                for row in rows]

    def related_watches(self, user_id: str) -> list[dict]:
        """그 사람이 받는 알림과 그 사람이 남에게 걸어준 알림."""
        return [w for w in self.active_watches() if user_id in (w["owner_id"], w["created_by"])]

    def deactivate(self, watch_id: int):
        self.db.execute("UPDATE watches SET active = 0 WHERE id = ?", (watch_id,))
        self.db.commit()

    # ── 딜 ──────────────────────────────────────────────
    def is_empty(self) -> bool:
        return self.db.execute("SELECT 1 FROM deals LIMIT 1").fetchone() is None

    def record_deals(self, source: str, deals: list) -> list:
        """Save deals and return the ones not seen before, each with a group_key.

        이미 본 딜은 댓글·추천 수와 종료 여부만 새로 고친다 (순위를 매길 때 최신 반응을 쓰려고).
        """
        since = (datetime.now(KST) - GROUP_WINDOW).isoformat()
        recent = [json.loads(row["data"]) | {"group_key": row["group_key"]} for row in self.db.execute(
            "SELECT data, group_key FROM deals WHERE first_seen >= ?", (since,))]
        known = {row["deal_id"]: row["group_key"] for row in self.db.execute(
            "SELECT deal_id, group_key FROM deals WHERE source = ?", (source,))}

        new = []
        for deal in deals:
            if deal["id"] in known:
                self.db.execute("UPDATE deals SET data = ?, price = ? WHERE source = ? AND deal_id = ?",
                                (json.dumps(deal | {"group_key": known[deal["id"]]}, ensure_ascii=False),
                                 deal.get("price"), source, deal["id"]))
                continue
            same = next((seen for seen in recent if same_deal(deal, seen)), None)
            deal = deal | {"group_key": same["group_key"] if same else f"{source}:{deal['id']}"}
            self.db.execute(
                "INSERT INTO deals (source, deal_id, group_key, title, price, data, first_seen)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                (source, deal["id"], deal["group_key"], deal["title"], deal.get("price"),
                 json.dumps(deal, ensure_ascii=False), _now()),
            )
            recent.append(deal)
            known[deal["id"]] = deal["group_key"]
            new.append(deal)
        self.db.commit()
        return new

    def recent_deals(self, days: float = 3, hours: float | None = None) -> list:
        """최근 며칠(또는 몇 시간) 동안 본 딜, 최신순. 각 딜에 first_seen이 붙는다."""
        since = (datetime.now(KST) - (timedelta(hours=hours) if hours else timedelta(days=days))).isoformat()
        rows = self.db.execute(
            "SELECT data, group_key, first_seen FROM deals WHERE first_seen >= ? AND source != 'seed'"
            " ORDER BY first_seen DESC, rowid DESC", (since,))
        return [json.loads(r["data"]) | {"group_key": r["group_key"], "first_seen": r["first_seen"]}
                for r in rows]

    # ── 알림 기록 ───────────────────────────────────────
    def notify_kind(self, watch_id: int, group_key: str, price: int | None) -> str | None:
        """'new'(처음 보는 딜), 'drop'(전에 알린 가격보다 내려감), None(알리지 않음)."""
        row = self.db.execute(
            "SELECT price FROM notified WHERE watch_id = ? AND group_key = ?",
            (watch_id, group_key)).fetchone()
        if row is None:
            return "new"
        if price is not None and row["price"] is not None and price < row["price"]:
            return "drop"
        return None

    def mark_notified(self, watch_id: int, group_key: str, price: int | None):
        self.db.execute(
            "INSERT INTO notified (watch_id, group_key, price, notified_at) VALUES (?, ?, ?, ?)"
            " ON CONFLICT (watch_id, group_key) DO UPDATE SET price = excluded.price,"
            " notified_at = excluded.notified_at",
            (watch_id, group_key, price, _now()),
        )
        self.db.commit()

    # ── 매일 글 ─────────────────────────────────────────
    def posted_keys(self, board: str, days: int = 2) -> set:
        """그 게시판에 최근 올린 딜 묶음 (다음 글에서 다시 올리지 않으려고)."""
        since = (datetime.now(KST) - timedelta(days=days)).isoformat()
        return {r["group_key"] for r in self.db.execute(
            "SELECT group_key FROM posted WHERE board = ? AND posted_at >= ?", (board, since))}

    def mark_posted(self, board: str, group_keys: list):
        self.db.executemany(
            "INSERT OR REPLACE INTO posted (board, group_key, posted_at) VALUES (?, ?, ?)",
            [(board, key, _now()) for key in group_keys])
        self.db.commit()

    # ── 상태 값 (마지막으로 읽은 메시지, 올린 시간대 등) ──────
    def get_meta(self, key: str) -> str | None:
        row = self.db.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else None

    def set_meta(self, key: str, value: str):
        self.db.execute("INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)", (key, value))
        self.db.commit()
