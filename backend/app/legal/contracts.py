"""Contrat public du module juridique (utilisé par la finance pour les tarifs de contrats de transport)."""

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.legal.router import LegalContract


@dataclass(frozen=True)
class ContractFacts:
    contract_id: uuid.UUID
    site_id: uuid.UUID
    reference: str
    title: str
    contract_type: str
    status: str


def contract_facts(db: Session, contract_id: uuid.UUID) -> ContractFacts | None:
    """Contrat du tenant courant (RLS) réduit aux faits utiles, ou None."""
    row = db.execute(
        select(
            LegalContract.contract_id,
            LegalContract.site_id,
            LegalContract.reference,
            LegalContract.title,
            LegalContract.contract_type,
            LegalContract.status,
        ).where(LegalContract.contract_id == contract_id)
    ).one_or_none()
    return ContractFacts(*row) if row is not None else None


@dataclass(frozen=True)
class BillableContract:
    contract_id: uuid.UUID
    site_id: uuid.UUID
    reference: str
    title: str
    counterparty_name: str


def billable_transport_contracts(db: Session) -> list[BillableContract]:
    """Contrats TRANSPORT approuvés du tenant courant (RLS) : faits exposés à la finance, pas le registre."""
    rows = db.execute(
        select(
            LegalContract.contract_id,
            LegalContract.site_id,
            LegalContract.reference,
            LegalContract.title,
            LegalContract.counterparty_name,
        )
        .where(LegalContract.contract_type == "TRANSPORT", LegalContract.status == "APPROVED")
        .order_by(LegalContract.reference)
    ).all()
    return [BillableContract(*row) for row in rows]


def contract_references(db: Session, contract_ids: set[uuid.UUID]) -> dict[uuid.UUID, str]:
    """Références des contrats du tenant courant (RLS), pour l'affichage des missions rattachées."""
    if not contract_ids:
        return {}
    rows = db.execute(
        select(LegalContract.contract_id, LegalContract.reference).where(
            LegalContract.contract_id.in_(contract_ids)
        )
    ).all()
    return {r[0]: r[1] for r in rows}
