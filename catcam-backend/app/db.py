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
    _conn.execute(
        """CREATE TABLE IF NOT EXISTS announcement_log (
               id INTEGER PRIMARY KEY AUTOINCREMENT,
               text TEXT NOT NULL,
               created_at TEXT NOT NULL
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


def record_feed(fed_at: datetime, ip: str | None, amount: int, source: str = "public") -> None:
    with _lock:
        conn = _db()
        if source == "public":
            # admin (secret-channel) feeds must not push out the public
            # cooldown — only public /feed calls move this timestamp
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


def get_announcement() -> str:
    with _lock:
        row = _db().execute(
            "SELECT value FROM state WHERE key = 'announcement'"
        ).fetchone()
    return row[0] if row and row[0] else ""


def set_announcement(text: str, created_at: datetime) -> None:
    with _lock:
        conn = _db()
        conn.execute(
            "INSERT INTO state (key, value) VALUES ('announcement', ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (text,),
        )
        # append-only — every save lands a new row here, even if the text is
        # unchanged, so "幾時改過公告" has a real answer instead of only
        # knowing what's currently live in `state`
        conn.execute(
            "INSERT INTO announcement_log (text, created_at) VALUES (?, ?)",
            (text, created_at.isoformat()),
        )
        conn.commit()


def get_announcement_log(limit: int = 20) -> list[dict]:
    with _lock:
        rows = _db().execute(
            "SELECT text, created_at FROM announcement_log ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [{"text": r[0], "created_at": r[1]} for r in rows]


def count_feeds_today(day_start: datetime) -> int:
    # public (visitor) feeds only — admin/secret-channel feeds (including
    # the admin_test simulated-visitor button) are excluded, matching the
    # "訪客餵食咗" label this backs
    with _lock:
        row = _db().execute(
            "SELECT COUNT(*) FROM feed_log WHERE fed_at >= ? "
            "AND (ip IS NULL OR (ip NOT LIKE 'admin:%' AND ip NOT LIKE 'admin_test:%'))",
            (day_start.isoformat(),),
        ).fetchone()
    return row[0] if row else 0
