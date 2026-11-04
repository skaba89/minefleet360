"""Envoi de SMS (notifications d'alertes GPS) : interface commune à tout fournisseur.

Décision du 4 novembre 2026 (docs/GPS_ALERTS.md) : l'utilisateur choisit e-mail et/ou SMS. Aucun
fournisseur SMS payant n'est branché tant que le client ne l'a pas choisi : `capture` (développement,
recette : fichiers privés, comme les e-mails) ou `disabled` (défaut ; obligatoire en production sans
fournisseur). Un fournisseur réel s'ajoutera comme une autre implémentation de `SmsSender`.
"""

import json
import logging
import os
import uuid
from dataclasses import dataclass
from typing import Protocol

from app.core.config import Settings
from app.core.email import FileCaptureEmailSender

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SmsMessage:
    to: str  # format E.164, saisi par l'utilisateur lui-même
    body: str
    kind: str  # GPS_ALERT


class SmsSender(Protocol):
    def send(self, message: SmsMessage) -> None: ...


class FileCaptureSmsSender(FileCaptureEmailSender):
    """Capture privée (0700/0600) des SMS, mêmes garanties que la capture des e-mails."""

    def send(self, message: SmsMessage) -> None:  # type: ignore[override]
        directory_fd = self._directory_fd()
        try:
            self._purge(directory_fd)
            fd = os.open(
                f"{uuid.uuid4()}.json",
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                mode=0o600,
                dir_fd=directory_fd,
            )
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(message.__dict__, handle, ensure_ascii=False, indent=2)
        finally:
            os.close(directory_fd)
        logger.info("sms_captured", extra={"kind": message.kind})


class MemorySmsSender:
    """Adaptateur de test."""

    def __init__(self) -> None:
        self.outbox: list[SmsMessage] = []

    def send(self, message: SmsMessage) -> None:
        self.outbox.append(message)


def build_sms_sender(settings: Settings) -> SmsSender | None:
    """None : SMS indisponible (aucun fournisseur) ; les notifications SMS sont alors marquées en échec."""
    if settings.sms_backend == "disabled":
        return None
    if settings.env == "production":
        raise ValueError("Capture SMS interdite en production : configurer un fournisseur ou 'disabled'")
    return FileCaptureSmsSender(settings.sms_capture_dir, settings.mail_capture_ttl_seconds)
