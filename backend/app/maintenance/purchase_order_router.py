"""Review-only purchase order drafts linked to approved parts requests."""

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
from app.maintenance.replenishment_router import ReplenishmentDraft

router = APIRouter(tags=["pieces"], route_class=SecuredRoute)
Read = Annotated[Authorized, Depends(Require("maintenance.parts.read"))]
Manage = Annotated[Authorized, Depends(Require("maintenance.parts.manage"))]


class PartsPurchaseOrder(Base):
    __tablename__ = "spare_part_purchase_order"
    __mapper_args__ = {"eager_defaults": True}

    purchase_order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    site_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    replenishment_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    supplier_name: Mapped[str] = mapped_column(String, nullable=False)
    supplier_reference: Mapped[str] = mapped_column(String, nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(16, 3), nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, server_default=text("'DRAFT'"))
    created_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)


class PurchaseOrderCreate(StrictModel):
    replenishment_id: uuid.UUID
    supplier_name: str = Field(min_length=1, max_length=200)
    supplier_reference: str = Field(min_length=1, max_length=120)


class PurchaseOrderOut(BaseModel):
    purchase_order_id: uuid.UUID
    site_id: uuid.UUID
    replenishment_id: uuid.UUID
    supplier_name: str
    supplier_reference: str
    quantity: Decimal
    status: str


@router.post("/parts-purchase-orders", response_model=PurchaseOrderOut, status_code=status.HTTP_201_CREATED)
def create_purchase_draft(body: PurchaseOrderCreate, auth: Manage) -> PurchaseOrderOut:
    request = auth.db.scalar(
        select(ReplenishmentDraft).where(
            ReplenishmentDraft.tenant_id == auth.tenant_id,
            ReplenishmentDraft.replenishment_id == body.replenishment_id,
        )
    )
    if request is None or not auth.scope.covers_site(request.site_id):
        raise AppError("NOT_FOUND")
    if request.status != "APPROVED":
        raise AppError("CONFLICT")
    if not body.supplier_name.strip() or not body.supplier_reference.strip():
        raise AppError("VALIDATION_ERROR")
    order = PartsPurchaseOrder(
        tenant_id=auth.tenant_id,
        site_id=request.site_id,
        replenishment_id=request.replenishment_id,
        supplier_name=body.supplier_name.strip(),
        supplier_reference=body.supplier_reference.strip(),
        quantity=request.quantity,
        created_by=auth.user_id,
    )
    auth.db.add(order)
    try:
        auth.db.flush()
    except IntegrityError:
        auth.db.rollback()
        raise AppError("CONFLICT") from None
    result = PurchaseOrderOut.model_validate(order, from_attributes=True)
    auth.db.commit()
    return result


@router.get("/parts-purchase-orders", response_model=Page[PurchaseOrderOut])
def list_purchase_drafts(
    auth: Read, page: Pagination, site_id: uuid.UUID | None = None
) -> Page[PurchaseOrderOut]:
    if site_id is not None and not auth.scope.covers_site(site_id):
        raise AppError("NOT_FOUND")
    query = select(PartsPurchaseOrder).where(PartsPurchaseOrder.tenant_id == auth.tenant_id)
    if not auth.scope.tenant_wide:
        query = query.where(PartsPurchaseOrder.site_id.in_(auth.scope.site_ids))
    if site_id is not None:
        query = query.where(PartsPurchaseOrder.site_id == site_id)
    total = auth.db.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = auth.db.scalars(
        query.order_by(PartsPurchaseOrder.purchase_order_id.desc()).offset(page.offset).limit(page.page_size)
    ).all()
    return Page(
        items=[PurchaseOrderOut.model_validate(row, from_attributes=True) for row in rows],
        page=page.page,
        page_size=page.page_size,
        total=total,
    )
