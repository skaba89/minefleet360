"""Port d'envoi d'e-mails (D-28). En développement : capture locale, aucun envoi externe."""

import json
import logging
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

logger = logging.getLogger("minefleet.email")


@dataclass(frozen=True)
class EmailMessage:
    to: str
    subject: str
    body: str
    kind: str  # INVITATION | PASSWORD_RESET


class EmailSender(Protocol):
    def send(self, message: EmailMessage) -> None: ...


class FileCaptureEmailSender:
    """Écrit chaque message dans un fichier JSON local (jamais commité : var/ est ignoré par Git)."""

    def __init__(self, directory: str) -> None:
        self.directory = Path(directory)

    def send(self, message: EmailMessage) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        path = self.directory / f"{uuid.uuid4()}.json"
        path.write_text(json.dumps(message.__dict__, ensure_ascii=False, indent=2), encoding="utf-8")
        # Ni destinataire ni contenu dans les logs (le corps contient un lien à usage unique).
        logger.info("email_captured", extra={"kind": message.kind})


class MemoryEmailSender:
    """Adaptateur de test."""

    def __init__(self) -> None:
        self.outbox: list[EmailMessage] = []

    def send(self, message: EmailMessage) -> None:
        self.outbox.append(message)
