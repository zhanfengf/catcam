import asyncio
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, patch
from zoneinfo import ZoneInfo

from app import autofeed, db, wet_reservation
from app.scheduling import build_status


HKT = ZoneInfo("Asia/Hong_Kong")


def at(day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 11, day, hour, minute, tzinfo=HKT)


class WetReservationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        db.init_db(str(Path(self.tmp.name) / "test.db"))
        db.set_cooldown_minutes(180)

    def tearDown(self):
        db._conn.close()
        db._conn = None
        self.tmp.cleanup()

    def test_rejects_1829_feed_conflict_and_reports_earliest_time(self):
        db.set_last_fed_at(at(3, 17))
        with self.assertRaisesRegex(ValueError, "2026-11-03 20:00"):
            wet_reservation.save("2026-11-03", "18:30", "19:30", at(3, 17, 30))

    def test_public_feed_blocked_before_window_and_restored_after_expiry(self):
        wet_reservation.save("2026-11-03", "18:30", "19:30", at(3, 12))
        with patch("app.scheduling.now", return_value=at(3, 18, 29)):
            blocked = build_status(None)
        self.assertEqual(blocked["reason"], "wet_food_reserved")
        self.assertFalse(blocked["can_feed"])
        self.assertEqual(blocked["next_feed_at"], at(3, 19, 30).isoformat())
        self.assertEqual(blocked["seconds_until_wet_food"], 60)
        self.assertFalse(blocked["wet_food_in_window"])
        with patch("app.scheduling.now", return_value=at(3, 19, 30)):
            restored = build_status(None)
        self.assertTrue(restored["can_feed"])

    def test_editing_start_changes_wet_food_countdown_even_if_end_is_same(self):
        wet_reservation.save("2026-11-03", "18:30", "19:30", at(3, 12))
        with patch("app.scheduling.now", return_value=at(3, 17)):
            before = build_status(None)
        wet_reservation.save("2026-11-03", "18:45", "19:30", at(3, 17))
        with patch("app.scheduling.now", return_value=at(3, 17)):
            after = build_status(None)
        self.assertEqual(before["next_feed_at"], after["next_feed_at"])
        self.assertEqual(after["seconds_until_wet_food"] - before["seconds_until_wet_food"], 15 * 60)

    def test_meal_window_end_countdown_is_separate_from_public_opening(self):
        wet_reservation.save("2026-11-04", "01:00", "02:00", at(3, 12))
        with patch("app.scheduling.now", return_value=at(4, 1, 30)):
            status = build_status(None)
        self.assertTrue(status["wet_food_in_window"])
        self.assertEqual(status["seconds_until_wet_food_end"], 30 * 60)
        self.assertEqual(status["next_feed_at"], at(4, 7).isoformat())

    def test_wet_food_completed_early_resets_cooldown_from_actual_meal(self):
        wet_reservation.save("2026-11-03", "18:30", "19:30", at(3, 12))
        fed = at(3, 18, 15)
        db.record_feed(fed, "admin_wet_food:owner", None, source="admin_wet_food")
        self.assertTrue(wet_reservation.complete_or_cancel_for_feed(fed, "admin_wet_food"))
        with patch("app.scheduling.now", return_value=at(3, 18, 20)):
            status = build_status(db.get_last_fed_at())
        self.assertEqual(status["reason"], "cooldown")
        self.assertEqual(status["next_feed_at"], at(3, 21, 15).isoformat())

    def test_auto_window_skipped_once_and_logged_without_dispense(self):
        wet_reservation.save("2026-11-03", "18:30", "19:30", at(3, 12))
        db.set_auto_feed_windows(["17:00-17:30"])
        with patch("app.autofeed.now", return_value=at(3, 17, 30)):
            asyncio.run(autofeed._check_once_locked())
            asyncio.run(autofeed._check_once_locked())
        self.assertEqual(db.get_auto_feed_handled()["17:00-17:30"], "2026-11-03")
        row = db._conn.execute("SELECT COUNT(*), reason FROM auto_feed_skip_log").fetchone()
        self.assertEqual(row, (1, "因罐頭預約而跳過"))
        self.assertEqual(db._conn.execute("SELECT COUNT(*) FROM feed_log").fetchone()[0], 0)

    def test_cooldown_change_cancels_invalid_booking(self):
        db.set_last_fed_at(at(3, 15))
        wet_reservation.save("2026-11-03", "18:30", "19:30", at(3, 15, 5))
        db.set_cooldown_minutes(240)
        self.assertTrue(wet_reservation.cancel_if_cooldown_invalid(at(3, 15, 5), 240))
        self.assertIsNone(db.get_wet_reservation("2026-11-03"))

    def test_next_day_early_meal_blocks_previous_evening(self):
        wet_reservation.save("2026-11-04", "00:30", "01:00", at(3, 12))
        db.set_cooldown_minutes(240)
        with patch("app.scheduling.now", return_value=at(3, 21)):
            status = build_status(None)
        self.assertEqual(status["reason"], "wet_food_reserved")
        self.assertEqual(status["next_feed_at"], at(4, 7).isoformat())

    def test_petkit_feed_cancels_and_notifies_once(self):
        wet_reservation.save("2026-11-03", "18:30", "19:30", at(3, 12))
        self.assertTrue(wet_reservation.complete_or_cancel_for_feed(at(3, 17), "petkit"))
        self.assertIsNone(db.get_wet_reservation("2026-11-03"))
        sent = AsyncMock(return_value=True)
        with patch("app.wet_reservation.notify.send", sent):
            asyncio.run(wet_reservation.check_once(at(3, 17, 1)))
            asyncio.run(wet_reservation.check_once(at(3, 17, 2)))
        self.assertEqual(sent.await_count, 1)
        self.assertIn("PetKit", sent.await_args.args[0])

    def test_expiry_restores_public_rule_and_notifies(self):
        wet_reservation.save("2026-11-03", "18:30", "19:30", at(3, 12))
        sent = AsyncMock(return_value=True)
        with patch("app.wet_reservation.notify.send", sent):
            asyncio.run(wet_reservation.check_once(at(3, 19, 30)))
        self.assertIsNone(db.get_wet_reservation("2026-11-03"))
        self.assertIn("未記錄餵罐", sent.await_args.args[0])


if __name__ == "__main__":
    unittest.main()
