import asyncio
import logging
from datetime import datetime, time, timedelta

from . import db, ha
from .config import get_settings
from .scheduling import current_cooldown_minutes, now

logger = logging.getLogger(__name__)

_CHECK_SECONDS = 60
# how long after a window's end we'll still auto-feed. past this (e.g. the
# service was down through the whole window) we skip rather than feed hours late
_GRACE_MINUTES = 60
_LATEST_END = time(22, 59)

_task: asyncio.Task | None = None
_scheduler_lock = asyncio.Lock()


def parse_window(w: str) -> tuple[time, time] | None:
    """Parse one same-day window whose catch-up deadline cannot cross midnight."""
    try:
        a, b = w.split("-")
        sh, sm = (int(x) for x in a.split(":"))
        eh, em = (int(x) for x in b.split(":"))
        start, end = time(sh, sm), time(eh, em)
    except (ValueError, AttributeError):
        return None
    if start >= end or end > _LATEST_END:
        return None
    return start, end


def normalise_windows(raw: object) -> tuple[list[str], list[str]]:
    """Return canonical unique windows plus every rejected input value."""
    if not isinstance(raw, list):
        return [], [str(raw)]

    windows: list[str] = []
    invalid: list[str] = []
    for value in raw:
        original = str(value).strip()
        parsed = parse_window(original)
        if not original or not parsed:
            invalid.append(original)
            continue
        start, end = parsed
        canonical = f"{start.strftime('%H:%M')}-{end.strftime('%H:%M')}"
        if canonical not in windows:
            windows.append(canonical)

    if len(windows) > 10:
        invalid.extend(windows[10:])
        windows = windows[:10]
    return windows, invalid


def replace_windows(windows: list[str], saved_at: datetime) -> list[str]:
    """Save a schedule, prune obsolete handled keys and defer past new slots.

    A newly-added window that has already ended today starts tomorrow instead
    of being mistaken for a missed meal that should dispense immediately.
    Existing windows keep their handled date so an ordinary save cannot erase
    today's duplicate-feed protection.
    """
    previous = set(db.get_auto_feed_windows())
    handled = db.get_auto_feed_handled()
    today = saved_at.date().isoformat()
    current_t = saved_at.timetz().replace(tzinfo=None)
    deferred: list[str] = []

    for window in windows:
        parsed = parse_window(window)
        if not parsed:
            continue
        _, end_t = parsed
        if window not in previous and current_t >= end_t:
            handled[window] = today
            deferred.append(window)

    handled = {window: handled[window] for window in windows if window in handled}
    db.set_auto_feed_windows(windows)
    db.set_auto_feed_handled(handled)
    return deferred


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

        last_fed = db.get_last_fed_at()
        cooldown = current_cooldown_minutes()
        if last_fed and end_dt - last_fed < timedelta(minutes=cooldown):
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
            s = get_settings()
            if s.preview_mode:
                # Preview has no HA/recorder process. Simulate the complete
                # result directly in its isolated DB so UI work remains useful
                # without any possible path to the physical feeder.
                fed_at = now()
                db.record_feed(fed_at, "auto:preview", s.feed_amount, source="auto")
                db.add_feed_event(fed_at, source="auto", note=w)
            else:
                # marker before dispensing so the recorder's poller (which creates
                # the feed_event when times_dispensed bumps) can tag it as auto
                db.set_auto_feed_pending(w, n)
                await ha.dispense(s.feed_amount)
                db.record_feed(now(), "auto:system", s.feed_amount, source="auto")
            handled[w] = today
            changed = True
            logger.info(
                "autofeed: %s for window %s (no feed in window)",
                "simulated preview feed" if s.preview_mode else "dispensed",
                w,
            )
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
    s = get_settings()
    if not s.ha_token and not s.preview_mode:
        return
    _task = asyncio.create_task(_loop())


def stop() -> None:
    if _task:
        _task.cancel()
