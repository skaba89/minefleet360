"""Contrat public du module fleet (provisioning de tenant, faits d'éligibilité des affectations)."""

import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date

from sqlalchemy import and_, func, select, text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.fleet.models import (
    Vehicle,
    VehicleCategory,
    VehicleCategoryDocument,
    VehicleCategoryLicense,
    VehicleDocument,
)


@dataclass(frozen=True)
class DocumentFact:
    vehicle_document_id: uuid.UUID
    doc_type: str
    status: str
    valid_from: date | None
    valid_until: date | None


@dataclass(frozen=True)
class VehicleFacts:
    """Ce dont l'affectation a besoin d'un véhicule (RM-030 a, c, d), sans exposer le modèle ORM."""

    vehicle_id: uuid.UUID
    site_id: uuid.UUID
    status: str
    fleet_number: str
    vehicle_category_id: uuid.UUID
    requires_driver: bool
    requires_internal_authorization: bool
    # Vide = aucun permis d'État exigé par le catalogue (RM-022, valeurs fictives à valider : C-07).
    required_license_categories: frozenset[str]
    # Capacité NOMINALE constructeur (kg) : base d'une estimation ou d'une alerte, jamais un tonnage mesuré.
    rated_payload_kg: int | None = None
    # Documents exigés par la catégorie (D-42) et exemplaires de ces types (hors retraits pour erreur).
    required_documents: frozenset[str] = frozenset()
    documents: tuple[DocumentFact, ...] = ()
    # D-42 : document exigé jamais saisi → bloquant (« block ») ou simple avertissement (« warn »).
    missing_documents_block: bool = False
    document_warning_days: int = 45


def vehicle_facts(
    db: Session, vehicle_ids: Iterable[uuid.UUID], *, lock: bool = False
) -> dict[uuid.UUID, VehicleFacts]:
    """Véhicules du tenant courant (RLS). `lock` : FOR NO KEY UPDATE (D-32) contre un changement de statut."""
    ids = sorted(set(vehicle_ids))
    if not ids:
        return {}
    stmt = (
        select(Vehicle, VehicleCategory)
        .join(VehicleCategory, VehicleCategory.vehicle_category_id == Vehicle.vehicle_category_id)
        .where(Vehicle.vehicle_id.in_(ids))
        .order_by(Vehicle.vehicle_id)
    )
    if lock:
        stmt = stmt.with_for_update(key_share=True, of=Vehicle)
    rows = db.execute(stmt).all()
    category_ids = {category.vehicle_category_id for _, category in rows}
    licenses: dict[uuid.UUID, set[str]] = {c: set() for c in category_ids}
    for category_id, code in db.execute(
        select(
            VehicleCategoryLicense.vehicle_category_id, VehicleCategoryLicense.license_category_code
        ).where(VehicleCategoryLicense.vehicle_category_id.in_(category_ids))
    ):
        licenses[category_id].add(code)
    required = required_documents(db, category_ids)
    documents = _documents(db, [vehicle.vehicle_id for vehicle, _ in rows])
    settings = get_settings()
    return {
        vehicle.vehicle_id: VehicleFacts(
            vehicle_id=vehicle.vehicle_id,
            site_id=vehicle.site_id,
            status=vehicle.status,
            fleet_number=vehicle.fleet_number,
            vehicle_category_id=category.vehicle_category_id,
            requires_driver=category.requires_driver,
            requires_internal_authorization=category.requires_internal_authorization,
            required_license_categories=frozenset(licenses[category.vehicle_category_id]),
            rated_payload_kg=vehicle.rated_payload_kg,
            required_documents=required.get(category.vehicle_category_id, frozenset()),
            documents=tuple(
                d
                for d in documents.get(vehicle.vehicle_id, ())
                if d.doc_type in required.get(category.vehicle_category_id, frozenset())
            ),
            missing_documents_block=settings.required_documents_policy == "block",
            document_warning_days=settings.document_warning_days,
        )
        for vehicle, category in rows
    }


def required_documents(db: Session, category_ids: Iterable[uuid.UUID]) -> dict[uuid.UUID, frozenset[str]]:
    """Types de document exigés par catégorie de véhicule (D-42), tenant courant (RLS)."""
    ids = sorted(set(category_ids))
    if not ids:
        return {}
    out: dict[uuid.UUID, set[str]] = {}
    for category_id, doc_type in db.execute(
        select(VehicleCategoryDocument.vehicle_category_id, VehicleCategoryDocument.doc_type).where(
            VehicleCategoryDocument.vehicle_category_id.in_(ids), VehicleCategoryDocument.required.is_(True)
        )
    ):
        out.setdefault(category_id, set()).add(doc_type)
    return {k: frozenset(v) for k, v in out.items()}


# Un document retiré pour erreur de saisie (possible seulement peu après sa création, revue L2C-R-01)
# n'a jamais existé ; les autres retraits laissent le type exigé non satisfait.
ENTRY_ERROR = and_(VehicleDocument.status == "WITHDRAWN", VehicleDocument.status_reason == "ENTRY_ERROR")


def _documents(db: Session, vehicle_ids: list[uuid.UUID]) -> dict[uuid.UUID, list[DocumentFact]]:
    if not vehicle_ids:
        return {}
    out: dict[uuid.UUID, list[DocumentFact]] = {}
    for d in db.execute(
        select(VehicleDocument).where(VehicleDocument.vehicle_id.in_(vehicle_ids), ~ENTRY_ERROR)
    ).scalars():
        out.setdefault(d.vehicle_id, []).append(
            DocumentFact(d.vehicle_document_id, d.doc_type, d.status, d.valid_from, d.valid_until)
        )
    return out


def site_blockers(db: Session, site_id: uuid.UUID, limit: int) -> tuple[int, list[dict[str, str]]]:
    """Ressources non réformées du site courant; identifiants techniques uniquement (RLS)."""
    rows = db.execute(
        select(Vehicle.vehicle_id, func.count().over().label("total"))
        .where(Vehicle.site_id == site_id, Vehicle.status != "RETIRED")
        .order_by(Vehicle.vehicle_id)
        .limit(max(1, limit))
    ).all()
    return (int(rows[0].total) if rows else 0), [
        {"entity_type": "vehicle", "entity_id": str(row.vehicle_id)} for row in rows[: max(0, limit)]
    ]


def seed_tenant_catalog(db: Session, tenant_id: uuid.UUID) -> int:
    """Copie le catalogue de référence global dans le tenant (D-18). Contexte courant = tenant_id."""
    created = db.execute(
        text(
            """
            INSERT INTO vehicle_category (tenant_id, code, label_fr, family, requires_driver,
                requires_internal_authorization, has_odometer, has_hour_meter, is_system)
            SELECT :tid, code, label_fr, family, requires_driver, requires_internal_authorization,
                   has_odometer, has_hour_meter, true
            FROM vehicle_category_template
            """
        ),
        {"tid": str(tenant_id)},
    )
    db.execute(
        text(
            """
            INSERT INTO vehicle_category_license_category
                (tenant_id, vehicle_category_id, license_category_code)
            SELECT vc.tenant_id, vc.vehicle_category_id, l.license_category_code
            FROM vehicle_category vc
            JOIN vehicle_category_template_license l ON l.category_code = vc.code
            WHERE vc.tenant_id = :tid
            """
        ),
        {"tid": str(tenant_id)},
    )
    # Documents exigés par défaut (D-42), modifiables ensuite par l'administrateur du tenant.
    db.execute(
        text(
            """
            INSERT INTO vehicle_category_document (tenant_id, vehicle_category_id, doc_type)
            SELECT vc.tenant_id, vc.vehicle_category_id, t.doc_type
            FROM vehicle_category vc
            JOIN vehicle_category_document_template t ON t.category_code = vc.code
            WHERE vc.tenant_id = :tid
            """
        ),
        {"tid": str(tenant_id)},
    )
    return int(getattr(created, "rowcount", 0) or 0)
