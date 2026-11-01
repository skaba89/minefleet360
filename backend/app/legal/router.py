"""Read-only legal and insurance registries, constrained by RBAC and site scope."""

import uuid
from datetime import date
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import Date, Numeric, String, func, select, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Mapped, mapped_column

from app.audit.contracts import record
from app.authz.dependencies import Authorized, Require
from app.authz.routing import SecuredRoute
from app.core.config import get_settings
from app.core.db import Base
from app.core.errors import AppError
from app.core.http import Page, Pagination
from app.legal.authorized_ingestion import ingest_authorized_contract_pdf
from app.legal.clamav_factory import build_contract_malware_scanner
from app.legal.document_registry import record_pending_contract_document
from app.legal.document_upload_policy import DocumentUploadContext, contract_document_upload_allowed
from app.legal.document_validation import MAX_PDF_BYTES
from app.legal.s3_factory import build_private_contract_store
from app.legal.schemas import ContractDraftInput, InsurancePolicyInput

router = APIRouter(tags=["juridique"], route_class=SecuredRoute)
ContractRead = Annotated[Authorized, Depends(Require("legal.contract.read"))]
ContractCreate = Annotated[Authorized, Depends(Require("legal.contract.create"))]
ContractSubmit = Annotated[Authorized, Depends(Require("legal.contract.submit"))]
ContractReview = Annotated[Authorized, Depends(Require("legal.contract.review"))]
InsuranceRead = Annotated[Authorized, Depends(Require("legal.insurance.read"))]
InsuranceCreate = Annotated[Authorized, Depends(Require("legal.insurance.create"))]


class LegalContract(Base):
    __tablename__ = "legal_contract"
    contract_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    site_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    reference: Mapped[str] = mapped_column(String)
    title: Mapped[str] = mapped_column(String)
    contract_type: Mapped[str] = mapped_column(String)
    counterparty_name: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String)
    document_sha256: Mapped[str | None] = mapped_column(String)
    created_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))


class InsurancePolicy(Base):
    __tablename__ = "insurance_policy"
    insurance_policy_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    site_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    policy_number: Mapped[str] = mapped_column(String)
    insurer_name: Mapped[str] = mapped_column(String)
    coverage_type: Mapped[str] = mapped_column(String)
    coverage_start: Mapped[date] = mapped_column(Date)
    coverage_end: Mapped[date] = mapped_column(Date)
    premium_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    currency: Mapped[str] = mapped_column(String)
    contract_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    created_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))


class ContractOut(BaseModel):
    contract_id: uuid.UUID
    site_id: uuid.UUID
    reference: str
    title: str
    contract_type: str
    counterparty_name: str
    status: str
    document_sha256: str | None


class InsuranceOut(BaseModel):
    insurance_policy_id: uuid.UUID
    site_id: uuid.UUID
    policy_number: str
    insurer_name: str
    coverage_type: str
    coverage_start: date
    coverage_end: date
    premium_amount: Decimal | None
    currency: str
    contract_id: uuid.UUID | None


@router.get("/legal-contracts", response_model=Page[ContractOut])
def list_contracts(
    auth: ContractRead, page: Pagination, site_id: uuid.UUID | None = None
) -> Page[ContractOut]:
    if site_id is not None and not auth.scope.covers_site(site_id):
        raise AppError("NOT_FOUND")
    query = select(LegalContract).where(LegalContract.tenant_id == auth.tenant_id)
    if not auth.scope.tenant_wide:
        query = query.where(LegalContract.site_id.in_(auth.scope.site_ids))
    if site_id is not None:
        query = query.where(LegalContract.site_id == site_id)
    total = auth.db.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = auth.db.scalars(
        query.order_by(LegalContract.contract_id.desc()).offset(page.offset).limit(page.page_size)
    ).all()
    return Page(
        items=[ContractOut.model_validate(row, from_attributes=True) for row in rows],
        page=page.page,
        page_size=page.page_size,
        total=total,
    )


@router.get("/insurance-policies", response_model=Page[InsuranceOut])
def list_insurance(
    auth: InsuranceRead, page: Pagination, site_id: uuid.UUID | None = None
) -> Page[InsuranceOut]:
    if site_id is not None and not auth.scope.covers_site(site_id):
        raise AppError("NOT_FOUND")
    query = select(InsurancePolicy).where(InsurancePolicy.tenant_id == auth.tenant_id)
    if not auth.scope.tenant_wide:
        query = query.where(InsurancePolicy.site_id.in_(auth.scope.site_ids))
    if site_id is not None:
        query = query.where(InsurancePolicy.site_id == site_id)
    total = auth.db.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = auth.db.scalars(
        query.order_by(InsurancePolicy.insurance_policy_id.desc()).offset(page.offset).limit(page.page_size)
    ).all()
    return Page(
        items=[InsuranceOut.model_validate(row, from_attributes=True) for row in rows],
        page=page.page,
        page_size=page.page_size,
        total=total,
    )


@router.post("/legal-contracts", response_model=ContractOut, status_code=status.HTTP_201_CREATED)
def create_contract_draft(body: ContractDraftInput, auth: ContractCreate) -> ContractOut:
    """Create a draft only; signing and activation require separate workflows."""
    if not auth.scope.covers_site(body.site_id):
        raise AppError("NOT_FOUND")
    contract = LegalContract(
        tenant_id=auth.tenant_id,
        site_id=body.site_id,
        reference=body.reference,
        title=body.title,
        contract_type=body.contract_type,
        counterparty_name=body.counterparty_name,
        status="DRAFT",
        document_sha256=body.document_sha256,
        created_by=auth.user_id,
    )
    auth.db.add(contract)
    try:
        auth.db.flush()
    except IntegrityError:
        auth.db.rollback()
        raise AppError("CONFLICT") from None
    result = ContractOut.model_validate(contract, from_attributes=True)
    auth.db.commit()
    return result


@router.post("/insurance-policies", response_model=InsuranceOut, status_code=status.HTTP_201_CREATED)
def create_insurance_policy(body: InsurancePolicyInput, auth: InsuranceCreate) -> InsuranceOut:
    if not auth.scope.covers_site(body.site_id):
        raise AppError("NOT_FOUND")
    if body.contract_id is not None:
        linked = auth.db.scalar(
            select(LegalContract.contract_id).where(
                LegalContract.tenant_id == auth.tenant_id,
                LegalContract.contract_id == body.contract_id,
                LegalContract.site_id == body.site_id,
            )
        )
        if linked is None:
            raise AppError("NOT_FOUND")
    policy = InsurancePolicy(
        tenant_id=auth.tenant_id,
        site_id=body.site_id,
        policy_number=body.policy_number,
        insurer_name=body.insurer_name,
        coverage_type=body.coverage_type,
        coverage_start=body.coverage_start,
        coverage_end=body.coverage_end,
        premium_amount=body.premium_amount,
        currency=body.currency,
        contract_id=body.contract_id,
        created_by=auth.user_id,
    )
    auth.db.add(policy)
    try:
        auth.db.flush()
    except IntegrityError:
        auth.db.rollback()
        raise AppError("CONFLICT") from None
    result = InsuranceOut.model_validate(policy, from_attributes=True)
    auth.db.commit()
    return result


@router.post("/legal-contracts/{contract_id}/documents/preflight")
def preflight_contract_document(contract_id: uuid.UUID, auth: ContractCreate) -> dict[str, bool]:
    """Authorize a future upload without accepting, scanning or storing bytes."""
    contract = auth.db.scalar(
        select(LegalContract).where(
            LegalContract.tenant_id == auth.tenant_id,
            LegalContract.contract_id == contract_id,
        )
    )
    if contract is None or not auth.scope.covers_site(contract.site_id):
        raise AppError("NOT_FOUND")
    context = DocumentUploadContext(
        authenticated_tenant_id=auth.tenant_id,
        contract_tenant_id=contract.tenant_id,
        contract_site_id=contract.site_id,
        accessible_site_ids=frozenset(auth.scope.site_ids),
        tenant_wide=auth.scope.tenant_wide,
        contract_status=contract.status,
    )
    if not contract_document_upload_allowed(context):
        raise AppError("CONFLICT")
    return {"allowed": True}


@router.post("/legal-contracts/{contract_id}/documents", status_code=201)
async def upload_contract_document(
    contract_id: uuid.UUID,
    request: Request,
    auth: ContractCreate,
    filename: Annotated[str, Header(alias="X-Filename")],
) -> dict[str, str]:
    """Store scanned PDF metadata as PENDING; never certify a document automatically."""
    contract = auth.db.scalar(
        select(LegalContract).where(
            LegalContract.tenant_id == auth.tenant_id,
            LegalContract.contract_id == contract_id,
        ).with_for_update()
    )
    if contract is None or not auth.scope.covers_site(contract.site_id):
        raise AppError("NOT_FOUND")
    context = DocumentUploadContext(
        authenticated_tenant_id=auth.tenant_id,
        contract_tenant_id=contract.tenant_id,
        contract_site_id=contract.site_id,
        accessible_site_ids=frozenset(auth.scope.site_ids),
        tenant_wide=auth.scope.tenant_wide,
        contract_status=contract.status,
    )
    if not contract_document_upload_allowed(context):
        raise AppError("CONFLICT")
    if request.headers.get("content-type", "").split(";")[0].strip().lower() != "application/pdf":
        raise AppError("VALIDATION_ERROR")
    name = filename.strip()
    if not name or len(name) > 255 or "/" in name or "\\" in name:
        raise AppError("VALIDATION_ERROR")
    chunks = bytearray()
    async for part in request.stream():
        if len(chunks) + len(part) > MAX_PDF_BYTES:
            raise AppError("VALIDATION_ERROR")
        chunks.extend(part)
    settings = get_settings()
    if not settings.legal_malware_scan_enabled or not settings.legal_object_storage_enabled:
        raise AppError("SERVICE_BUSY")
    try:
        document = ingest_authorized_contract_pdf(
            context=context,
            contract_id=contract_id,
            payload=bytes(chunks),
            scanner=build_contract_malware_scanner(settings),
            store=build_private_contract_store(settings),
        )
    except ValueError:
        raise AppError("VALIDATION_ERROR") from None
    except (OSError, RuntimeError):
        raise AppError("SERVICE_BUSY") from None
    document_id = record_pending_contract_document(
        auth.db,
        tenant_id=auth.tenant_id,
        contract_id=contract_id,
        actor_id=auth.user_id,
        original_filename=name,
        document=document,
    )
    record(
        auth.db,
        tenant_id=auth.tenant_id,
        site_id=contract.site_id,
        action="legal.contract.document.upload",
        entity_type="legal_contract_document",
        entity_id=document_id,
        actor_user_id=auth.user_id,
        before=None,
        after={"status": "PENDING"},
        changed_fields=["status"],
    )
    auth.db.commit()
    return {"document_id": str(document_id), "status": "PENDING"}


@router.post("/legal-contracts/{contract_id}/submit", response_model=ContractOut)
def submit_contract(contract_id: uuid.UUID, auth: ContractSubmit) -> ContractOut:
    """Atomically submit a document-backed draft without approving or signing."""
    contract = auth.db.scalar(
        select(LegalContract).where(
            LegalContract.tenant_id == auth.tenant_id,
            LegalContract.contract_id == contract_id,
        )
    )
    if contract is None or not auth.scope.covers_site(contract.site_id):
        raise AppError("NOT_FOUND")
    if contract.status != "DRAFT" or contract.document_sha256 is None:
        raise AppError("CONFLICT")
    # Fail closed until the private upload, scan and verification workflow exists.
    # A caller-supplied digest alone is never evidence of stored, safe bytes.
    evidence = auth.db.scalar(
        text(
            "SELECT EXISTS (SELECT 1 FROM legal_contract_document "
            "WHERE tenant_id = :tenant AND contract_id = :contract_id "
            "AND sha256 = :sha AND status = 'VERIFIED' "
            "AND stored_object_verified = true AND malware_scan_passed = true)"
        ),
        {"tenant": auth.tenant_id, "contract_id": contract_id, "sha": contract.document_sha256},
    )
    if not evidence:
        raise AppError("CONFLICT")
    updated = auth.db.execute(
        text(
            "UPDATE legal_contract SET status = 'PENDING_REVIEW', submitted_at = now() "
            "WHERE tenant_id = :tenant AND contract_id = :contract_id "
            "AND status = 'DRAFT' AND document_sha256 IS NOT NULL "
            "RETURNING contract_id"
        ),
        {"tenant": auth.tenant_id, "contract_id": contract_id},
    ).first()
    if updated is None:
        auth.db.rollback()
        raise AppError("CONFLICT")
    record(
        auth.db,
        tenant_id=auth.tenant_id,
        site_id=contract.site_id,
        action="legal.contract.submit",
        entity_type="legal_contract",
        entity_id=contract_id,
        actor_user_id=auth.user_id,
        before={"status": "DRAFT"},
        after={"status": "PENDING_REVIEW"},
        changed_fields=["status", "submitted_at"],
    )
    auth.db.refresh(contract)
    result = ContractOut.model_validate(contract, from_attributes=True)
    auth.db.commit()
    return result


class ContractDecisionIn(BaseModel):
    action: str
    note: str = Field(min_length=1, max_length=500)


@router.post("/legal-contracts/{contract_id}/decision", response_model=ContractOut)
def decide_contract(
    contract_id: uuid.UUID, auth: ContractReview, body: ContractDecisionIn | None = None
) -> ContractOut:
    """Approve or reject a submitted contract; never act as an electronic signature."""
    contract = auth.db.scalar(
        select(LegalContract).where(
            LegalContract.tenant_id == auth.tenant_id,
            LegalContract.contract_id == contract_id,
        )
    )
    if contract is None or not auth.scope.covers_site(contract.site_id):
        raise AppError("NOT_FOUND")
    if body is None or body.action not in {"APPROVE", "REJECT"} or not body.note.strip():
        raise AppError("VALIDATION_ERROR")
    if contract.created_by == auth.user_id or contract.status != "PENDING_REVIEW":
        raise AppError("CONFLICT")
    target = "APPROVED" if body.action == "APPROVE" else "REJECTED"
    changed = auth.db.execute(
        text(
            "UPDATE legal_contract SET status = :target, reviewed_by = :actor, "
            "reviewed_at = now(), review_note = :note "
            "WHERE tenant_id = :tenant AND contract_id = :contract_id "
            "AND status = 'PENDING_REVIEW' AND created_by <> :actor "
            "AND document_sha256 IS NOT NULL RETURNING contract_id"
        ),
        {
            "target": target,
            "actor": auth.user_id,
            "note": body.note.strip(),
            "tenant": auth.tenant_id,
            "contract_id": contract_id,
        },
    ).first()
    if changed is None:
        auth.db.rollback()
        raise AppError("CONFLICT")
    record(
        auth.db,
        tenant_id=auth.tenant_id,
        site_id=contract.site_id,
        action="legal.contract.review",
        entity_type="legal_contract",
        entity_id=contract_id,
        actor_user_id=auth.user_id,
        before={"status": "PENDING_REVIEW"},
        after={"status": target},
        changed_fields=["status", "reviewed_by", "reviewed_at", "review_note"],
    )
    auth.db.refresh(contract)
    result = ContractOut.model_validate(contract, from_attributes=True)
    auth.db.commit()
    return result
