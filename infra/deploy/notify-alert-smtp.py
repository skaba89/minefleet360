#!/usr/bin/env python3
"""SMTP notification adapter for MineFleet operational alert events.

Explicit invocation only; no credentials, sensitive probes or PII in output.
"""
from __future__ import annotations

import argparse
import os
import smtplib
import ssl
import sys
from email.message import EmailMessage


def compose_message(event: str, recipient: str, sender: str, instance: str) -> EmailMessage:
    if event not in {"ALERT", "RECOVERED"}:
        raise ValueError("Only ALERT or RECOVERED are eligible for notification")
    message = EmailMessage()
    message["From"] = sender
    message["To"] = recipient
    message["Subject"] = f"[MineFleet] {event} — {instance}"
    message.set_content(
        f"MineFleet operational monitoring event: {event}.\n"
        f"Instance: {instance}\n"
        "Review the monitoring state and diagnostics on the trusted operations host.\n"
        "No operational or personal data is included in this message.\n"
    )
    return message


def send_message(message: EmailMessage, host: str, port: int, username: str, password: str) -> None:
    context = ssl.create_default_context()
    with smtplib.SMTP(host, port, timeout=12) as client:
        client.ehlo()
        client.starttls(context=context)
        client.ehlo()
        client.login(username, password)
        client.send_message(message)


def main() -> int:
    parser = argparse.ArgumentParser(description="Send one ALERT/RECOVERED notification via SMTP STARTTLS")
    parser.add_argument("event", choices=["ALERT", "RECOVERED"])
    args = parser.parse_args()
    required = {
        name: os.environ.get(name, "")
        for name in ("MF_ALERT_SMTP_HOST", "MF_ALERT_SMTP_USERNAME", "MF_ALERT_SMTP_PASSWORD",
                     "MF_ALERT_EMAIL_FROM", "MF_ALERT_EMAIL_TO", "MF_ALERT_INSTANCE")
    }
    if not all(required.values()):
        print("ERROR: SMTP alert configuration incomplete", file=sys.stderr)
        return 3
    try:
        port = int(os.environ.get("MF_ALERT_SMTP_PORT", "587"))
        if not 1 <= port <= 65535:
            raise ValueError("bad port")
        message = compose_message(args.event, required["MF_ALERT_EMAIL_TO"],
                                  required["MF_ALERT_EMAIL_FROM"], required["MF_ALERT_INSTANCE"])
        send_message(message, required["MF_ALERT_SMTP_HOST"], port,
                     required["MF_ALERT_SMTP_USERNAME"], required["MF_ALERT_SMTP_PASSWORD"])
    except (OSError, ValueError, smtplib.SMTPException):
        print("ERROR: SMTP alert notification failed (details withheld)", file=sys.stderr)
        return 2
    print(f"OK: {args.event} notification accepted by SMTP server")
    return 0


if __name__ == "__main__":
    sys.exit(main())
