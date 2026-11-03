"""One-off wet-food reservations in Hong Kong time."""

import asyncio
import re
from datetime import date, datetime, time, timedelta

from . import db, notify
from .scheduling import current_cooldown_minutes, now, tz

_task: asyncio.Task | None = None


def parse_slot(meal_date: str, start: str, end: str, at: datetime) -> tuple[datetime, datetime]:
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", meal_date) or not all(
        re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", value) for value in (start, end)
    ):
        raise ValueError("請用香港日期 YYYY-MM-DD 及 HH:MM 時間設定預約")
    day = date.fromisoformat(meal_date)
    starts = datetime.combine(day, time.fromisoformat(start), tzinfo=tz())
    ends = datetime.combine(day, time.fromisoformat(end), tzinfo=tz())
    minutes = (ends - starts).total_seconds() / 60
    if not 15 <= minutes <= 120 or starts <= at:
        raise ValueError("預留時段須在未來、同日完結，長度為 15 至 120 分鐘")
    return starts, ends


def earliest_start(at: datetime, cooldown: int | None = None) -> datetime:
    minutes = cooldown if cooldown is not None else current_cooldown_minutes()
    latest = db.get_last_fed_at()
    return max(at, latest + timedelta(minutes=minutes)) if latest else at


def save(meal_date: str, start: str, end: str, at: datetime) -> dict:
    starts, ends = parse_slot(meal_date, start, end, at)
    earliest = earliest_start(at)
    if starts < earliest:
        raise ValueError(f"餐前禁乾糧時間不足；最早可由 {earliest.strftime('%Y-%m-%d %H:%M')} 開始")
    return db.save_wet_reservation(meal_date, starts, ends, at)


def active_at(at: datetime) -> dict | None:
    for day in (at.date(), (at + timedelta(days=1)).date()):
        reservation = db.get_wet_reservation(day.isoformat())
        if not reservation:
            continue
        starts = datetime.fromisoformat(reservation["starts_at"])
        ends = datetime.fromisoformat(reservation["ends_at"])
        if starts - timedelta(minutes=current_cooldown_minutes()) <= at < ends:
            return reservation
    return None


def complete_or_cancel_for_feed(at: datetime, source: str) -> bool:
    reservation = active_at(at)
    if not reservation:
        return False
    if source == "admin_wet_food" and at.date().isoformat() == reservation["meal_date"]:
        return db.transition_wet_reservation(reservation["id"], "completed", "wet_food", at)
    label = "petkit" if source == "petkit" else source
    return db.transition_wet_reservation(
        reservation["id"], "cancelled_feed", label, at, notify=source == "petkit"
    )


def cancel_if_cooldown_invalid(at: datetime, minutes: int) -> bool:
    latest = db.get_last_fed_at()
    cancelled = False
    for day in (at.date(), (at + timedelta(days=1)).date()):
        reservation = db.get_wet_reservation(day.isoformat())
        if not reservation:
            continue
        starts = datetime.fromisoformat(reservation["starts_at"])
        if latest and latest + timedelta(minutes=minutes) > starts:
            cancelled = db.transition_wet_reservation(
                reservation["id"], "cancelled_cooldown", "cooldown_changed", at
            ) or cancelled
    return cancelled


def guard_auto_window(window: str, at: datetime) -> int | None:
    """Return the reservation id when this day's window must not dispense."""
    try:
        a, b = window.split("-")
        day = at.date()
        window_start = datetime.combine(day, time.fromisoformat(a), tzinfo=tz())
        window_end = datetime.combine(day, time.fromisoformat(b), tzinfo=tz())
    except ValueError:
        return None
    reservations = (
        db.get_wet_reservations_for_guard(day.isoformat())
        + db.get_wet_reservations_for_guard((day + timedelta(days=1)).isoformat())
    )
    for reservation in reservations:
        starts = datetime.fromisoformat(reservation["starts_at"])
        ends = datetime.fromisoformat(reservation["ends_at"])
        blocked_from = starts - timedelta(minutes=current_cooldown_minutes())
        if window_start < ends and window_end > blocked_from:
            return reservation["id"]
    return None


async def check_once(at: datetime | None = None) -> None:
    at = at or now()
    for reservation in db.get_due_wet_reservations(at):
        db.transition_wet_reservation(
            reservation["id"], "expired", "wet_food_not_recorded", at, notify=True
        )
    for item in db.pending_wet_reservation_notifications():
        if item["status"] == "expired":
            message = f"🥫 Roll Roll 預留罐頭餐 {item['meal_date']} {item['starts_at'][11:16]}–{item['ends_at'][11:16]} 已結束，未記錄餵罐。公開餵食已恢復原有規則。"
        elif item["reason"] == "petkit":
            message = f"⚠️ 偵測到 PetKit 出糧；{item['meal_date']} 的罐頭餐預約已取消，餐前禁乾糧時間無法保證。"
        else:
            continue
        if await notify.send(message):
            db.clear_wet_reservation_notification(item["id"])


async def _loop() -> None:
    while True:
        try:
            await check_once()
        except Exception:
            import logging
            logging.getLogger(__name__).exception("wet food reservation check failed")
        await asyncio.sleep(60)


def start() -> None:
    global _task
    _task = asyncio.create_task(_loop())


def stop() -> None:
    if _task:
        _task.cancel()
