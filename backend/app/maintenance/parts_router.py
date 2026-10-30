"""Consultation des références et magasins de pièces, limitée au tenant et au site."""

import uuid
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError

from app.authz.dependencies import Authorized, Require
from app.authz.routing import SecuredRoute
from app.core.errors import AppError
from app.core.http import Page, Pagination, StrictModel
from app.maintenance.models import WorkOrder
from app.maintenance.parts_models import (
    SparePart,
    SparePartBalance,
    SparePartMovement,
    SparePartReservation,
    SparePartStore,
)

router = APIRouter(tags=["pieces"], route_class=SecuredRoute)
Read = Annotated[Authorized, Depends(Require("maintenance.parts.read"))]
Manage = Annotated[Authorized, Depends(Require("maintenance.parts.manage"))]
Receive = Annotated[Authorized, Depends(Require("maintenance.parts.receive"))]
Issue = Annotated[Authorized, Depends(Require("maintenance.parts.issue"))]
Reserve = Annotated[Authorized, Depends(Require("maintenance.parts.reserve"))]
Release = Annotated[Authorized, Depends(Require("maintenance.parts.release"))]


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


class PartReservationIn(StrictModel):
    work_order_id: uuid.UUID
    spare_part_store_id: uuid.UUID
    spare_part_id: uuid.UUID
    quantity: Decimal = Field(gt=0, max_digits=16, decimal_places=3)
    reference: str = Field(min_length=1, max_length=120)


class PartReservationOut(BaseModel):
    spare_part_reservation_id: uuid.UUID
    work_order_id: uuid.UUID
    spare_part_store_id: uuid.UUID
    spare_part_id: uuid.UUID
    quantity: Decimal
    reference: str
    status: str


@router.post("/part-reservations", response_model=PartReservationOut, status_code=status.HTTP_201_CREATED)
def reserve_part(body: PartReservationIn, auth: Reserve) -> PartReservationOut:
    order = auth.db.scalar(
        select(WorkOrder).where(
            WorkOrder.tenant_id == auth.tenant_id,
            WorkOrder.work_order_id == body.work_order_id,
        )
    )
    store = auth.db.scalar(
        select(SparePartStore).where(
            SparePartStore.tenant_id == auth.tenant_id,
            SparePartStore.spare_part_store_id == body.spare_part_store_id,
        )
    )
    if (
        order is None
        or store is None
        or order.site_id != store.site_id
        or not auth.scope.covers_site(order.site_id)
    ):
        raise AppError("REFERENCE_NOT_FOUND")
    if order.status in {"CLOSED", "REJECTED", "CANCELLED"}:
        raise AppError("CONFLICT")
    part_exists = auth.db.scalar(
        select(SparePart.spare_part_id).where(
            SparePart.tenant_id == auth.tenant_id,
            SparePart.spare_part_id == body.spare_part_id,
        )
    )
    if part_exists is None:
        raise AppError("REFERENCE_NOT_FOUND")
    try:
        # L'UPDATE conditionnel sérialise les réservations concurrentes
        # et ne permet jamais de réserver davantage que le stock disponible.
        updated = auth.db.execute(
            text(
                "UPDATE spare_part_balance SET reserved = reserved + :quantity "
                "WHERE tenant_id = :tenant_id AND site_id = :site_id "
                "AND spare_part_store_id = :store_id AND spare_part_id = :part_id "
                "AND on_hand - reserved >= :quantity RETURNING spare_part_balance_id"
            ),
            {
                "tenant_id": auth.tenant_id,
                "site_id": order.site_id,
                "store_id": body.spare_part_store_id,
                "part_id": body.spare_part_id,
                "quantity": body.quantity,
            },
        ).first()
        if updated is None:
            auth.db.rollback()
            raise AppError("CONFLICT")
        reservation = SparePartReservation(
            tenant_id=auth.tenant_id,
            site_id=order.site_id,
            work_order_id=body.work_order_id,
            spare_part_store_id=body.spare_part_store_id,
            spare_part_id=body.spare_part_id,
            quantity=body.quantity,
            reference=body.reference,
            created_by=auth.user_id,
        )
        auth.db.add(reservation)
        auth.db.flush()
    except IntegrityError:
        auth.db.rollback()
        raise AppError("CONFLICT") from None
    output = PartReservationOut.model_validate(reservation, from_attributes=True)
    auth.db.commit()
    return output


@router.post("/part-reservations/{reservation_id}/release", response_model=PartReservationOut)
def release_part_reservation(reservation_id: uuid.UUID, auth: Release) -> PartReservationOut:
    reservation = auth.db.scalar(
        select(SparePartReservation).where(
            SparePartReservation.tenant_id == auth.tenant_id,
            SparePartReservation.spare_part_reservation_id == reservation_id,
        )
    )
    if reservation is None or not auth.scope.covers_site(reservation.site_id):
        raise AppError("NOT_FOUND")
    if reservation.status != "ACTIVE":
        raise AppError("CONFLICT")
    # Verrou de ligne et transition conditionnelle dans une seule transaction.
    changed = auth.db.execute(
        text(
            "UPDATE spare_part_reservation SET status = 'RELEASED', released_at = now() "
            "WHERE tenant_id = :tenant_id AND spare_part_reservation_id = :reservation_id "
            "AND status = 'ACTIVE' RETURNING spare_part_reservation_id"
        ),
        {"tenant_id": auth.tenant_id, "reservation_id": reservation_id},
    ).first()
    if changed is None:
        auth.db.rollback()
        raise AppError("CONFLICT")
    balance_changed = auth.db.execute(
        text(
            "UPDATE spare_part_balance SET reserved = reserved - :quantity "
            "WHERE tenant_id = :tenant_id AND site_id = :site_id "
            "AND spare_part_store_id = :store_id AND spare_part_id = :part_id "
            "AND reserved >= :quantity RETURNING spare_part_balance_id"
        ),
        {
            "tenant_id": auth.tenant_id,
            "site_id": reservation.site_id,
            "store_id": reservation.spare_part_store_id,
            "part_id": reservation.spare_part_id,
            "quantity": reservation.quantity,
        },
    ).first()
    if balance_changed is None:
        auth.db.rollback()
        raise AppError("CONFLICT")
    auth.db.flush()
    result = PartReservationOut(
        spare_part_reservation_id=reservation_id,
        work_order_id=reservation.work_order_id,
        spare_part_store_id=reservation.spare_part_store_id,
        spare_part_id=reservation.spare_part_id,
        quantity=reservation.quantity,
        reference=reservation.reference,
        status="RELEASED",
    )
    auth.db.commit()
    return result


class PartIssueIn(StrictModel):
    spare_part_store_id: uuid.UUID
    spare_part_id: uuid.UUID
    quantity: Decimal = Field(gt=0, max_digits=16, decimal_places=3)
    reference: str = Field(min_length=1, max_length=120)


class PartIssueOut(BaseModel):
    spare_part_movement_id: uuid.UUID
    spare_part_store_id: uuid.UUID
    spare_part_id: uuid.UUID
    quantity: Decimal
    reference: str


@router.post("/part-movements/issues", response_model=PartIssueOut, status_code=status.HTTP_201_CREATED)
def issue_part(body: PartIssueIn, auth: Issue) -> PartIssueOut:
    store = auth.db.scalar(
        select(SparePartStore).where(
            SparePartStore.tenant_id == auth.tenant_id,
            SparePartStore.spare_part_store_id == body.spare_part_store_id,
        )
    )
    if store is None or not auth.scope.covers_site(store.site_id):
        raise AppError("REFERENCE_NOT_FOUND")
    part = auth.db.scalar(
        select(SparePart).where(
            SparePart.tenant_id == auth.tenant_id,
            SparePart.spare_part_id == body.spare_part_id,
        )
    )
    if part is None:
        raise AppError("REFERENCE_NOT_FOUND")
    try:
        # L'UPDATE conditionnel verrouille le solde pour les sorties concurrentes.
        updated = auth.db.execute(
            text(
                "UPDATE spare_part_balance SET on_hand = on_hand - :quantity "
                "WHERE tenant_id = :tenant_id AND spare_part_store_id = :store_id "
                "AND spare_part_id = :part_id AND on_hand - reserved >= :quantity "
                "RETURNING spare_part_balance_id"
            ),
            {
                "tenant_id": auth.tenant_id,
                "store_id": body.spare_part_store_id,
                "part_id": body.spare_part_id,
                "quantity": body.quantity,
            },
        ).first()
        if updated is None:
            auth.db.rollback()
            raise AppError("CONFLICT")
        movement = SparePartMovement(
            tenant_id=auth.tenant_id,
            site_id=store.site_id,
            spare_part_store_id=body.spare_part_store_id,
            spare_part_id=body.spare_part_id,
            movement_type="ISSUE",
            quantity=body.quantity,
            reference=body.reference,
            recorded_by=auth.user_id,
        )
        auth.db.add(movement)
        auth.db.flush()
    except IntegrityError:
        auth.db.rollback()
        raise AppError("CONFLICT") from None
    output = PartIssueOut.model_validate(movement, from_attributes=True)
    auth.db.commit()
    return output


class PartReceiptIn(StrictModel):
    spare_part_store_id: uuid.UUID
    spare_part_id: uuid.UUID
    quantity: Decimal = Field(gt=0, max_digits=16, decimal_places=3)
    reference: str = Field(min_length=1, max_length=120)


class PartReceiptOut(BaseModel):
    spare_part_movement_id: uuid.UUID
    spare_part_store_id: uuid.UUID
    spare_part_id: uuid.UUID
    quantity: Decimal
    reference: str


@router.post("/part-movements/receipts", response_model=PartReceiptOut, status_code=status.HTTP_201_CREATED)
def receive_part(body: PartReceiptIn, auth: Receive) -> PartReceiptOut:
    store = auth.db.scalar(
        select(SparePartStore).where(
            SparePartStore.tenant_id == auth.tenant_id,
            SparePartStore.spare_part_store_id == body.spare_part_store_id,
        )
    )
    if store is None or not auth.scope.covers_site(store.site_id):
        raise AppError("REFERENCE_NOT_FOUND")
    part = auth.db.scalar(
        select(SparePart).where(
            SparePart.tenant_id == auth.tenant_id,
            SparePart.spare_part_id == body.spare_part_id,
        )
    )
    if part is None:
        raise AppError("REFERENCE_NOT_FOUND")
    existing = auth.db.scalar(
        select(SparePartMovement).where(
            SparePartMovement.tenant_id == auth.tenant_id,
            SparePartMovement.spare_part_store_id == body.spare_part_store_id,
            SparePartMovement.reference == body.reference,
        )
    )
    if existing is not None:
        raise AppError("CONFLICT")
    try:
        # UPSERT atomique : les réceptions concurrentes additionnent leurs quantités.
        auth.db.execute(
            text(
                "INSERT INTO spare_part_balance "
                "(tenant_id, site_id, spare_part_store_id, spare_part_id, on_hand) "
                "VALUES (:tenant_id, :site_id, :store_id, :part_id, :quantity) "
                "ON CONFLICT (tenant_id, spare_part_store_id, spare_part_id) "
                "DO UPDATE SET on_hand = spare_part_balance.on_hand + EXCLUDED.on_hand"
            ),
            {
                "tenant_id": auth.tenant_id,
                "site_id": store.site_id,
                "store_id": body.spare_part_store_id,
                "part_id": body.spare_part_id,
                "quantity": body.quantity,
            },
        )
        movement = SparePartMovement(
            tenant_id=auth.tenant_id,
            site_id=store.site_id,
            spare_part_store_id=body.spare_part_store_id,
            spare_part_id=body.spare_part_id,
            movement_type="RECEIPT",
            quantity=body.quantity,
            reference=body.reference,
            recorded_by=auth.user_id,
        )
        auth.db.add(movement)
        auth.db.flush()
    except IntegrityError:
        auth.db.rollback()
        raise AppError("CONFLICT") from None
    output = PartReceiptOut.model_validate(movement, from_attributes=True)
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
