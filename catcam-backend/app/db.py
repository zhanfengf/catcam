import sqlite3
import threading
from datetime import datetime


_lock = threading.Lock()
_conn: sqlite3.Connection | None = None


def init_db(db_path: str) -> None:
    global _conn
    _conn = sqlite3.connect(db_path, check_same_thread=False)
    _conn.execute("PRAGMA journal_mode=WAL;")
    _conn.execute(
        "CREATE TABLE IF NOT EXISTS state (key TEXT PRIMARY KEY, value TEXT)"
    )
    _conn.execute(
        """CREATE TABLE IF NOT EXISTS feed_log (
               id INTEGER PRIMARY KEY AUTOINCREMENT,
               fed_at TEXT NOT NULL,
               ip TEXT,
               amount INTEGER
           )"""
    )
    _conn.commit()


def _db() -> sqlite3.Connection:
    if _conn is None:
        raise RuntimeError("DB not initialised — call init_db() first")
    return _conn


def get_last_fed_at() -> datetime | None:
    with _lock:
        row = _db().execute(
            "SELECT value FROM state WHERE key = 'last_fed_at'"
        ).fetchone()
    if not row or not row[0]:
        return None
    return datetime.fromisoformat(row[0])


def record_feed(fed_at: datetime, ip: str | None, amount: int) -> None:
    with _lock:
        conn = _db()
        conn.execute(
            "INSERT INTO state (key, value) VALUES ('last_fed_at', ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (fed_at.isoformat(),),
        )
        conn.execute(
            "INSERT INTO feed_log (fed_at, ip, amount) VALUES (?, ?, ?)",
            (fed_at.isoformat(), ip, amount),
        )
        conn.commit()


def count_feeds_today(day_start: datetime) -> int:
    with _lock:
        row = _db().execute(
            "SELECT COUNT(*) FROM feed_log WHERE fed_at >= ?",
            (day_start.isoformat(),),
        ).fetchone()
    return row[0] if row else 0
