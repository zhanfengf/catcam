import logging
import unittest

from app.logging_utils import SensitiveUrlFilter, redact_sensitive_urls


class SensitiveLoggingTests(unittest.TestCase):
    def test_redacts_telegram_bot_token_from_url(self):
        message = (
            'HTTP Request: POST '
            '"https://api.telegram.org/bot123456:TEST_secret-token/sendMessage" '
            '"HTTP/1.1 200 OK"'
        )

        redacted = redact_sensitive_urls(message)

        self.assertNotIn("123456:TEST_secret-token", redacted)
        self.assertIn("https://api.telegram.org/bot[REDACTED]/sendMessage", redacted)

    def test_filter_redacts_formatted_log_record(self):
        record = logging.LogRecord(
            name="httpx",
            level=logging.INFO,
            pathname=__file__,
            lineno=1,
            msg='HTTP Request: %s "%s"',
            args=(
                "POST",
                "https://api.telegram.org/bot987654:ANOTHER_secret/sendMessage",
            ),
            exc_info=None,
        )

        self.assertTrue(SensitiveUrlFilter().filter(record))
        self.assertEqual(
            record.getMessage(),
            'HTTP Request: POST '
            '"https://api.telegram.org/bot[REDACTED]/sendMessage"',
        )

    def test_non_telegram_urls_are_unchanged(self):
        message = "HTTP Request: GET http://192.168.99.183:8123/api/ HTTP/1.1 200 OK"
        self.assertEqual(redact_sensitive_urls(message), message)
