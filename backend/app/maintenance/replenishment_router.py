"""Create and list procurement drafts without approving orders or changing stock."""

import uuid
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field
from sqlalchemy import Numeric, String, func, select, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Mapped, mapped_column

from app.authz.dependencies import Authorized, Require
from app.authz.routing import SecuredRoute
from app.core.db import Base
from app.core.errors import AppError
from app.core.http import Page, Pagination, StrictModel
from app.maintenance.parts_models import SparePart, SparePartStore

router = APIRouter(tags=["pieces"], route_class=SecuredRoute)
Read = Annotated[Authorized, Depends(Require("maintenance.parts.read"))]
Manage = Annotated[Authorized, Depends(Require("maintenance.parts.manage"))]


class ReplenishmentDraft(Base):
    __tablename__ = "spare_part_replenishment"
    __mapper_args__ = {"eager_defaults": True}

    replenishment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    site_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    spare_part_store_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    spare_part_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(16, 3), nullable=False)
    reference: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, server_default=text("'DRAFT'"))
    created_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)



class DraftCreate(StrictModel):
    spare_part_store_id: uuid.UUID
    spare_part_id: uuid.UUID
    quantity: Decimal = Field(gt=0, max_digits=16, decimal_places=3)
    reference: str = Field(min_length=1, max_length=120)


class DraftOut(BaseModel):
    replenishment_id: uuid.UUID
    site_id: uuid.UUID
    spare_part_store_id: uuid.UUID
    spare_part_id: uuid.UUID
    quantity: Decimal
    reference: str
    status: str


@router.post("/part-replenishments", response_model=DraftOut, status_code=status.HTTP_201_CREATED)
def create_draft(body: DraftCreate, auth: Manage) -> DraftOut:
    store = auth.db.scalar(
        select(SparePartStore).where(
            SparePartStore.tenant_id == auth.tenant_id,
            SparePartStore.spare_part_store_id == body.spare_part_store_id,
        )
    )
    part = auth.db.scalar(
        select(SparePart.spare_part_id).where(
            SparePart.tenant_id == auth.tenant_id, SparePart.spare_part_id == body.spare_part_id
        )
    )
    if store is None or part is None or not auth.scope.covers_site(store.site_id):
        raise AppError("REFERENCE_NOT_FOUND")
    draft = ReplenishmentDraft(
        tenant_id=auth.tenant_id,
        site_id=store.site_id,
        spare_part_store_id=store.spare_part_store_id,
        spare_part_id=body.spare_part_id,
        quantity=body.quantity,
        reference=body.reference.strip(),
        created_by=auth.user_id,
    )
    if not draft.reference:
        raise AppError("VALIDATION_ERROR")
    auth.db.add(draft)
    try:
        auth.db.flush()
    except IntegrityError:
        auth.db.rollback()
        raise AppError("CONFLICT") from None
    result = DraftOut.model_validate(draft, from_attributes=True)
    auth.db.commit()
    return result


@router.get("/part-replenishments", response_model=Page[DraftOut])
def list_drafts(auth: Read, page: Pagination, site_id: uuid.UUID | None = None) -> Page[DraftOut]:
    if site_id is not None and not auth.scope.covers_site(site_id):
        raise AppError("NOT_FOUND")
    query = select(ReplenishmentDraft).where(ReplenishmentDraft.tenant_id == auth.tenant_id)
    if not auth.scope.tenant_wide:
        query = query.where(ReplenishmentDraft.site_id.in_(auth.scope.site_ids))
    if site_id is not None:
        query = query.where(ReplenishmentDraft.site_id == site_id)
    total = auth.db.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = auth.db.scalars(
        query.order_by(ReplenishmentDraft.replenishment_id.desc()).offset(page.offset).limit(page.page_size)
    ).all()
    return Page(
        items=[DraftOut.model_validate(row, from_attributes=True) for row in rows],
        page=page.page,
        page_size=page.page_size,
        total=total,
    )


@router.post("/part-replenishments/{replenishment_id}/submit", response_model=DraftOut)
def submit_draft(replenishment_id: uuid.UUID, auth: Manage) -> DraftOut:
    draft = auth.db.scalar(
        select(ReplenishmentDraft).where(
            ReplenishmentDraft.tenant_id == auth.tenant_id,
            ReplenishmentDraft.replenishment_id == replenishment_id,
        )
    )
    if draft is None or not auth.scope.covers_site(draft.site_id):
        raise AppError("NOT_FOUND")
    changed = auth.db.execute(
        text(
            "UPDATE spare_part_replenishment SET status = 'SUBMITTED', submitted_at = now() "
            "WHERE tenant_id = :tenant_id AND replenishment_id = :replenishment_id "
            "AND status = 'DRAFT' RETURNING replenishment_id"
        ),
        {"tenant_id": auth.tenant_id, "replenishment_id": replenishment_id},
    ).first()
    if changed is None:
        auth.db.rollback()
        raise AppError("CONFLICT")
    result = DraftOut(
        replenishment_id=draft.replenishment_id,
        site_id=draft.site_id,
        spare_part_store_id=draft.spare_part_store_id,
        spare_part_id=draft.spare_part_id,
        quantity=draft.quantity,
        reference=draft.reference,
        status="SUBMITTED",
    )
    auth.db.commit()
    return result
