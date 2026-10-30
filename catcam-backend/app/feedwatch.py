import asyncio
import logging
from datetime import datetime, timedelta

from . import db, notify
from .config import get_settings
from .scheduling import is_within_window, now


logger = logging.getLogger(__name__)

_CHECK_SECONDS = 60
_task: asyncio.Task | None = None


def build_alert_message(last_feed: dict | None, checked_at: datetime) -> str:
    """Build the owner-facing warning without exposing any visitor metadata."""
    s = get_settings()
    hours = s.feed_inactivity_alert_hours
    hours_text = str(int(hours)) if float(hours).is_integer() else str(hours)
    lines = [f"⚠️ Roll Roll 已經連續 {hours_text} 小時冇餵食紀錄"]
    if last_feed:
        fed_at = datetime.fromisoformat(last_feed["fed_at"])
        lines.append(f"🕐 最後餵食：{fed_at.strftime('%Y-%m-%d %H:%M')}")
    else:
        lines.append(
            f"🕐 今日 {s.open_time} 開放後仍未有任何餵食紀錄"
        )
    lines.append("🍚 請檢查糧兜、餵食機同 Roll Roll")
    return "\n".join(lines)


def _inactivity_anchor(
    checked_at: datetime,
    last_feed: dict | None,
) -> tuple[datetime, str]:
    """Return the timestamp to count from and a stable de-duplication key."""
    if last_feed:
        return datetime.fromisoformat(last_feed["fed_at"]), f"event:{last_feed['id']}"

    # A brand-new database has no event to count from. Start at today's public
    # opening time rather than warning immediately on first boot.
    s = get_settings()
    opened_at = checked_at.replace(
        hour=s.open_t.hour,
        minute=s.open_t.minute,
        second=0,
        microsecond=0,
    )
    return opened_at, "event:none"


async def _check_once(checked_at: datetime | None = None) -> bool:
    """Send one warning when a five-hour feed-event drought is due.

    Returns True only when Telegram accepted a new notification. This helper is
    also deliberately testable with a supplied timestamp; the production loop
    always uses Hong Kong `now()`.
    """
    checked_at = checked_at or now()
    if not is_within_window(checked_at):
        return False

    s = get_settings()
    last_feed = db.get_latest_feed_event()
    anchor, alert_key = _inactivity_anchor(checked_at, last_feed)
    if checked_at - anchor < timedelta(hours=s.feed_inactivity_alert_hours):
        return False
    if db.get_feed_inactivity_alert_key() == alert_key:
        return False

    sent = await notify.send(build_alert_message(last_feed, checked_at))
    if not sent:
        return False

    # Persist only after Telegram confirms success. A failed/no-op send is
    # retried on a later tick instead of silently suppressing the warning.
    db.set_feed_inactivity_alert_key(alert_key)
    logger.info(
        "feedwatch: sent inactivity alert for %s",
        last_feed["fed_at"] if last_feed else "no feed event",
    )
    return True


async def _loop() -> None:
    while True:
        try:
            await _check_once()
        except Exception as exc:  # never let a transient DB/Telegram error kill the task
            logger.warning("feedwatch: loop error: %s", exc)
        await asyncio.sleep(_CHECK_SECONDS)


def start() -> None:
    global _task
    s = get_settings()
    if not s.feed_inactivity_alert_enabled:
        return
    _task = asyncio.create_task(_loop())


def stop() -> None:
    if _task:
        _task.cancel()
