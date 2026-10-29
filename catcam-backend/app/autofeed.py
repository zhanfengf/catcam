import asyncio
import logging
from datetime import datetime, time, timedelta

from . import db, ha
from .config import get_settings
from .scheduling import now

logger = logging.getLogger(__name__)

_CHECK_SECONDS = 60
# how long after a window's end we'll still auto-feed. past this (e.g. the
# service was down through the whole window) we skip rather than feed hours late
_GRACE_MINUTES = 60

_task: asyncio.Task | None = None
_scheduler_lock = asyncio.Lock()


def parse_window(w: str) -> tuple[time, time] | None:
    """`"HH:MM-HH:MM"` -> (start, end), or None if malformed / start >= end."""
    try:
        a, b = w.split("-")
        sh, sm = (int(x) for x in a.split(":"))
        eh, em = (int(x) for x in b.split(":"))
        start, end = time(sh, sm), time(eh, em)
    except (ValueError, AttributeError):
        return None
    if start >= end:
        return None
    return start, end


def scheduler_lock() -> asyncio.Lock:
    """Shared lock for a force-feed and the auto-feed boundary check."""
    return _scheduler_lock


def mark_windows_covered(fed_at: datetime) -> list[str]:
    """Mark every auto-feed window containing `fed_at` as handled today.

    Called immediately after an owner force-feed succeeds, instead of waiting
    for the 10-second PetKit counter poll. This closes the race where a feed at
    the very end of a window could otherwise be followed by the scheduler's
    own dispense before the recorder has observed it. It also makes a feed near
    the start of a window cover that whole window even when the window is
    longer than the public cooldown.
    """
    current_t = fed_at.timetz().replace(tzinfo=None)
    today = fed_at.date().isoformat()
    handled = db.get_auto_feed_handled()
    marked: list[str] = []

    for window in db.get_auto_feed_windows():
        parsed = parse_window(window)
        if not parsed:
            continue
        start_t, end_t = parsed
        if start_t <= current_t <= end_t:
            handled[window] = today
            marked.append(window)

    if marked:
        db.set_auto_feed_handled(handled)
        logger.info("autofeed: force-feed covered window(s): %s", ", ".join(marked))
    return marked


async def _check_once() -> None:
    async with _scheduler_lock:
        await _check_once_locked()


async def _check_once_locked() -> None:
    windows = db.get_auto_feed_windows()
    if not windows:
        return
    if db.get_fasting()["active"]:
        # admin-initiated fast pauses the auto-feed safety net too — it'd
        # otherwise dispense regardless, defeating the point of fasting mode.
        # Windows are deliberately left unhandled (not marked done) so that
        # if fasting clears while still within _GRACE_MINUTES, the next tick
        # catches up and feeds normally instead of silently skipping it.
        return

    n = now()
    today = n.date().isoformat()
    handled = db.get_auto_feed_handled()
    changed = False

    for w in windows:
        parsed = parse_window(w)
        if not parsed:
            continue
        _, end_t = parsed

        if handled.get(w) == today:
            continue
        if n.time() < end_t:
            continue  # window hasn't closed yet today

        end_dt = n.replace(hour=end_t.hour, minute=end_t.minute, second=0, microsecond=0)

        if n > end_dt + timedelta(minutes=_GRACE_MINUTES):
            handled[w] = today  # too late to feed sensibly — just mark done
            changed = True
            continue

        s = get_settings()
        last_fed = db.get_last_fed_at()
        if last_fed and end_dt - last_fed < timedelta(minutes=s.cooldown_minutes):
            # a feed (any source, any window) already landed within the
            # global cooldown of this window's close — treat it as already
            # covered rather than re-checking the window's own fixed range.
            # Keys this off wall-clock distance instead of the window string
            # so editing a window's times mid-day can't make an already-fed
            # slot look "unfed" again (the exact bug that caused the
            # 2026-10-28 double feed: a window edit after the day's feed
            # moved the lookup range away from the actual fed_at timestamp).
            handled[w] = today
            changed = True
            continue

        # nobody fed within cooldown of this window and we're still within grace — feed now
        try:
            # marker before dispensing so the recorder's poller (which creates
            # the feed_event when times_dispensed bumps) can tag it as auto
            db.set_auto_feed_pending(w, n)
            await ha.dispense(s.feed_amount)
            db.record_feed(now(), "auto:system", s.feed_amount, source="auto")
            handled[w] = today
            changed = True
            logger.info("autofeed: dispensed for window %s (no feed in window)", w)
        except ha.HAError as exc:
            # clear the stale marker and leave the window unhandled so it retries
            # on the next tick while still within grace
            db.pop_auto_feed_pending(n, 0)
            logger.warning("autofeed: HA dispense failed for window %s: %s", w, exc)

    if changed:
        db.set_auto_feed_handled(handled)


async def _loop() -> None:
    while True:
        try:
            await _check_once()
        except Exception as exc:  # never let the scheduler task die silently
            logger.warning("autofeed: loop error: %s", exc)
        await asyncio.sleep(_CHECK_SECONDS)


def start() -> None:
    global _task
    if not get_settings().ha_token:
        return
    _task = asyncio.create_task(_loop())


def stop() -> None:
    if _task:
        _task.cancel()
