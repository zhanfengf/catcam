import unittest
from datetime import datetime, time
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from zoneinfo import ZoneInfo

from app import feedwatch


HK = ZoneInfo("Asia/Hong_Kong")
SETTINGS = SimpleNamespace(
    feed_inactivity_alert_hours=5.0,
    open_time="07:00",
    open_t=time(7, 0),
)


def event(event_id: int, fed_at: datetime, source: str = "auto") -> dict:
    return {
        "id": event_id,
        "fed_at": fed_at.isoformat(),
        "source": source,
        "note": None,
    }


class FeedInactivityWatchTests(unittest.IsolatedAsyncioTestCase):
    async def test_outside_public_hours_does_nothing(self):
        checked_at = datetime(2026, 10, 30, 6, 59, tzinfo=HK)

        with (
            patch.object(feedwatch, "is_within_window", return_value=False),
            patch.object(feedwatch.db, "get_latest_feed_event") as latest,
            patch.object(feedwatch.notify, "send", new_callable=AsyncMock) as send,
        ):
            result = await feedwatch._check_once(checked_at)

        self.assertFalse(result)
        latest.assert_not_called()
        send.assert_not_awaited()

    async def test_feed_outside_public_hours_resets_real_five_hour_clock(self):
        last_feed = event(41, datetime(2026, 10, 30, 6, 0, tzinfo=HK))
        before_due = datetime(2026, 10, 30, 10, 59, tzinfo=HK)

        with (
            patch.object(feedwatch, "get_settings", return_value=SETTINGS),
            patch.object(feedwatch, "is_within_window", return_value=True),
            patch.object(feedwatch.db, "get_latest_feed_event", return_value=last_feed),
            patch.object(feedwatch.db, "get_feed_inactivity_alert_key", return_value=""),
            patch.object(feedwatch.notify, "send", new_callable=AsyncMock) as send,
        ):
            result = await feedwatch._check_once(before_due)

        self.assertFalse(result)
        send.assert_not_awaited()

    async def test_sends_once_at_five_hours_and_persists_event_key(self):
        last_feed = event(41, datetime(2026, 10, 30, 6, 0, tzinfo=HK))
        due = datetime(2026, 10, 30, 11, 0, tzinfo=HK)

        with (
            patch.object(feedwatch, "get_settings", return_value=SETTINGS),
            patch.object(feedwatch, "is_within_window", return_value=True),
            patch.object(feedwatch.db, "get_latest_feed_event", return_value=last_feed),
            patch.object(feedwatch.db, "get_feed_inactivity_alert_key", return_value=""),
            patch.object(feedwatch.db, "set_feed_inactivity_alert_key") as set_key,
            patch.object(
                feedwatch.notify,
                "send",
                new_callable=AsyncMock,
                return_value=True,
            ) as send,
        ):
            result = await feedwatch._check_once(due)

        self.assertTrue(result)
        send.assert_awaited_once()
        message = send.await_args.args[0]
        self.assertIn("連續 5 小時冇餵食紀錄", message)
        self.assertIn("2026-10-30 06:00", message)
        self.assertNotIn("IP", message)
        self.assertNotIn("🌐", message)
        set_key.assert_called_once_with("event:41")

    async def test_same_drought_is_not_sent_twice(self):
        last_feed = event(41, datetime(2026, 10, 30, 6, 0, tzinfo=HK))
        checked_at = datetime(2026, 10, 30, 12, 0, tzinfo=HK)

        with (
            patch.object(feedwatch, "get_settings", return_value=SETTINGS),
            patch.object(feedwatch, "is_within_window", return_value=True),
            patch.object(feedwatch.db, "get_latest_feed_event", return_value=last_feed),
            patch.object(
                feedwatch.db,
                "get_feed_inactivity_alert_key",
                return_value="event:41",
            ),
            patch.object(feedwatch.notify, "send", new_callable=AsyncMock) as send,
        ):
            result = await feedwatch._check_once(checked_at)

        self.assertFalse(result)
        send.assert_not_awaited()

    async def test_new_feed_event_starts_a_new_alert_cycle(self):
        last_feed = event(42, datetime(2026, 10, 30, 9, 0, tzinfo=HK))
        checked_at = datetime(2026, 10, 30, 14, 0, tzinfo=HK)

        with (
            patch.object(feedwatch, "get_settings", return_value=SETTINGS),
            patch.object(feedwatch, "is_within_window", return_value=True),
            patch.object(feedwatch.db, "get_latest_feed_event", return_value=last_feed),
            patch.object(
                feedwatch.db,
                "get_feed_inactivity_alert_key",
                return_value="event:41",
            ),
            patch.object(feedwatch.db, "set_feed_inactivity_alert_key") as set_key,
            patch.object(
                feedwatch.notify,
                "send",
                new_callable=AsyncMock,
                return_value=True,
            ),
        ):
            result = await feedwatch._check_once(checked_at)

        self.assertTrue(result)
        set_key.assert_called_once_with("event:42")

    async def test_failed_telegram_send_does_not_suppress_retry(self):
        last_feed = event(41, datetime(2026, 10, 30, 6, 0, tzinfo=HK))
        checked_at = datetime(2026, 10, 30, 11, 0, tzinfo=HK)

        with (
            patch.object(feedwatch, "get_settings", return_value=SETTINGS),
            patch.object(feedwatch, "is_within_window", return_value=True),
            patch.object(feedwatch.db, "get_latest_feed_event", return_value=last_feed),
            patch.object(feedwatch.db, "get_feed_inactivity_alert_key", return_value=""),
            patch.object(feedwatch.db, "set_feed_inactivity_alert_key") as set_key,
            patch.object(
                feedwatch.notify,
                "send",
                new_callable=AsyncMock,
                return_value=False,
            ),
        ):
            result = await feedwatch._check_once(checked_at)

        self.assertFalse(result)
        set_key.assert_not_called()

    async def test_empty_database_counts_from_public_opening(self):
        before_due = datetime(2026, 10, 30, 11, 59, tzinfo=HK)
        due = datetime(2026, 10, 30, 12, 0, tzinfo=HK)

        with (
            patch.object(feedwatch, "get_settings", return_value=SETTINGS),
            patch.object(feedwatch, "is_within_window", return_value=True),
            patch.object(feedwatch.db, "get_latest_feed_event", return_value=None),
            patch.object(feedwatch.db, "get_feed_inactivity_alert_key", return_value=""),
            patch.object(feedwatch.db, "set_feed_inactivity_alert_key") as set_key,
            patch.object(
                feedwatch.notify,
                "send",
                new_callable=AsyncMock,
                return_value=True,
            ) as send,
        ):
            self.assertFalse(await feedwatch._check_once(before_due))
            self.assertTrue(await feedwatch._check_once(due))

        send.assert_awaited_once()
        set_key.assert_called_once_with("event:none")


if __name__ == "__main__":
    unittest.main()
