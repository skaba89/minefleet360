"""Standalone tests for the SMTP alert adapter."""
import importlib.util
import unittest
from pathlib import Path
from unittest.mock import patch

file = Path(__file__).resolve().parents[1] / "infra/deploy/notify-alert-smtp.py"
spec = importlib.util.spec_from_file_location("notify_alert_smtp", file)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class AlertNotificationTests(unittest.TestCase):
    def test_only_alert_and_recovered_can_be_sent(self):
        with self.assertRaises(ValueError):
            module.compose_message("PENDING", "ops@example.test", "bot@example.test", "staging")

    def test_message_contains_no_probe_output(self):
        msg = module.compose_message("ALERT", "ops@example.test", "bot@example.test", "staging")
        self.assertIn("ALERT", msg["Subject"])
        self.assertNotIn("password", msg.get_content())

    def test_smtp_uses_starttls_before_auth(self):
        with patch.object(module.smtplib, "SMTP") as smtp:
            module.send_message(
                module.compose_message("RECOVERED", "ops@example.test", "bot@example.test", "staging"),
                "smtp.example.test", 587, "user", "secret",
            )
            connection = smtp.return_value.__enter__.return_value
            connection.starttls.assert_called_once()
            connection.login.assert_called_once_with("user", "secret")
            connection.send_message.assert_called_once()


if __name__ == "__main__":
    unittest.main()
