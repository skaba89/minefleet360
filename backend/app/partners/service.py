"""Référentiel des sous-traitants (lot 1 de docs/MODELE_SECURITE_SOUS_TRAITANTS.md, option B).

Données du donneur d'ordre : lues et gérées par ses rôles internes seulement. Aucun compte externe ici ;
chaque écriture est journalisée (création, modification, changement de statut motivé).
"""

import uuid

from sqlalchemy import select

from app.audit.contracts import record
from app.authz.dependencies import Authorized
from app.core.errors import AppError
from app.core.http import check_version
from app.partners.models import Subcontractor
from app.partners.schemas import SubcontractorCreate, SubcontractorStatus, SubcontractorUpdate


def list_subcontractors(
    auth: Authorized, *, status: SubcontractorStatus | None = None
) -> list[Subcontractor]:
    stmt = select(Subcontractor).order_by(Subcontractor.code)
    if status is not None:
        stmt = stmt.where(Subcontractor.status == status)
    return list(auth.db.execute(stmt).scalars().all())


def create_subcontractor(auth: Authorized, body: SubcontractorCreate) -> Subcontractor:
    db = auth.db
    subcontractor = Subcontractor(
        tenant_id=auth.tenant_id,
        code=body.code,
        legal_name=body.legal_name.strip(),
        registration_number=body.registration_number,
        tax_id=body.tax_id,
        country_code=body.country_code,
        notes=body.notes,
        created_by=auth.user_id,
        updated_by=auth.user_id,
    )
    db.add(subcontractor)
    db.flush()
    record(
        db,
        tenant_id=auth.tenant_id,
        action="subcontractor.create",
        entity_type="subcontractor",
        entity_id=subcontractor.subcontractor_id,
        actor_user_id=auth.user_id,
        after={"code": subcontractor.code, "legal_name": subcontractor.legal_name},
    )
    db.commit()
    return subcontractor


def update_subcontractor(
    auth: Authorized, subcontractor_id: uuid.UUID, body: SubcontractorUpdate, version: int
) -> Subcontractor:
    db = auth.db
    subcontractor = db.execute(
        select(Subcontractor)
        .where(Subcontractor.subcontractor_id == subcontractor_id)
        .with_for_update(key_share=True)
    ).scalar_one_or_none()
    if subcontractor is None:
        raise AppError("NOT_FOUND")
    check_version(version, subcontractor.row_version)
    fields = sorted(f for f in body.model_fields_set if getattr(body, f) is not None)
    if body.status == "ACTIVE":
        fields = sorted({*fields, "status_reason"})  # réactivation : le motif précédent est effacé
    before = {f: getattr(subcontractor, f) for f in fields}
    for name in fields:
        value = getattr(body, name)
        setattr(
            subcontractor, name, value.strip() if isinstance(value, str) and name == "legal_name" else value
        )
    subcontractor.updated_by = auth.user_id
    db.flush()
    changed = tuple(f for f in fields if before[f] != getattr(subcontractor, f))
    record(
        db,
        tenant_id=auth.tenant_id,
        action="subcontractor.status_change" if "status" in changed else "subcontractor.update",
        entity_type="subcontractor",
        entity_id=subcontractor.subcontractor_id,
        actor_user_id=auth.user_id,
        reason=subcontractor.status_reason if "status" in changed else None,
        before={f: before[f] for f in changed},
        after={f: getattr(subcontractor, f) for f in changed},
        changed_fields=changed,
    )
    db.commit()
    return subcontractor
