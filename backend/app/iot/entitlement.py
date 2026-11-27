"""Read-only provisioning entitlement; absence means disabled.

The entitlement must never be used to suppress existing safety alerts or telemetry.
"""

import uuid

from sqlalchemy import Boolean, select
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.core.db import Base


class IoTEntitlement(Base):
    __tablename__ = "iot_entitlement"

    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    provisioning_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False)


def provisioning_enabled(db: Session, tenant_id: uuid.UUID) -> bool:
    return (
        db.scalar(select(IoTEntitlement.provisioning_enabled).where(IoTEntitlement.tenant_id == tenant_id))
        is True
    )
