"""Port d'envoi d'e-mails (D-28) : SMTP chiffré ou capture privée de développement."""

import json
import logging
import os
import smtplib
import ssl
import stat
import time
import uuid
from dataclasses import dataclass
from email.message import EmailMessage as MimeEmailMessage
from email.utils import parseaddr
from pathlib import Path
from typing import Protocol
from urllib.parse import urlsplit

from app.core.config import Settings

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
    """Capture privée (0700/0600), purgée à chaque envoi; aucun lien symbolique n'est suivi."""

    def __init__(self, directory: str, ttl_seconds: int = 86400) -> None:
        if ttl_seconds <= 0:
            raise ValueError("La durée de conservation des captures doit être positive")
        self.directory = Path(directory)
        self.ttl_seconds = ttl_seconds

    def _directory_fd(self) -> int:
        # Parcours openat de chaque composant : même un parent symbolique est refusé. Les permissions
        # des parents existants restent intactes; seul le répertoire final est rendu privé.
        directory = self.directory.absolute()
        if directory == Path(directory.anchor) or ".." in directory.parts:
            raise ValueError("Le répertoire de capture doit être un répertoire dédié")
        flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
        current = os.open(directory.anchor, flags)
        try:
            for component in directory.parts[1:]:
                try:
                    os.mkdir(component, mode=0o700, dir_fd=current)
                except FileExistsError:
                    pass
                child = os.open(component, flags, dir_fd=current)
                os.close(current)
                current = child
            os.fchmod(current, 0o700)
            return current
        except OSError:
            os.close(current)
            raise

    def _purge(self, directory_fd: int) -> None:
        cutoff = time.time() - self.ttl_seconds
        with os.scandir(directory_fd) as entries:
            for entry in entries:
                name = Path(entry.name)
                if name.suffix != ".json":
                    continue
                try:
                    if str(uuid.UUID(name.stem)) != name.stem:
                        continue
                    info = entry.stat(follow_symlinks=False)
                    if stat.S_ISREG(info.st_mode) and info.st_mtime < cutoff:
                        os.unlink(entry.name, dir_fd=directory_fd)
                except FileNotFoundError:  # un autre worker a déjà purgé ce fichier
                    continue
                except ValueError:  # les autres fichiers ne sont pas des captures de cet adaptateur
                    continue

    def send(self, message: EmailMessage) -> None:
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
        # Ni destinataire ni contenu dans les logs (le corps contient un lien à usage unique).
        logger.info("email_captured", extra={"kind": message.kind})


class SMTPEmailSender:
    """SMTP avec TLS obligatoire et délais bornés; aucune donnée du message n'est journalisée."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def send(self, message: EmailMessage) -> None:
        settings = self.settings
        try:
            mail = MimeEmailMessage()
            mail["From"] = settings.smtp_sender
            mail["To"] = message.to
            mail["Subject"] = message.subject
            mail.set_content(message.body)
            context = ssl.create_default_context()
            connection: smtplib.SMTP
            if settings.smtp_use_ssl:
                connection = smtplib.SMTP_SSL(
                    settings.smtp_host,
                    settings.smtp_port,
                    timeout=settings.smtp_timeout_seconds,
                    context=context,
                )
            else:
                connection = smtplib.SMTP(
                    settings.smtp_host, settings.smtp_port, timeout=settings.smtp_timeout_seconds
                )
            with connection as smtp:
                if not settings.smtp_use_ssl:
                    smtp.ehlo()
                    smtp.starttls(context=context)
                    smtp.ehlo()
                if settings.smtp_username and settings.smtp_password is not None:
                    smtp.login(settings.smtp_username, settings.smtp_password.get_secret_value())
                smtp.send_message(mail)
        except (smtplib.SMTPException, OSError, ValueError):
            # Les exceptions SMTP peuvent inclure destinataire et réponse du serveur : ne pas les relayer.
            raise RuntimeError("Échec du transport email") from None
        logger.info("email_sent", extra={"kind": message.kind})


def build_email_sender(settings: Settings) -> EmailSender:
    """Valide la configuration au démarrage, sans connexion SMTP ni envoi externe."""
    if settings.mail_backend == "capture":
        if settings.env == "production":
            raise ValueError("La capture email est interdite en production; configurer SMTP")
        return FileCaptureEmailSender(settings.mail_capture_dir, settings.mail_capture_ttl_seconds)
    if settings.mail_backend != "smtp":
        raise ValueError("Transport email inconnu")
    sender = parseaddr(settings.smtp_sender)[1]
    if (
        not settings.smtp_host.strip()
        or any(char in settings.smtp_host for char in "\r\n")
        or not sender
        or "@" not in sender
        or any(char in settings.smtp_sender for char in "\r\n")
        or not 1 <= settings.smtp_port <= 65535
        or settings.smtp_timeout_seconds <= 0
    ):
        raise ValueError("Configuration SMTP incomplète ou invalide")
    if bool(settings.smtp_username) != bool(settings.smtp_password):
        raise ValueError("Identifiant et mot de passe SMTP doivent être configurés ensemble")
    if settings.env in ("staging", "production"):
        web = urlsplit(settings.public_web_url)
        if web.scheme != "https" or not web.netloc:
            raise ValueError("MF_PUBLIC_WEB_URL doit être une URL HTTPS pour les emails SMTP")
    return SMTPEmailSender(settings)


class MemoryEmailSender:
    """Adaptateur de test."""

    def __init__(self) -> None:
        self.outbox: list[EmailMessage] = []

    def send(self, message: EmailMessage) -> None:
        self.outbox.append(message)
