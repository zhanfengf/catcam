from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from . import db
from .config import get_settings


def tz() -> ZoneInfo:
    return ZoneInfo(get_settings().timezone)


def now() -> datetime:
    return datetime.now(tz())


def day_start(dt: datetime) -> datetime:
    return dt.replace(hour=0, minute=0, second=0, microsecond=0)


def is_within_window(dt: datetime) -> bool:
    s = get_settings()
    open_t: time = s.open_t
    close_t: time = s.close_t

    close_full = time(close_t.hour, close_t.minute, 59)
    return open_t <= dt.timetz().replace(tzinfo=None) <= close_full


def next_window_open(dt: datetime) -> datetime:
    """Earliest moment >= dt that falls inside the open window."""
    s = get_settings()
    if is_within_window(dt):
        return dt
    open_today = dt.replace(
        hour=s.open_t.hour, minute=s.open_t.minute, second=0, microsecond=0
    )
    if dt < open_today:
        return open_today

    return open_today + timedelta(days=1)


def current_cooldown_minutes() -> int:
    s = get_settings()
    return db.get_cooldown_minutes(s.cooldown_minutes)


def next_feed_at(
    last_fed_at: datetime | None,
    cooldown_minutes: int | None = None,
) -> datetime:
    """When feeding is next allowed, accounting for cooldown AND window."""
    n = now()
    cooldown = (
        current_cooldown_minutes()
        if cooldown_minutes is None
        else cooldown_minutes
    )
    if last_fed_at is None:
        candidate = n
    else:
        candidate = max(n, last_fed_at + timedelta(minutes=cooldown))
    return next_window_open(candidate)


def build_status(last_fed_at: datetime | None) -> dict:
    s = get_settings()
    n = now()
    cooldown = current_cooldown_minutes()
    open_now = is_within_window(n)
    cooldown_ok = last_fed_at is None or n >= last_fed_at + timedelta(
        minutes=cooldown
    )
    nxt = next_feed_at(last_fed_at, cooldown)
    can_feed = open_now and cooldown_ok

    if can_feed:
        reason = "ok"
    elif not open_now:
        reason = "outside_hours"
    else:
        reason = "cooldown"

    return {
        "can_feed": can_feed,
        "reason": reason,
        "amount": s.feed_amount,
        "cooldown_minutes": cooldown,
        "window": {
            "open": s.open_time,
            "close": s.close_time,
            "timezone": s.timezone,
            "is_open_now": open_now,
        },
        "last_fed_at": last_fed_at.isoformat() if last_fed_at else None,
        "next_feed_at": nxt.isoformat(),
        "seconds_until_next": max(0, int((nxt - n).total_seconds())),
        "server_time": n.isoformat(),
    }
