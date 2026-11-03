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

    # A one-off wet-food booking blocks public kibble during its preparation
    # and meal window. Import here to keep the time helpers independent.
    from . import wet_reservation
    reservation = wet_reservation.active_at(n)
    wet_food_starts_at = None
    seconds_until_wet_food = None
    seconds_until_wet_food_end = None
    wet_food_in_window = False
    if reservation:
        can_feed = False
        reason = "wet_food_reserved"
        wet_food_starts_at = datetime.fromisoformat(reservation["starts_at"])
        seconds_until_wet_food = max(0, int((wet_food_starts_at - n).total_seconds()))
        wet_food_in_window = n >= wet_food_starts_at
        wet_food_ends_at = datetime.fromisoformat(reservation["ends_at"])
        seconds_until_wet_food_end = max(0, int((wet_food_ends_at - n).total_seconds()))
        nxt = next_window_open(max(nxt, wet_food_ends_at))

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
        "wet_food_starts_at": wet_food_starts_at.isoformat() if wet_food_starts_at else None,
        "seconds_until_wet_food": seconds_until_wet_food,
        "seconds_until_wet_food_end": seconds_until_wet_food_end,
        "wet_food_in_window": wet_food_in_window,
        "server_time": n.isoformat(),
    }
