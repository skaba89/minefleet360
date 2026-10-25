"""Colonnes communes des tables modifiables (MODELE_PHYSIQUE_LOT1 §2) : gérées par le serveur (D-19)."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, FetchedValue, Integer, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column


class AuditedColumns:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), server_onupdate=FetchedValue(), nullable=False
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    updated_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    # Incrémenté par le trigger tg_touch ; jamais par l'ORM (version_id_generator=False, DB-24).
    row_version: Mapped[int] = mapped_column(
        Integer, server_default=text("1"), server_onupdate=FetchedValue(), nullable=False
    )
