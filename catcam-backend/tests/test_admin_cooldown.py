import json
import tempfile
import unittest
from datetime import datetime, time, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from zoneinfo import ZoneInfo

from starlette.requests import Request

from app import autofeed, db, main, recorder, scheduling


HK = ZoneInfo("Asia/Hong_Kong")


class AdminCooldownDbTests(unittest.IsolatedAsyncioTestCase):
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

    def test_dynamic_cooldown_falls_back_then_persists(self):
        self.assertEqual(db.get_cooldown_minutes(120), 120)

        db.set_cooldown_minutes(180)

        self.assertEqual(db.get_cooldown_minutes(120), 180)
        with self.assertRaises(ValueError):
            db.set_cooldown_minutes(119)
        with self.assertRaises(ValueError):
            db.set_cooldown_minutes(241)
        with self.assertRaises(ValueError):
            db.set_cooldown_minutes(True)

    def test_external_petkit_feed_resets_cooldown_without_feed_log(self):
        detected = datetime(2026, 10, 30, 5, 45, tzinfo=HK)
        before = db.count_feeds_today(detected.replace(hour=0, minute=0))

        source, note, visitor = recorder._record_detected_feed(detected)

        self.assertEqual((source, note, visitor), ("petkit", None, None))
        self.assertEqual(db.get_last_fed_at(), detected)
        self.assertEqual(
            db.count_feeds_today(detected.replace(hour=0, minute=0)),
            before,
        )
        self.assertEqual(db.get_latest_feed_event()["source"], "petkit")

    def test_admin_test_marker_preserves_cooldown_exception(self):
        previous = datetime(2026, 10, 30, 5, 0, tzinfo=HK)
        detected = previous + timedelta(minutes=10)
        db.record_feed(previous, "visitor", 10)
        db.set_admin_test_pending(detected - timedelta(seconds=2))

        source, note, visitor = recorder._record_detected_feed(detected)

        self.assertEqual((source, note, visitor), ("admin_test", None, None))
        self.assertEqual(db.get_last_fed_at(), previous)
        self.assertEqual(db.get_latest_feed_event()["source"], "admin_test")
        self.assertFalse(db.pop_admin_test_pending(detected, 90))

    def test_existing_countdown_recalculates_immediately(self):
        last = datetime(2026, 10, 30, 10, 0, tzinfo=HK)
        checked_at = datetime(2026, 10, 30, 11, 0, tzinfo=HK)
        settings = SimpleNamespace(
            cooldown_minutes=120,
            feed_amount=10,
            open_time="07:00",
            close_time="23:59",
            timezone="Asia/Hong_Kong",
            open_t=time(7, 0),
            close_t=time(23, 59),
        )
        db.set_cooldown_minutes(180)

        with (
            patch.object(scheduling, "get_settings", return_value=settings),
            patch.object(scheduling, "now", return_value=checked_at),
        ):
            result = scheduling.build_status(last)

        self.assertEqual(result["cooldown_minutes"], 180)
        self.assertEqual(result["next_feed_at"], "2026-10-30T13:00:00+08:00")
        self.assertEqual(result["seconds_until_next"], 7200)

    def test_cooldown_crossing_close_moves_to_next_open(self):
        last = datetime(2026, 10, 30, 21, 28, tzinfo=HK)
        checked_at = last
        settings = SimpleNamespace(
            cooldown_minutes=120,
            feed_amount=10,
            open_time="07:00",
            close_time="23:59",
            timezone="Asia/Hong_Kong",
            open_t=time(7, 0),
            close_t=time(23, 59),
        )
        db.set_cooldown_minutes(180)

        with (
            patch.object(scheduling, "get_settings", return_value=settings),
            patch.object(scheduling, "now", return_value=checked_at),
        ):
            result = scheduling.build_status(last)

        self.assertEqual(result["next_feed_at"], "2026-10-31T07:00:00+08:00")

    def test_force_feed_inside_long_window_marks_it_handled(self):
        db.set_auto_feed_windows(["05:00-08:00", "09:00-09:30"])
        forced = datetime(2026, 10, 29, 5, 10, tzinfo=HK)

        marked = autofeed.mark_windows_covered(forced)

        self.assertEqual(marked, ["05:00-08:00"])
        self.assertEqual(
            db.get_auto_feed_handled(),
            {"05:00-08:00": "2026-10-29"},
        )

    def test_auto_feed_windows_reject_cross_midnight_and_late_end(self):
        windows, invalid = autofeed.normalise_windows([
            "00:00-00:30",
            "21:30-22:59",
            "23:30-00:30",
            "22:30-23:00",
            "06:00-06:00",
        ])

        self.assertEqual(windows, ["00:00-00:30", "21:30-22:59"])
        self.assertEqual(invalid, [
            "23:30-00:30",
            "22:30-23:00",
            "06:00-06:00",
        ])

    def test_replacing_windows_prunes_old_keys_and_preserves_current_key(self):
        db.set_auto_feed_windows(["05:30-06:00", "05:45-06:15"])
        db.set_auto_feed_handled({
            "05:30-06:00": "2026-10-30",
            "05:45-06:15": "2026-10-28",
        })

        deferred = autofeed.replace_windows(
            ["05:30-06:00", "18:00-18:30"],
            datetime(2026, 10, 30, 12, 0, tzinfo=HK),
        )

        self.assertEqual(deferred, [])
        self.assertEqual(
            db.get_auto_feed_handled(),
            {"05:30-06:00": "2026-10-30"},
        )

    def test_new_window_that_already_ended_starts_tomorrow(self):
        db.set_auto_feed_windows(["05:30-06:00"])
        db.set_auto_feed_handled({"05:30-06:00": "2026-10-30"})

        deferred = autofeed.replace_windows(
            ["05:30-06:00", "11:30-12:00"],
            datetime(2026, 10, 30, 12, 10, tzinfo=HK),
        )

        self.assertEqual(deferred, ["11:30-12:00"])
        self.assertEqual(db.get_auto_feed_handled(), {
            "05:30-06:00": "2026-10-30",
            "11:30-12:00": "2026-10-30",
        })

    async def test_preview_auto_feed_writes_event_without_home_assistant(self):
        db.set_auto_feed_windows(["07:00-07:30"])
        checked_at = datetime(2026, 10, 30, 7, 31, tzinfo=HK)
        settings = SimpleNamespace(
            preview_mode=True,
            cooldown_minutes=120,
            feed_amount=10,
        )

        with (
            patch.object(autofeed, "get_settings", return_value=settings),
            patch.object(autofeed, "now", return_value=checked_at),
            patch.object(autofeed.ha, "dispense", new_callable=AsyncMock) as dispense,
        ):
            await autofeed._check_once_locked()

        dispense.assert_not_awaited()
        self.assertEqual(db.get_last_fed_at(), checked_at)
        self.assertEqual(db.get_latest_feed_event()["source"], "auto")
        self.assertEqual(db.get_latest_feed_event()["note"], "07:00-07:30")

    async def test_auto_feed_uses_dynamic_cooldown_exact_boundary(self):
        db.set_auto_feed_windows(["08:30-09:00"])
        db.set_cooldown_minutes(180)
        db.record_feed(
            datetime(2026, 10, 30, 6, 0, tzinfo=HK),
            "visitor",
            10,
        )
        checked_at = datetime(2026, 10, 30, 9, 0, tzinfo=HK)
        settings = SimpleNamespace(
            preview_mode=True,
            cooldown_minutes=120,
            feed_amount=10,
        )

        with (
            patch.object(autofeed, "get_settings", return_value=settings),
            patch.object(autofeed, "now", return_value=checked_at),
            patch.object(autofeed.ha, "dispense", new_callable=AsyncMock) as dispense,
        ):
            await autofeed._check_once_locked()

        dispense.assert_not_awaited()
        self.assertEqual(db.get_last_fed_at(), checked_at)
        self.assertEqual(db.get_latest_feed_event()["source"], "auto")

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

    def test_wet_food_resets_cooldown_but_not_visitor_count(self):
        visitor = datetime(2026, 10, 29, 7, 5, tzinfo=HK)
        wet_food = visitor + timedelta(minutes=30)

        db.record_feed(visitor, "visitor", 10)
        db.record_feed(
            wet_food,
            "admin_wet_food:owner",
            None,
            source="admin_wet_food",
        )
        db.add_feed_event(wet_food, source="admin_wet_food")

        self.assertEqual(db.get_last_fed_at(), wet_food)
        self.assertEqual(db.count_feeds_today(visitor.replace(hour=0, minute=0)), 1)
        self.assertEqual(db.get_feed_events(visitor)[0], {
            "fed_at": wet_food.isoformat(),
            "clip": None,
            "clip_ready_at": None,
            "source": "admin_wet_food",
            "note": None,
        })

    def test_latest_feed_event_uses_newest_timestamp_from_every_source(self):
        first = datetime(2026, 10, 29, 23, 30, tzinfo=HK)
        latest = datetime(2026, 10, 30, 6, 0, tzinfo=HK)
        db.add_feed_event(first, source="visitor")
        db.add_feed_event(latest, source="auto", note="05:30-06:00")

        result = db.get_latest_feed_event()

        self.assertEqual(result["fed_at"], latest.isoformat())
        self.assertEqual(result["source"], "auto")
        self.assertEqual(result["note"], "05:30-06:00")


class AdminEndpointTests(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def _json_request(path: str, payload: dict) -> Request:
        body = json.dumps(payload).encode()

        async def receive():
            return {"type": "http.request", "body": body, "more_body": False}

        return Request({
            "type": "http",
            "method": "POST",
            "path": path,
            "headers": [(b"content-type", b"application/json")],
            "client": ("203.0.113.4", 12345),
        }, receive)

    async def test_auto_feed_api_rejects_cross_midnight_window(self):
        request = self._json_request(
            "/admin/auto-feed",
            {"windows": ["23:30-00:30"]},
        )

        with (
            patch.object(main, "check_ip", return_value=True),
            patch.object(main, "verify_admin_signature", return_value=True),
            patch.object(main.autofeed, "replace_windows") as replace_windows,
        ):
            result = await main.admin_set_auto_feed(request)

        self.assertEqual(result.status_code, 422)
        self.assertEqual(
            json.loads(result.body)["reason"],
            "invalid_auto_feed_window",
        )
        replace_windows.assert_not_called()

    async def test_cooldown_api_accepts_integer_boundaries(self):
        for value in (120, 180, 240):
            with self.subTest(value=value):
                request = self._json_request(
                    "/admin/cooldown",
                    {"cooldown_minutes": value},
                )
                status = {
                    "can_feed": False,
                    "reason": "cooldown",
                    "cooldown_minutes": value,
                    "seconds_until_next": value * 60,
                }
                with (
                    patch.object(main, "check_ip", return_value=True),
                    patch.object(main, "verify_admin_signature", return_value=True),
                    patch.object(main.db, "set_cooldown_minutes") as save,
                    patch.object(main.db, "get_last_fed_at", return_value=None),
                    patch.object(main, "build_status", return_value=status),
                ):
                    result = await main.admin_set_cooldown(request)

                save.assert_called_once_with(value)
                self.assertTrue(result["ok"])
                self.assertEqual(result["cooldown_minutes"], value)

    async def test_cooldown_api_rejects_invalid_values(self):
        for value in (None, True, 119, 241, 180.5, "180"):
            with self.subTest(value=value):
                request = self._json_request(
                    "/admin/cooldown",
                    {"cooldown_minutes": value},
                )
                with (
                    patch.object(main, "check_ip", return_value=True),
                    patch.object(main, "verify_admin_signature", return_value=True),
                    patch.object(main.db, "set_cooldown_minutes") as save,
                ):
                    result = await main.admin_set_cooldown(request)

                self.assertEqual(result.status_code, 422)
                self.assertEqual(
                    json.loads(result.body)["reason"],
                    "invalid_cooldown_minutes",
                )
                save.assert_not_called()

    async def test_failed_admin_test_clears_pending_marker(self):
        request = Request({
            "type": "http",
            "method": "POST",
            "path": "/admin/feed-test",
            "headers": [],
            "client": ("203.0.113.4", 12345),
        })
        pending_at = datetime(2026, 10, 30, 12, 0, tzinfo=HK)
        settings = SimpleNamespace(
            preview_mode=False,
            feed_amount=10,
            client_ip_header="cf-connecting-ip",
        )

        with (
            patch.object(main, "check_ip", return_value=True),
            patch.object(main, "verify_admin_signature", return_value=True),
            patch.object(main, "get_settings", return_value=settings),
            patch.object(main, "now", return_value=pending_at),
            patch.object(main.db, "set_admin_test_pending") as set_pending,
            patch.object(main.db, "clear_admin_test_pending") as clear_pending,
            patch.object(
                main.ha,
                "dispense",
                new_callable=AsyncMock,
                side_effect=main.ha.HAError("offline"),
            ),
        ):
            result = await main.admin_feed_test(request)

        self.assertEqual(result.status_code, 502)
        set_pending.assert_called_once_with(pending_at)
        clear_pending.assert_called_once_with()

    async def test_auto_feed_api_returns_past_new_windows_as_tomorrow(self):
        saved_at = datetime(2026, 10, 30, 12, 10, tzinfo=HK)
        request = self._json_request(
            "/admin/auto-feed",
            {"windows": ["07:00-07:30", "11:30-12:00"]},
        )

        with (
            patch.object(main, "check_ip", return_value=True),
            patch.object(main, "verify_admin_signature", return_value=True),
            patch.object(main, "now", return_value=saved_at),
            patch.object(
                main.autofeed,
                "replace_windows",
                return_value=["11:30-12:00"],
            ) as replace_windows,
        ):
            result = await main.admin_set_auto_feed(request)

        replace_windows.assert_called_once_with(
            ["07:00-07:30", "11:30-12:00"],
            saved_at,
        )
        self.assertEqual(result["starts_tomorrow"], ["11:30-12:00"])

    async def test_preview_public_feed_never_calls_home_assistant(self):
        request = Request({
            "type": "http",
            "method": "POST",
            "path": "/feed",
            "headers": [],
            "client": ("203.0.113.4", 12345),
        })
        fed_at = datetime(2026, 10, 30, 12, 0, tzinfo=HK)
        settings = SimpleNamespace(
            preview_mode=True,
            client_ip_header="cf-connecting-ip",
        )
        ready = {"can_feed": True, "amount": 10}
        cooldown = {"can_feed": False, "reason": "cooldown"}

        with (
            patch.object(main, "check_ip", return_value=True),
            patch.object(main, "get_settings", return_value=settings),
            patch.object(main.db, "get_last_fed_at", side_effect=[None, fed_at]),
            patch.object(main, "build_status", side_effect=[ready, cooldown]),
            patch.object(main, "now", return_value=fed_at),
            patch.object(main.ha, "dispense", new_callable=AsyncMock) as dispense,
            patch.object(main.db, "record_feed") as record_feed,
            patch.object(main.db, "add_feed_event") as add_feed_event,
            patch.object(main.db, "set_visitor_feed_pending") as set_pending,
        ):
            result = await main.feed(request)

        dispense.assert_not_awaited()
        record_feed.assert_called_once_with(fed_at, "203.0.113.4", 10)
        add_feed_event.assert_called_once_with(
            fed_at,
            source="visitor",
            note="preview",
        )
        set_pending.assert_not_called()
        self.assertTrue(result["ok"])

    async def test_force_feed_marks_window_and_returns_fresh_cooldown(self):
        forced = datetime(2026, 10, 29, 5, 45, tzinfo=HK)
        request = Request({
            "type": "http",
            "method": "POST",
            "path": "/admin/feed",
            "headers": [],
            "client": ("203.0.113.4", 12345),
        })
        status = {
            "can_feed": False,
            "reason": "cooldown",
            "seconds_until_next": 7200,
            "cooldown_minutes": 120,
        }

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

    async def test_wet_food_logs_event_without_dispensing_and_covers_window(self):
        fed_at = datetime(2026, 10, 29, 7, 15, tzinfo=HK)
        request = Request({
            "type": "http",
            "method": "POST",
            "path": "/admin/wet-food",
            "headers": [],
            "client": ("203.0.113.4", 12345),
        })
        status = {"can_feed": False, "reason": "cooldown", "seconds_until_next": 7200}

        with (
            patch.object(main, "check_ip", return_value=True),
            patch.object(main, "verify_admin_signature", return_value=True),
            patch.object(main, "now", return_value=fed_at),
            patch.object(main.ha, "dispense", new_callable=AsyncMock) as dispense,
            patch.object(main.db, "record_feed") as record_feed,
            patch.object(main.db, "add_feed_event") as add_feed_event,
            patch.object(main.autofeed, "mark_windows_covered") as mark_covered,
            patch.object(main.db, "get_last_fed_at", return_value=fed_at),
            patch.object(main, "build_status", return_value=status),
        ):
            result = await main.admin_wet_food(request)

        dispense.assert_not_awaited()
        record_feed.assert_called_once_with(
            fed_at,
            "admin_wet_food:203.0.113.4",
            None,
            source="admin_wet_food",
        )
        add_feed_event.assert_called_once_with(fed_at, source="admin_wet_food")
        mark_covered.assert_called_once_with(fed_at)
        self.assertEqual(result["fed_at"], fed_at.isoformat())
        self.assertEqual(result["seconds_until_next"], 7200)


class RecorderNotificationTests(unittest.IsolatedAsyncioTestCase):
    async def test_auto_source_records_clip_then_sends_auto_notification(self):
        fed_at = datetime(2026, 10, 30, 7, 30, tzinfo=HK)

        with tempfile.TemporaryDirectory() as tempdir:
            settings = SimpleNamespace(
                post_roll_seconds=0,
                pre_roll_seconds=15,
                recording_seconds=60,
                notify_visitor_feeds=True,
                notify_auto_feeds=True,
            )

            async def create_clip(final_path, _seconds):
                final_path.write_bytes(b"test mp4")

            with (
                patch.object(recorder, "get_settings", return_value=settings),
                patch.object(recorder, "recordings_dir", return_value=Path(tempdir)),
                patch.object(recorder.asyncio, "sleep", new_callable=AsyncMock),
                patch.object(recorder.buffer, "segments_covering", return_value=[]),
                patch.object(
                    recorder,
                    "_record_clip_live_export",
                    new_callable=AsyncMock,
                    side_effect=create_clip,
                ),
                patch.object(recorder.db, "set_feed_event_clip") as set_clip,
                patch.object(recorder, "_cleanup_old"),
                patch.object(
                    recorder,
                    "_notify_auto_feed",
                    new_callable=AsyncMock,
                ) as notify_auto,
                patch.object(
                    recorder,
                    "_notify_visitor_feed",
                    new_callable=AsyncMock,
                ) as notify_visitor,
            ):
                await recorder._record_clip(fed_at, visitor=None, source="auto")

        clip_name = "2026-10-30_073000.mp4"
        set_clip.assert_called_once()
        self.assertEqual(set_clip.call_args.args[:2], (fed_at, clip_name))
        notify_auto.assert_awaited_once_with(fed_at, clip_name)
        notify_visitor.assert_not_awaited()

    async def test_auto_feed_notification_has_clip_but_no_ip(self):
        fed_at = datetime(2026, 10, 30, 7, 30, tzinfo=HK)
        clip_name = "2026-10-30_073000.mp4"

        with patch.object(recorder.notify, "send", new_callable=AsyncMock) as send:
            await recorder._notify_auto_feed(fed_at, clip_name)

        send.assert_awaited_once()
        message = send.await_args.args[0]
        self.assertEqual(
            message,
            "🤖 自動餵食咗 Roll Roll\n"
            "🕐 2026-10-30 07:30\n"
            "📹 錄影片段：https://cat.kelvinp.work/clips/2026-10-30_073000.mp4",
        )
        self.assertNotIn("IP", message)
        self.assertNotIn("🌐", message)

    async def test_auto_feed_notification_reports_failed_recording_without_ip(self):
        fed_at = datetime(2026, 10, 30, 7, 30, tzinfo=HK)

        with patch.object(recorder.notify, "send", new_callable=AsyncMock) as send:
            await recorder._notify_auto_feed(fed_at, None)

        message = send.await_args.args[0]
        self.assertIn("🤖 自動餵食咗 Roll Roll", message)
        self.assertIn("📹 錄影片段整唔到", message)
        self.assertNotIn("🌐", message)


if __name__ == "__main__":
    unittest.main()
