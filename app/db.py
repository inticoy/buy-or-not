import sqlite3
from contextlib import contextmanager
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "deals.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS daily_posts (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    date          TEXT NOT NULL,
    category_id   INTEGER NOT NULL,
    category_name TEXT NOT NULL,
    thread_id     TEXT NOT NULL,
    posted_at     TEXT NOT NULL,
    UNIQUE(date, category_id)
);
"""


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with get_conn() as conn:
        conn.executescript(SCHEMA)


def get_thread_id(date: str, category_id: int):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT thread_id FROM daily_posts WHERE date = ? AND category_id = ?",
            (date, category_id),
        ).fetchone()
    return row["thread_id"] if row else None


def save_thread_id(date: str, category_id: int, category_name: str,
                   thread_id: str, posted_at: str):
    with get_conn() as conn:
        conn.execute(
            """INSERT OR IGNORE INTO daily_posts
               (date, category_id, category_name, thread_id, posted_at)
               VALUES (?, ?, ?, ?, ?)""",
            (date, category_id, category_name, thread_id, posted_at),
        )
