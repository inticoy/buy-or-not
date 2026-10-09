"""관심사·딜·알림 기록 (SQLite)."""
import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from .collector import _same_deal

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
        self.db = sqlite3.connect(path)
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

    def deactivate(self, watch_id: int):
        self.db.execute("UPDATE watches SET active = 0 WHERE id = ?", (watch_id,))
        self.db.commit()

    # ── 딜 ──────────────────────────────────────────────
    def is_empty(self) -> bool:
        return self.db.execute("SELECT 1 FROM deals LIMIT 1").fetchone() is None

    def record_deals(self, source: str, deals: list) -> list:
        """Save deals and return the ones not seen before, each with a group_key."""
        since = (datetime.now(KST) - GROUP_WINDOW).isoformat()
        recent = [json.loads(row["data"]) | {"group_key": row["group_key"]} for row in self.db.execute(
            "SELECT data, group_key FROM deals WHERE first_seen >= ?", (since,))]
        known = {row["deal_id"] for row in self.db.execute(
            "SELECT deal_id FROM deals WHERE source = ?", (source,))}

        new = []
        for deal in deals:
            if deal["id"] in known:
                continue
            same = next((seen for seen in recent if _same_deal(deal, seen)), None)
            deal = deal | {"group_key": same["group_key"] if same else f"{source}:{deal['id']}"}
            self.db.execute(
                "INSERT INTO deals (source, deal_id, group_key, title, price, data, first_seen)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                (source, deal["id"], deal["group_key"], deal["title"], deal.get("price"),
                 json.dumps(deal, ensure_ascii=False), _now()),
            )
            recent.append(deal)
            known.add(deal["id"])
            new.append(deal)
        self.db.commit()
        return new

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
