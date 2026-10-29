import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, patch
from zoneinfo import ZoneInfo

from starlette.requests import Request

from app import autofeed, db, main, recorder


HK = ZoneInfo("Asia/Hong_Kong")


class AdminCooldownDbTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        db.init_db(str(Path(self.tempdir.name) / "catcam.db"))

    def tearDown(self):
        if db._conn is not None:
            db._conn.close()
            db._conn = None
        self.tempdir.cleanup()

    def test_force_feed_resets_cooldown_but_admin_test_does_not(self):
        initial = datetime(2026, 10, 29, 5, 0, tzinfo=HK)
        forced = initial + timedelta(minutes=30)
        simulated = forced + timedelta(minutes=10)

        db.record_feed(initial, "visitor", 10)
        db.record_feed(forced, "admin:owner", 10, source="admin")
        self.assertEqual(db.get_last_fed_at(), forced)

        db.record_feed(simulated, "admin_test:owner", 10, source="admin_test")
        self.assertEqual(db.get_last_fed_at(), forced)

    def test_force_feed_inside_long_window_marks_it_handled(self):
        db.set_auto_feed_windows(["05:00-08:00", "09:00-09:30"])
        forced = datetime(2026, 10, 29, 5, 10, tzinfo=HK)

        marked = autofeed.mark_windows_covered(forced)

        self.assertEqual(marked, ["05:00-08:00"])
        self.assertEqual(
            db.get_auto_feed_handled(),
            {"05:00-08:00": "2026-10-29"},
        )

    def test_force_feed_pending_marker_is_consumed_once(self):
        forced = datetime(2026, 10, 29, 18, 37, tzinfo=HK)
        detected = forced + timedelta(seconds=14)

        db.set_admin_feed_pending(forced)

        self.assertTrue(db.pop_admin_feed_pending(detected, 90))
        self.assertFalse(db.pop_admin_feed_pending(detected, 90))

    def test_recorder_resolves_force_feed_as_admin(self):
        detected = datetime(2026, 10, 29, 18, 37, 14, tzinfo=HK)

        with (
            patch.object(recorder.db, "pop_auto_feed_pending", return_value=None),
            patch.object(recorder.db, "pop_admin_feed_pending", return_value=True),
            patch.object(recorder.db, "pop_visitor_feed_pending") as pop_visitor,
        ):
            source, note, visitor = recorder._resolve_feed_source(detected)

        self.assertEqual((source, note, visitor), ("admin", None, None))
        pop_visitor.assert_not_called()


class AdminEndpointTests(unittest.IsolatedAsyncioTestCase):
    async def test_force_feed_marks_window_and_returns_fresh_cooldown(self):
        forced = datetime(2026, 10, 29, 5, 45, tzinfo=HK)
        request = Request({
            "type": "http",
            "method": "POST",
            "path": "/admin/feed",
            "headers": [],
            "client": ("203.0.113.4", 12345),
        })
        status = {"can_feed": False, "reason": "cooldown", "seconds_until_next": 7200}

        with (
            patch.object(main, "check_ip", return_value=True),
            patch.object(main, "verify_admin_signature", return_value=True),
            patch.object(main, "now", return_value=forced),
            patch.object(main.ha, "dispense", new_callable=AsyncMock),
            patch.object(main.db, "record_feed") as record_feed,
            patch.object(main.db, "set_admin_feed_pending") as set_admin_pending,
            patch.object(main.autofeed, "mark_windows_covered") as mark_covered,
            patch.object(main.db, "get_last_fed_at", return_value=forced),
            patch.object(main, "build_status", return_value=status),
        ):
            result = await main.admin_feed(request)

        record_feed.assert_called_once_with(forced, "admin:203.0.113.4", 10, source="admin")
        set_admin_pending.assert_called_once_with(forced)
        mark_covered.assert_called_once_with(forced)
        self.assertEqual(result["seconds_until_next"], 7200)


if __name__ == "__main__":
    unittest.main()
