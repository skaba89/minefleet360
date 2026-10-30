"""Consultation des références et magasins de pièces, limitée au tenant et au site."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.authz.dependencies import Authorized, Require
from app.authz.routing import SecuredRoute
from app.core.errors import AppError
from app.core.http import Page, Pagination, StrictModel
from app.maintenance.parts_models import SparePart, SparePartBalance, SparePartStore

router = APIRouter(tags=["pieces"], route_class=SecuredRoute)
Read = Annotated[Authorized, Depends(Require("maintenance.parts.read"))]
Manage = Annotated[Authorized, Depends(Require("maintenance.parts.manage"))]


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


class PartCreate(StrictModel):
    code: str = Field(pattern=r"^[A-Za-z0-9_-]{1,48}$")
    name: str = Field(min_length=1, max_length=200)
    unit: str = Field(default="EACH", pattern=r"^(EACH|LITER|KG|METER)$")


class StoreCreate(StrictModel):
    site_id: uuid.UUID
    code: str = Field(pattern=r"^[A-Za-z0-9_-]{1,48}$")
    name: str = Field(min_length=1, max_length=200)


@router.post("/parts", response_model=PartOut, status_code=status.HTTP_201_CREATED)
def create_part(body: PartCreate, auth: Manage) -> PartOut:
    part = SparePart(tenant_id=auth.tenant_id, code=body.code, name=body.name.strip(), unit=body.unit)
    if not part.name:
        raise AppError("VALIDATION_ERROR")
    auth.db.add(part)
    try:
        auth.db.flush()
    except IntegrityError:
        auth.db.rollback()
        raise AppError("CONFLICT") from None
    output = PartOut.model_validate(part, from_attributes=True)
    auth.db.commit()
    return output


@router.post("/part-stores", response_model=StoreOut, status_code=status.HTTP_201_CREATED)
def create_part_store(body: StoreCreate, auth: Manage) -> StoreOut:
    if not auth.scope.covers_site(body.site_id):
        raise AppError("REFERENCE_NOT_FOUND", details=[{"field": "site_id"}])
    store = SparePartStore(
        tenant_id=auth.tenant_id, site_id=body.site_id, code=body.code, name=body.name.strip()
    )
    if not store.name:
        raise AppError("VALIDATION_ERROR")
    auth.db.add(store)
    try:
        auth.db.flush()
    except IntegrityError:
        auth.db.rollback()
        raise AppError("CONFLICT") from None
    output = StoreOut.model_validate(store, from_attributes=True)
    auth.db.commit()
    return output


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
