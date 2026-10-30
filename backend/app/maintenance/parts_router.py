"""Consultation des références et magasins de pièces, limitée au tenant et au site."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select

from app.authz.dependencies import Authorized, Require
from app.authz.routing import SecuredRoute
from app.core.errors import AppError
from app.core.http import Page, Pagination
from app.maintenance.parts_models import SparePart, SparePartBalance, SparePartStore

router = APIRouter(tags=["pieces"], route_class=SecuredRoute)
Read = Annotated[Authorized, Depends(Require("maintenance.parts.read"))]


class PartOut(BaseModel):
    spare_part_id: uuid.UUID
    code: str
    name: str
    unit: str


class StoreOut(BaseModel):
    spare_part_store_id: uuid.UUID
    site_id: uuid.UUID
    code: str
    name: str


class BalanceOut(BaseModel):
    spare_part_balance_id: uuid.UUID
    site_id: uuid.UUID
    spare_part_store_id: uuid.UUID
    spare_part_id: uuid.UUID
    on_hand: float
    reserved: float
    low_stock_threshold: float


@router.get("/parts", response_model=Page[PartOut])
def list_parts(auth: Read, page: Pagination) -> Page[PartOut]:
    # Les références sont communes au tenant ; un rôle SITE peut voir le catalogue
    # sans recevoir aucune donnée de stock d'autres sites.
    stmt = select(SparePart).where(SparePart.tenant_id == auth.tenant_id)
    total = auth.db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = auth.db.scalars(stmt.order_by(SparePart.code).offset(page.offset).limit(page.page_size)).all()
    return Page(
        items=[PartOut.model_validate(row, from_attributes=True) for row in rows],
        page=page.page,
        page_size=page.page_size,
        total=total,
    )


@router.get("/part-stores", response_model=Page[StoreOut])
def list_part_stores(auth: Read, page: Pagination, site_id: uuid.UUID | None = None) -> Page[StoreOut]:
    if site_id is not None and not auth.scope.covers_site(site_id):
        raise AppError("NOT_FOUND")
    stmt = select(SparePartStore).where(SparePartStore.tenant_id == auth.tenant_id)
    if not auth.scope.tenant_wide:
        stmt = stmt.where(SparePartStore.site_id.in_(auth.scope.site_ids))
    if site_id is not None:
        stmt = stmt.where(SparePartStore.site_id == site_id)
    total = auth.db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = auth.db.scalars(stmt.order_by(SparePartStore.code).offset(page.offset).limit(page.page_size)).all()
    return Page(
        items=[StoreOut.model_validate(row, from_attributes=True) for row in rows],
        page=page.page,
        page_size=page.page_size,
        total=total,
    )


@router.get("/part-balances", response_model=Page[BalanceOut])
def list_part_balances(auth: Read, page: Pagination, site_id: uuid.UUID | None = None) -> Page[BalanceOut]:
    if site_id is not None and not auth.scope.covers_site(site_id):
        raise AppError("NOT_FOUND")
    stmt = select(SparePartBalance).where(SparePartBalance.tenant_id == auth.tenant_id)
    if not auth.scope.tenant_wide:
        stmt = stmt.where(SparePartBalance.site_id.in_(auth.scope.site_ids))
    if site_id is not None:
        stmt = stmt.where(SparePartBalance.site_id == site_id)
    total = auth.db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = auth.db.scalars(
        stmt.order_by(SparePartBalance.spare_part_balance_id).offset(page.offset).limit(page.page_size)
    ).all()
    return Page(
        items=[BalanceOut.model_validate(row, from_attributes=True) for row in rows],
        page=page.page,
        page_size=page.page_size,
        total=total,
    )
