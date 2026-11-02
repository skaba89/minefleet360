"""HSE-2 : checklists versionnées, inspections, preuves photo, actions sur non-conformités.

Voir docs/LIVRAISON_HSE2.md.

- Un modèle de checklist est versionné : créer un modèle avec un code existant crée la version suivante
  et désactive la précédente ; les éléments d'une version sont immuables (trigger).
- Une inspection est enregistrée en une fois, en ajout seul : réponses figées avec le libellé de la version,
  résultat calculé (FAIL dès qu'un élément critique est non conforme), commentaire obligatoire si non
  conforme.
- Les actions correctives d'une inspection réutilisent la table et le cycle des actions HSE-1.
- Preuves : JPEG/PNG reconnus par signature, ≤ 2 Mo (limite du proxy), antivirus obligatoire, stockage
  privé ; sans antivirus ou stockage configuré, refus explicite (503). Lecture uniquement via l'API, droits
  revérifiés.
"""

import hashlib
import uuid
from collections import defaultdict
from datetime import datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Request, Response, status
from pydantic import AwareDatetime, BaseModel, Field, model_validator
from sqlalchemy import func, select, text, update

from app.audit.contracts import record
from app.authz.dependencies import Authorized, Require
from app.authz.principal import evaluate
from app.authz.routing import SecuredRoute
from app.core.config import Settings, get_settings
from app.core.errors import AppError
from app.core.http import Page, Pagination, StrictModel
from app.core.logging import security_logger
from app.fleet.contracts import vehicle_facts
from app.hse import service
from app.hse.models import (
    HseChecklistTemplate,
    HseCorrectiveAction,
    HseEvidence,
    HseInspection,
    HseInspectionAnswer,
)
from app.hse.schemas import ActionCreate, ActionOut, ActionOwnerOut, EvidenceOut
from app.identity.contracts import display_names, users_with_roles
from app.legal.clamav_factory import build_contract_malware_scanner
from app.legal.malware_scan import MalwareScanner, ScanVerdict
from app.legal.private_storage import PrivateObjectStore
from app.legal.s3_factory import build_private_contract_store
from app.organization.contracts import active_site_in_scope, local_date

router = APIRouter(tags=["hse"], route_class=SecuredRoute)
InspectionRead = Annotated[Authorized, Depends(Require("hse.inspection.read"))]
Perform = Annotated[Authorized, Depends(Require("hse.inspection.perform"))]
ChecklistManage = Annotated[Authorized, Depends(Require("hse.checklist.manage"))]
IncidentManage = Annotated[Authorized, Depends(Require("hse.incident.manage"))]
Report = Annotated[Authorized, Depends(Require("hse.incident.report"))]

TargetType = Literal["PRE_SHIFT", "VEHICLE", "WORK_AREA"]
AnswerResult = Literal["COMPLIANT", "NON_COMPLIANT", "NOT_APPLICABLE"]
MAX_EVIDENCE_BYTES = 2_000_000
MAX_EVIDENCE_PER_INSPECTION = 10
SIGNATURES = {"image/jpeg": (b"\xff\xd8\xff", "jpg"), "image/png": (b"\x89PNG\r\n\x1a\n", "png")}


# --- Schémas -------------------------------------------------------------------------------------------


class ChecklistItem(StrictModel):
    key: str = Field(pattern=r"^[a-z0-9_]{1,48}$")
    label: str = Field(min_length=1, max_length=300)
    critical: bool = False


class TemplateCreate(StrictModel):
    code: str = Field(pattern=r"^[A-Za-z0-9_-]{1,48}$")
    name: str = Field(min_length=3, max_length=200)
    target_type: TargetType
    items: list[ChecklistItem] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def _unique_keys(self) -> "TemplateCreate":
        if len({i.key for i in self.items}) != len(self.items):
            raise ValueError("clés d'éléments en double")
        return self


class TemplateOut(BaseModel):
    hse_checklist_template_id: uuid.UUID
    code: str
    version: int
    name: str
    target_type: TargetType
    items: list[ChecklistItem]
    active: bool
    created_at: datetime


class AnswerIn(StrictModel):
    item_key: str = Field(pattern=r"^[a-z0-9_]{1,48}$")
    result: AnswerResult
    comment: str | None = Field(default=None, max_length=1000)


class InspectionCreate(StrictModel):
    site_id: uuid.UUID
    hse_checklist_template_id: uuid.UUID
    vehicle_id: uuid.UUID | None = None
    area_note: str | None = Field(default=None, max_length=200)
    performed_at: AwareDatetime
    answers: list[AnswerIn] = Field(min_length=1, max_length=100)
    note: str | None = Field(default=None, max_length=2000)


class AnswerOut(BaseModel):
    item_key: str
    label: str
    critical: bool
    result: AnswerResult
    comment: str | None


class InspectionOut(BaseModel):
    hse_inspection_id: uuid.UUID
    number: int
    reference: str
    site_id: uuid.UUID
    hse_checklist_template_id: uuid.UUID
    template_code: str
    template_name: str
    template_version: int
    target_type: TargetType
    vehicle_id: uuid.UUID | None
    vehicle_fleet_number: str | None
    area_note: str | None
    performed_at: datetime
    recorded_at: datetime
    performed_by: uuid.UUID
    performed_by_name: str | None
    result: Literal["PASS", "FAIL"]
    nonconformities: int
    critical_nonconformities: int
    open_actions: int
    note: str | None
    answers: list[AnswerOut] | None = None
    evidence: list[EvidenceOut] | None = None
    actions: list[ActionOut] | None = None


# --- Stockage et antivirus (réutilise les adaptateurs du module juridique) -----------------------------


def build_evidence_store(settings: Settings) -> PrivateObjectStore:
    return build_private_contract_store(settings)


def build_evidence_scanner(settings: Settings) -> MalwareScanner:
    return build_contract_malware_scanner(settings)


def _store_and_scanner() -> tuple[PrivateObjectStore, MalwareScanner]:
    settings = get_settings()
    try:
        return build_evidence_store(settings), build_evidence_scanner(settings)
    except RuntimeError:
        # Pas de preuve acceptée sans stockage privé ET antivirus configurés (fail-closed).
        raise AppError("SERVICE_BUSY") from None


# --- Modèles de checklists -----------------------------------------------------------------------------


def _template_out(t: HseChecklistTemplate) -> TemplateOut:
    return TemplateOut(
        hse_checklist_template_id=t.hse_checklist_template_id,
        code=t.code,
        version=t.version,
        name=t.name,
        target_type=t.target_type,
        items=[ChecklistItem.model_validate(i) for i in t.items],
        active=t.active,
        created_at=t.created_at,
    )


@router.get("/hse/checklist-templates", response_model=list[TemplateOut])
def list_templates(
    auth: Perform, target_type: TargetType | None = None, include_inactive: bool = False
) -> list[TemplateOut]:
    conditions: list[Any] = []
    if target_type is not None:
        conditions.append(HseChecklistTemplate.target_type == target_type)
    if not include_inactive:
        conditions.append(HseChecklistTemplate.active.is_(True))
    rows = auth.db.execute(
        select(HseChecklistTemplate)
        .where(*conditions)
        .order_by(HseChecklistTemplate.code, HseChecklistTemplate.version.desc())
        .limit(500)
    ).scalars()
    return [_template_out(t) for t in rows]


@router.post("/hse/checklist-templates", status_code=status.HTTP_201_CREATED, response_model=TemplateOut)
def create_template(body: TemplateCreate, auth: ChecklistManage) -> TemplateOut:
    db = auth.db
    # Sérialise les créations d'un même code : numéros de version sans trou ni doublon.
    db.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:k, 0))"),
        {"k": f"hse-template:{auth.tenant_id}:{body.code.lower()}"},
    )
    current = db.execute(
        select(func.max(HseChecklistTemplate.version)).where(
            func.lower(HseChecklistTemplate.code) == body.code.lower()
        )
    ).scalar_one()
    db.execute(
        update(HseChecklistTemplate)
        .where(
            func.lower(HseChecklistTemplate.code) == body.code.lower(), HseChecklistTemplate.active.is_(True)
        )
        .values(active=False)
    )
    template = HseChecklistTemplate(
        tenant_id=auth.tenant_id,
        code=body.code,
        version=(current or 0) + 1,
        name=body.name,
        target_type=body.target_type,
        items=[i.model_dump() for i in body.items],
        created_by=auth.user_id,
    )
    db.add(template)
    db.flush()
    record(
        db,
        tenant_id=auth.tenant_id,
        action="hse.checklist.create",
        entity_type="hse_checklist_template",
        entity_id=template.hse_checklist_template_id,
        actor_user_id=auth.user_id,
        after={"code": template.code, "version": template.version, "items": len(body.items)},
    )
    out = _template_out(template)
    db.commit()
    return out


@router.post("/hse/checklist-templates/{template_id}/deactivate", response_model=TemplateOut)
def deactivate_template(template_id: uuid.UUID, auth: ChecklistManage) -> TemplateOut:
    template = auth.db.execute(
        select(HseChecklistTemplate).where(HseChecklistTemplate.hse_checklist_template_id == template_id)
    ).scalar_one_or_none()
    if template is None:
        raise AppError("NOT_FOUND")
    template.active = False
    auth.db.flush()
    record(
        auth.db,
        tenant_id=auth.tenant_id,
        action="hse.checklist.deactivate",
        entity_type="hse_checklist_template",
        entity_id=template.hse_checklist_template_id,
        actor_user_id=auth.user_id,
    )
    out = _template_out(template)
    auth.db.commit()
    return out


# --- Inspections ---------------------------------------------------------------------------------------


def inspections_out(
    auth: Authorized, rows: list[HseInspection], *, detail: bool = False
) -> list[InspectionOut]:
    if not rows:
        return []
    db = auth.db
    ids = [r.hse_inspection_id for r in rows]
    templates = {
        t.hse_checklist_template_id: t
        for t in db.execute(
            select(HseChecklistTemplate).where(
                HseChecklistTemplate.hse_checklist_template_id.in_(
                    {r.hse_checklist_template_id for r in rows}
                )
            )
        ).scalars()
    }
    fleet = vehicle_facts(db, {r.vehicle_id for r in rows if r.vehicle_id})
    names = display_names(db, {r.performed_by for r in rows})
    actions: dict[uuid.UUID, list[HseCorrectiveAction]] = defaultdict(list)
    for a in db.execute(
        select(HseCorrectiveAction)
        .where(HseCorrectiveAction.hse_inspection_id.in_(ids))
        .order_by(HseCorrectiveAction.due_date, HseCorrectiveAction.created_at)
    ).scalars():
        actions[a.hse_inspection_id].append(a)  # type: ignore[index]
    answers: dict[uuid.UUID, list[HseInspectionAnswer]] = defaultdict(list)
    evidence: dict[uuid.UUID, list[HseEvidence]] = defaultdict(list)
    if detail:
        for ans in db.execute(
            select(HseInspectionAnswer)
            .where(HseInspectionAnswer.hse_inspection_id.in_(ids))
            .order_by(HseInspectionAnswer.position)
        ).scalars():
            answers[ans.hse_inspection_id].append(ans)
        for ev in db.execute(
            select(HseEvidence)
            .where(HseEvidence.hse_inspection_id.in_(ids))
            .order_by(HseEvidence.uploaded_at)
        ).scalars():
            evidence[ev.hse_inspection_id].append(ev)  # type: ignore[index]
    out = []
    for r in rows:
        template = templates[r.hse_checklist_template_id]
        data: dict[str, Any] = {
            "hse_inspection_id": r.hse_inspection_id,
            "number": r.number,
            "reference": service.inspection_reference(r.number),
            "site_id": r.site_id,
            "hse_checklist_template_id": r.hse_checklist_template_id,
            "template_code": template.code,
            "template_name": template.name,
            "template_version": template.version,
            "target_type": r.target_type,
            "vehicle_id": r.vehicle_id,
            "vehicle_fleet_number": fleet[r.vehicle_id].fleet_number if r.vehicle_id in fleet else None,
            "area_note": r.area_note,
            "performed_at": r.performed_at,
            "recorded_at": r.recorded_at,
            "performed_by": r.performed_by,
            "performed_by_name": names.get(r.performed_by),
            "result": r.result,
            "nonconformities": r.nonconformities,
            "critical_nonconformities": r.critical_nonconformities,
            "open_actions": sum(1 for a in actions[r.hse_inspection_id] if a.status in ("OPEN", "DONE")),
            "note": r.note,
        }
        if detail:
            data["answers"] = [
                AnswerOut.model_validate(a, from_attributes=True) for a in answers[r.hse_inspection_id]
            ]
            data["evidence"] = [
                EvidenceOut.model_validate(e, from_attributes=True) for e in evidence[r.hse_inspection_id]
            ]
            data["actions"] = service.actions_out(auth, actions[r.hse_inspection_id])
        out.append(InspectionOut(**data))
    return out


def inspection_in_scope(auth: Authorized, inspection_id: uuid.UUID) -> HseInspection:
    row = auth.db.execute(
        select(HseInspection).where(HseInspection.hse_inspection_id == inspection_id)
    ).scalar_one_or_none()
    if row is None or not auth.scope.covers_site(row.site_id):
        security_logger.info(
            "item_not_found", extra={"entity_type": "hse_inspection", "entity_id": str(inspection_id)}
        )
        raise AppError("NOT_FOUND")
    return row


@router.get("/hse/inspections", response_model=Page[InspectionOut], response_model_exclude_unset=True)
def list_inspections(
    auth: InspectionRead,
    page: Pagination,
    site_id: uuid.UUID | None = None,
    result: Literal["PASS", "FAIL"] | None = None,
    target_type: TargetType | None = None,
    vehicle_id: uuid.UUID | None = None,
) -> Page[InspectionOut]:
    if site_id is not None and not auth.scope.covers_site(site_id):
        raise AppError("NOT_FOUND")
    conditions: list[Any] = []
    if not auth.scope.tenant_wide:
        conditions.append(HseInspection.site_id.in_(auth.scope.site_ids))
    if site_id is not None:
        conditions.append(HseInspection.site_id == site_id)
    if result is not None:
        conditions.append(HseInspection.result == result)
    if target_type is not None:
        conditions.append(HseInspection.target_type == target_type)
    if vehicle_id is not None:
        conditions.append(HseInspection.vehicle_id == vehicle_id)
    total = auth.db.execute(select(func.count()).select_from(HseInspection).where(*conditions)).scalar_one()
    rows = list(
        auth.db.execute(
            select(HseInspection)
            .where(*conditions)
            .order_by(HseInspection.performed_at.desc(), HseInspection.number.desc())
            .offset(page.offset)
            .limit(page.page_size)
        ).scalars()
    )
    return Page(items=inspections_out(auth, rows), page=page.page, page_size=page.page_size, total=int(total))


@router.get(
    "/hse/inspections/{hse_inspection_id}", response_model=InspectionOut, response_model_exclude_unset=True
)
def get_inspection(hse_inspection_id: uuid.UUID, auth: InspectionRead) -> InspectionOut:
    return inspections_out(auth, [inspection_in_scope(auth, hse_inspection_id)], detail=True)[0]


def _next_inspection_number(auth: Authorized) -> int:
    return int(
        auth.db.execute(
            text(
                "INSERT INTO hse_counter (tenant_id, last_number, last_inspection_number) VALUES (:t, 0, 1) "
                "ON CONFLICT (tenant_id) DO UPDATE "
                "SET last_inspection_number = hse_counter.last_inspection_number + 1 "
                "RETURNING last_inspection_number"
            ),
            {"t": str(auth.tenant_id)},
        ).scalar_one()
    )


@router.post(
    "/hse/inspections",
    status_code=status.HTTP_201_CREATED,
    response_model=InspectionOut,
    response_model_exclude_unset=True,
)
def create_inspection(body: InspectionCreate, auth: Perform) -> InspectionOut:
    db = auth.db
    if active_site_in_scope(db, auth.scope, body.site_id) is None:
        raise AppError("REFERENCE_NOT_FOUND", details=[{"field": "site_id"}])
    now = auth.clock.now()
    if body.performed_at > now + service.CLOCK_SKEW:
        raise AppError("VALIDATION_ERROR", details=[{"field": "performed_at", "type": "in_future"}])
    template = db.execute(
        select(HseChecklistTemplate).where(
            HseChecklistTemplate.hse_checklist_template_id == body.hse_checklist_template_id
        )
    ).scalar_one_or_none()
    if template is None or not template.active:
        raise AppError("REFERENCE_NOT_FOUND", details=[{"field": "hse_checklist_template_id"}])
    if template.target_type == "VEHICLE" and body.vehicle_id is None:
        raise AppError("VALIDATION_ERROR", details=[{"field": "vehicle_id", "type": "missing"}])
    if template.target_type == "WORK_AREA" and not (body.area_note or "").strip():
        raise AppError("VALIDATION_ERROR", details=[{"field": "area_note", "type": "missing"}])
    if body.vehicle_id is not None:
        facts = vehicle_facts(db, [body.vehicle_id]).get(body.vehicle_id)
        if facts is None or facts.site_id != body.site_id:
            raise AppError("REFERENCE_NOT_FOUND", details=[{"field": "vehicle_id"}])
    items = [ChecklistItem.model_validate(i) for i in template.items]
    given = {a.item_key: a for a in body.answers}
    if len(given) != len(body.answers) or set(given) != {i.key for i in items}:
        # Chaque élément de la version reçoit exactement une réponse : pas d'inspection partielle.
        raise AppError("VALIDATION_ERROR", details=[{"field": "answers", "type": "incomplete"}])
    for a in body.answers:
        if a.result == "NON_COMPLIANT" and not (a.comment or "").strip():
            raise AppError(
                "VALIDATION_ERROR", details=[{"field": f"answers.{a.item_key}.comment", "type": "missing"}]
            )
    nonconform = [i for i in items if given[i.key].result == "NON_COMPLIANT"]
    critical = [i for i in nonconform if i.critical]
    inspection = HseInspection(
        tenant_id=auth.tenant_id,
        site_id=body.site_id,
        hse_checklist_template_id=template.hse_checklist_template_id,
        target_type=template.target_type,
        vehicle_id=body.vehicle_id,
        area_note=(body.area_note or "").strip() or None,
        performed_at=body.performed_at,
        recorded_at=now,
        performed_by=auth.user_id,
        result="FAIL" if critical else "PASS",
        nonconformities=len(nonconform),
        critical_nonconformities=len(critical),
        note=(body.note or "").strip() or None,
        number=_next_inspection_number(auth),
    )
    db.add(inspection)
    db.flush()
    for position, item in enumerate(items):
        answer = given[item.key]
        db.add(
            HseInspectionAnswer(
                tenant_id=auth.tenant_id,
                hse_inspection_id=inspection.hse_inspection_id,
                position=position,
                item_key=item.key,
                label=item.label,
                critical=item.critical,
                result=answer.result,
                comment=(answer.comment or "").strip() or None,
            )
        )
    record(
        db,
        tenant_id=auth.tenant_id,
        action="hse.inspection.create",
        entity_type="hse_inspection",
        entity_id=inspection.hse_inspection_id,
        site_id=inspection.site_id,
        actor_user_id=auth.user_id,
        after={
            "reference": service.inspection_reference(inspection.number),
            "template": f"{template.code} v{template.version}",
            "result": inspection.result,
            "nonconformities": inspection.nonconformities,
        },
    )
    db.flush()
    out = inspections_out(auth, [inspection], detail=True)[0]
    db.commit()
    return out


# --- Actions correctives sur non-conformités -----------------------------------------------------------


@router.get("/hse/inspections/{hse_inspection_id}/action-owners", response_model=list[ActionOwnerOut])
def inspection_action_owners(hse_inspection_id: uuid.UUID, auth: IncidentManage) -> list[ActionOwnerOut]:
    inspection = inspection_in_scope(auth, hse_inspection_id)
    return [
        ActionOwnerOut(user_account_id=user_id, display_name=name)
        for user_id, name in users_with_roles(
            auth.db, service.ACTION_OWNER_ROLES, inspection.site_id, auth.clock.now()
        )
    ]


@router.post(
    "/hse/inspections/{hse_inspection_id}/actions",
    status_code=status.HTTP_201_CREATED,
    response_model=ActionOut,
)
def add_inspection_action(
    hse_inspection_id: uuid.UUID, body: ActionCreate, auth: IncidentManage, response: Response
) -> ActionOut:
    db = auth.db
    inspection = inspection_in_scope(auth, hse_inspection_id)
    if inspection.nonconformities == 0:
        raise AppError("HSE_NO_NONCONFORMITY")
    eligible = {
        u for u, _ in users_with_roles(db, service.ACTION_OWNER_ROLES, inspection.site_id, auth.clock.now())
    }
    if body.owner_user_id not in eligible:
        raise AppError("HSE_OWNER_NOT_ELIGIBLE", details=[{"field": "owner_user_id"}])
    if body.due_date < local_date(db, inspection.site_id, auth.clock.now()):
        raise AppError("VALIDATION_ERROR", details=[{"field": "due_date", "type": "in_past"}])
    action = HseCorrectiveAction(
        tenant_id=auth.tenant_id,
        site_id=inspection.site_id,
        hse_inspection_id=inspection.hse_inspection_id,
        title=body.title,
        description=body.description or None,
        owner_user_id=body.owner_user_id,
        due_date=body.due_date,
        created_by=auth.user_id,
        updated_by=auth.user_id,
    )
    db.add(action)
    db.flush()
    record(
        db,
        tenant_id=auth.tenant_id,
        action="hse.action.create",
        entity_type="hse_corrective_action",
        entity_id=action.hse_corrective_action_id,
        site_id=action.site_id,
        actor_user_id=auth.user_id,
        after={
            "inspection": service.inspection_reference(inspection.number),
            "owner_user_id": str(action.owner_user_id),
            "due_date": action.due_date.isoformat(),
        },
    )
    out = service.actions_out(auth, [action])[0]
    response.headers["ETag"] = f'"{out.row_version}"'
    db.commit()
    return out


# --- Preuves photo -------------------------------------------------------------------------------------


async def ingest_evidence(
    auth: Authorized,
    request: Request,
    *,
    site_id: uuid.UUID,
    parent: dict[str, uuid.UUID],
    parent_reference: str,
) -> EvidenceOut:
    """Contrôle, analyse antivirus, stockage privé et enregistrement d'une photo de preuve (parent unique)."""
    content_type = request.headers.get("content-type", "").split(";")[0].strip().lower()
    if content_type not in SIGNATURES:
        raise AppError("VALIDATION_ERROR", details=[{"field": "Content-Type", "type": "unsupported"}])
    payload = bytearray()
    async for part in request.stream():
        if len(payload) + len(part) > MAX_EVIDENCE_BYTES:
            raise AppError("VALIDATION_ERROR", details=[{"field": "body", "type": "too_large"}])
        payload.extend(part)
    content = bytes(payload)
    signature, extension = SIGNATURES[content_type]
    if not content.startswith(signature):
        # Le type annoncé doit correspondre au contenu réel (pas de fichier déguisé en image).
        raise AppError("VALIDATION_ERROR", details=[{"field": "body", "type": "signature_mismatch"}])
    ((column, parent_id),) = parent.items()
    count = auth.db.execute(
        select(func.count()).select_from(HseEvidence).where(getattr(HseEvidence, column) == parent_id)
    ).scalar_one()
    if count >= MAX_EVIDENCE_PER_INSPECTION:
        raise AppError("VALIDATION_ERROR", details=[{"field": "body", "type": "too_many"}])
    store, scanner = _store_and_scanner()
    # L'adaptateur ClamAV ne lève pas : toute panne réseau ou réponse inattendue vaut ERROR (fail-closed).
    verdict = scanner.scan(content)
    if verdict == ScanVerdict.INFECTED:
        security_logger.warning(
            "evidence_malware_rejected", extra={"entity_type": column, "entity_id": str(parent_id)}
        )
        raise AppError("VALIDATION_ERROR", details=[{"field": "body", "type": "malware"}])
    if verdict != ScanVerdict.CLEAN:
        raise AppError("SERVICE_BUSY")
    digest = hashlib.sha256(content).hexdigest()
    evidence_id = uuid.uuid4()
    key = f"hse/{auth.tenant_id}/{evidence_id}.{extension}"
    try:
        store.put(key=key, content=content, content_type=content_type)
        if hashlib.sha256(store.get(key=key)).hexdigest() != digest:
            raise ValueError("intégrité")
    except Exception as exc:
        raise AppError("SERVICE_BUSY") from exc
    evidence = HseEvidence(
        hse_evidence_id=evidence_id,
        tenant_id=auth.tenant_id,
        site_id=site_id,
        object_key=key,
        content_type=content_type,
        size_bytes=len(content),
        sha256=digest,
        uploaded_by=auth.user_id,
        **parent,
    )
    auth.db.add(evidence)
    auth.db.flush()
    record(
        auth.db,
        tenant_id=auth.tenant_id,
        action="hse.evidence.upload",
        entity_type="hse_evidence",
        entity_id=evidence_id,
        site_id=site_id,
        actor_user_id=auth.user_id,
        after={"parent": parent_reference, "sha256": digest},
    )
    out = EvidenceOut.model_validate(evidence, from_attributes=True)
    auth.db.commit()
    return out


@router.post(
    "/hse/inspections/{hse_inspection_id}/evidence",
    status_code=status.HTTP_201_CREATED,
    response_model=EvidenceOut,
)
async def upload_evidence(hse_inspection_id: uuid.UUID, request: Request, auth: Perform) -> EvidenceOut:
    inspection = inspection_in_scope(auth, hse_inspection_id)
    return await ingest_evidence(
        auth,
        request,
        site_id=inspection.site_id,
        parent={"hse_inspection_id": inspection.hse_inspection_id},
        parent_reference=service.inspection_reference(inspection.number),
    )


@router.post(
    "/hse/incidents/{hse_incident_id}/evidence",
    status_code=status.HTTP_201_CREATED,
    response_model=EvidenceOut,
)
async def upload_incident_evidence(hse_incident_id: uuid.UUID, request: Request, auth: Report) -> EvidenceOut:
    """Photo d'un incident ouvert : par son déclarant, ou par un responsable HSE du site."""
    incident = service.incident_in_scope(auth, hse_incident_id)
    manager = evaluate(auth.principal, "hse.incident.manage")
    if incident.reported_by != auth.user_id and not (
        manager is not None and manager.covers_site(incident.site_id)
    ):
        raise AppError("HSE_NOT_REPORTER")
    if incident.status not in service.OPEN_INCIDENT:
        raise AppError(
            "HSE_INCIDENT_STATE_INVALID", details={"status": incident.status, "action": "ADD_EVIDENCE"}
        )
    return await ingest_evidence(
        auth,
        request,
        site_id=incident.site_id,
        parent={"hse_incident_id": incident.hse_incident_id},
        parent_reference=service.reference(incident.number),
    )


@router.get("/hse/evidence/{hse_evidence_id}/content", response_class=Response)
def evidence_content(hse_evidence_id: uuid.UUID, auth: InspectionRead) -> Response:
    evidence = auth.db.execute(
        select(HseEvidence).where(HseEvidence.hse_evidence_id == hse_evidence_id)
    ).scalar_one_or_none()
    if evidence is None or not auth.scope.covers_site(evidence.site_id):
        raise AppError("NOT_FOUND")
    store, _ = _store_and_scanner()
    try:
        content = store.get(key=evidence.object_key)
    except Exception as exc:
        raise AppError("SERVICE_BUSY") from exc
    if hashlib.sha256(content).hexdigest() != evidence.sha256:
        raise AppError("SERVICE_BUSY")
    return Response(
        content=content,
        media_type=evidence.content_type,
        headers={
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
            "Content-Disposition": f'inline; filename="preuve-{evidence.hse_evidence_id}"',
        },
    )
