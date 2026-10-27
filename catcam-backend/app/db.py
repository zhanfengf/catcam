import json
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
    # backs the public two-phase activity feed: one row per real dispense
    # (any trigger — site/app/physical/auto), written the moment the feed is
    # detected (clip still NULL), then updated once its clip finishes
    # rendering ~1 min later. keyed by fed_at because that's the recorder's
    # own detection timestamp, shared between insert and later update.
    _conn.execute(
        """CREATE TABLE IF NOT EXISTS feed_event (
               id INTEGER PRIMARY KEY AUTOINCREMENT,
               fed_at TEXT NOT NULL,
               clip TEXT,
               clip_ready_at TEXT,
               source TEXT,
               note TEXT
           )"""
    )
    # migrate feed_event tables created before source/note existed
    cols = {r[1] for r in _conn.execute("PRAGMA table_info(feed_event)").fetchall()}
    if "source" not in cols:
        _conn.execute("ALTER TABLE feed_event ADD COLUMN source TEXT")
    if "note" not in cols:
        _conn.execute("ALTER TABLE feed_event ADD COLUMN note TEXT")
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
        if source != "admin":
            # admin (secret-channel) feeds must not push out the public
            # cooldown; everything else that actually feeds the cat does —
            # a real public feed AND the scheduled auto-feed both start the
            # next 120-min window ("下次可以餵：120 分鐘後")
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


def add_feed_event(fed_at: datetime, source: str = "visitor", note: str | None = None) -> None:
    with _lock:
        conn = _db()
        conn.execute(
            "INSERT INTO feed_event (fed_at, clip, clip_ready_at, source, note) "
            "VALUES (?, NULL, NULL, ?, ?)",
            (fed_at.isoformat(), source, note),
        )
        conn.commit()


def set_feed_event_clip(fed_at: datetime, clip: str, clip_ready_at: datetime) -> None:
    with _lock:
        conn = _db()
        conn.execute(
            "UPDATE feed_event SET clip = ?, clip_ready_at = ? WHERE fed_at = ?",
            (clip, clip_ready_at.isoformat(), fed_at.isoformat()),
        )
        conn.commit()


def get_feed_events(since: datetime) -> list[dict]:
    with _lock:
        rows = _db().execute(
            "SELECT fed_at, clip, clip_ready_at, source, note FROM feed_event "
            "WHERE fed_at >= ? ORDER BY id DESC",
            (since.isoformat(),),
        ).fetchall()
    return [
        {"fed_at": r[0], "clip": r[1], "clip_ready_at": r[2],
         "source": r[3] or "visitor", "note": r[4]}
        for r in rows
    ]


def has_feed_in_window(start: datetime, end: datetime) -> bool:
    with _lock:
        row = _db().execute(
            "SELECT COUNT(*) FROM feed_event WHERE fed_at >= ? AND fed_at <= ?",
            (start.isoformat(), end.isoformat()),
        ).fetchone()
    return bool(row and row[0])


def _get_state(key: str, default: str = "") -> str:
    with _lock:
        row = _db().execute(
            "SELECT value FROM state WHERE key = ?", (key,)
        ).fetchone()
    return row[0] if row and row[0] is not None else default


def _set_state(key: str, value: str) -> None:
    with _lock:
        conn = _db()
        conn.execute(
            "INSERT INTO state (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
        conn.commit()


def get_auto_feed_windows() -> list[str]:
    try:
        return json.loads(_get_state("auto_feed_windows", "[]"))
    except ValueError:
        return []


def set_auto_feed_windows(windows: list[str]) -> None:
    _set_state("auto_feed_windows", json.dumps(windows))


def get_auto_feed_handled() -> dict:
    try:
        return json.loads(_get_state("auto_feed_handled", "{}"))
    except ValueError:
        return {}


def set_auto_feed_handled(handled: dict) -> None:
    _set_state("auto_feed_handled", json.dumps(handled))


def set_auto_feed_pending(window: str, at: datetime) -> None:
    _set_state("auto_feed_pending", json.dumps({"window": window, "at": at.isoformat()}))


def pop_auto_feed_pending(now: datetime, within_seconds: int) -> str | None:
    """Return (and clear) the pending auto-feed window if it was set within the
    last `within_seconds`, so the recorder can tag the matching feed_event as an
    auto-feed. Stale markers are cleared and ignored."""
    raw = _get_state("auto_feed_pending", "")
    if not raw:
        return None
    try:
        data = json.loads(raw)
        at = datetime.fromisoformat(data["at"])
        window = data["window"]
    except (ValueError, KeyError):
        _set_state("auto_feed_pending", "")
        return None
    _set_state("auto_feed_pending", "")
    if (now - at).total_seconds() <= within_seconds:
        return window
    return None


def set_visitor_feed_pending(ip: str | None, country: str | None, at: datetime) -> None:
    """Stash a web visitor's IP + country at /feed time so the recorder can
    attach them to the matching dispense (and push a Telegram alert). Only the
    site's /feed sets this, so app/physical-button/admin feeds — which have no
    IP — never match and never get pushed."""
    _set_state("visitor_feed_pending", json.dumps(
        {"ip": ip, "country": country, "at": at.isoformat()}))


def pop_visitor_feed_pending(now: datetime, within_seconds: int) -> dict | None:
    """Return (and clear) the pending web-visitor info if it was set within the
    last `within_seconds`. Stale/invalid markers are cleared and ignored."""
    raw = _get_state("visitor_feed_pending", "")
    if not raw:
        return None
    try:
        data = json.loads(raw)
        at = datetime.fromisoformat(data["at"])
    except (ValueError, KeyError):
        _set_state("visitor_feed_pending", "")
        return None
    _set_state("visitor_feed_pending", "")
    if (now - at).total_seconds() <= within_seconds:
        return {"ip": data.get("ip"), "country": data.get("country")}
    return None


def prune_feed_events(cutoff: datetime) -> None:
    with _lock:
        conn = _db()
        conn.execute("DELETE FROM feed_event WHERE fed_at < ?", (cutoff.isoformat(),))
        conn.commit()


def count_feeds_today(day_start: datetime) -> int:
    # public (visitor) feeds only — admin/secret-channel feeds (including
    # the admin_test simulated-visitor button) are excluded, matching the
    # "訪客餵食咗" label this backs
    with _lock:
        row = _db().execute(
            "SELECT COUNT(*) FROM feed_log WHERE fed_at >= ? "
            "AND (ip IS NULL OR (ip NOT LIKE 'admin:%' AND ip NOT LIKE 'admin_test:%' "
            "AND ip NOT LIKE 'auto:%'))",
            (day_start.isoformat(),),
        ).fetchone()
    return row[0] if row else 0
