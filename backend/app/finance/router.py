"""Tarifs des contrats de transport (contrôle de gestion, tranche 2a, docs/CONTROLE_GESTION.md).

Un tarif ne s'applique qu'à un contrat juridique de type TRANSPORT **approuvé** (circuit quatre-yeux
existant), sur un site couvert par l'appelant. Versions datées en ajout seul : la version en vigueur à une
date est la plus récente dont `valid_from` ≤ date. Aucun revenu n'est calculé ici (tranche 3).
"""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.audit.contracts import record
from app.authz.dependencies import Authorized, Require
from app.authz.routing import SecuredRoute
from app.core.errors import AppError
from app.core.http import StrictModel
from app.finance.models import ContractTariff
from app.legal.contracts import ContractFacts, billable_transport_contracts, contract_facts

router = APIRouter(tags=["finance"], route_class=SecuredRoute)
TariffManage = Annotated[Authorized, Depends(Require("finance.tariff.manage"))]
TariffRead = Annotated[Authorized, Depends(Require("finance.tariff.read"))]
Basis = Literal["TONNE", "HOUR", "KM", "MISSION"]


class TariffIn(StrictModel):
    contract_id: uuid.UUID
    basis: Basis
    unit_price: Decimal = Field(gt=0, max_digits=18, decimal_places=4)
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    valid_from: date
    note: str | None = Field(default=None, max_length=500)


class TariffOut(BaseModel):
    contract_tariff_id: uuid.UUID
    contract_id: uuid.UUID
    basis: Basis
    unit_price: Decimal
    currency: str
    valid_from: date
    note: str | None
    created_at: datetime
    # Version en vigueur aujourd'hui (la plus récente dont valid_from ≤ aujourd'hui).
    current: bool = False


class BillableContractOut(BaseModel):
    contract_id: uuid.UUID
    site_id: uuid.UUID
    reference: str
    title: str
    counterparty_name: str


def _billable_contract(auth: Authorized, contract_id: uuid.UUID) -> ContractFacts:
    facts = contract_facts(auth.db, contract_id)
    if facts is None or not auth.scope.covers_site(facts.site_id):
        raise AppError("REFERENCE_NOT_FOUND", details=[{"field": "contract_id"}])
    if facts.contract_type != "TRANSPORT":
        raise AppError("VALIDATION_ERROR", details=[{"field": "contract_id", "type": "not_transport"}])
    if facts.status != "APPROVED":
        raise AppError("VALIDATION_ERROR", details=[{"field": "contract_id", "type": "not_approved"}])
    return facts


def _out(tariff: ContractTariff, current_id: uuid.UUID | None) -> TariffOut:
    return TariffOut(
        contract_tariff_id=tariff.contract_tariff_id,
        contract_id=tariff.contract_id,
        basis=tariff.basis,
        unit_price=tariff.unit_price,
        currency=tariff.currency,
        valid_from=tariff.valid_from,
        note=tariff.note,
        created_at=tariff.created_at,
        current=tariff.contract_tariff_id == current_id,
    )


@router.post("/contract-tariffs", status_code=status.HTTP_201_CREATED, response_model=TariffOut)
def create_tariff(body: TariffIn, auth: TariffManage) -> TariffOut:
    facts = _billable_contract(auth, body.contract_id)
    tariff = ContractTariff(
        tenant_id=auth.tenant_id,
        contract_id=body.contract_id,
        basis=body.basis,
        unit_price=body.unit_price,
        currency=body.currency,
        valid_from=body.valid_from,
        note=body.note,
        created_by=auth.user_id,
    )
    auth.db.add(tariff)
    try:
        auth.db.flush()
    except IntegrityError:
        auth.db.rollback()
        raise AppError("CONFLICT") from None  # une version existe déjà à cette date d'effet
    record(
        auth.db,
        tenant_id=auth.tenant_id,
        action="finance.tariff.create",
        entity_type="contract_tariff",
        entity_id=tariff.contract_tariff_id,
        site_id=facts.site_id,
        actor_user_id=auth.user_id,
        after={
            "contract": facts.reference,
            "basis": body.basis,
            "unit_price": str(body.unit_price),
            "currency": body.currency,
            "valid_from": body.valid_from.isoformat(),
        },
    )
    out = _out(tariff, None)
    auth.db.commit()
    return out


@router.get("/contract-tariffs", response_model=list[TariffOut])
def list_tariffs(
    auth: TariffRead, contract_id: Annotated[uuid.UUID | None, Query()] = None
) -> list[TariffOut]:
    """Versions de tarifs (plus récente d'abord) d'un contrat, ou de tous les contrats des sites couverts.

    `current` marque, pour chaque contrat, la version en vigueur aujourd'hui.
    """
    stmt = select(ContractTariff).order_by(ContractTariff.contract_id, ContractTariff.valid_from.desc())
    if contract_id is not None:
        facts = contract_facts(auth.db, contract_id)
        if facts is None or not auth.scope.covers_site(facts.site_id):
            raise AppError("NOT_FOUND")
        stmt = stmt.where(ContractTariff.contract_id == contract_id)
    rows = list(auth.db.execute(stmt).scalars())
    visible: dict[uuid.UUID, bool] = {}
    for tariff in rows:
        if tariff.contract_id not in visible:
            facts = contract_facts(auth.db, tariff.contract_id)
            visible[tariff.contract_id] = facts is not None and auth.scope.covers_site(facts.site_id)
    today = auth.clock.now().date()
    current: dict[uuid.UUID, uuid.UUID] = {}
    for tariff in rows:
        if tariff.valid_from <= today:
            current.setdefault(tariff.contract_id, tariff.contract_tariff_id)
    return [_out(t, current.get(t.contract_id)) for t in rows if visible[t.contract_id]]


@router.get("/contract-tariffs/contracts", response_model=list[BillableContractOut])
def list_billable_contracts(auth: TariffRead) -> list[BillableContractOut]:
    """Contrats de transport approuvés des sites couverts (saisie des tarifs, sans le registre)."""
    return [
        BillableContractOut(**vars(c))
        for c in billable_transport_contracts(auth.db)
        if auth.scope.covers_site(c.site_id)
    ]
