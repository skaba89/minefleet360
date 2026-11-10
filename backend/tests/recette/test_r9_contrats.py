"""Recette R9 — contrats, documents et assurance (docs/RECETTE.md §R9).

Parcours : contrat incomplet (soumission refusée, SHA déclaré sans preuve refusé) → prévol du dépôt
(preflight, RBAC strict) → dépôt de documents : cas non conformes refusés sans rien stocker (type
mime, nom de fichier, PDF invalide, PDF tronqué, virus simulé) puis dépôt conforme dont le SHA-256
a été déclaré à la création → vérification par un tiers (le déposant ne se vérifie pas) →
soumission puis décision en quatre-yeux (le créateur ne décide pas) → réconciliation du stockage
légal cohérente, qui détecte une clé orpheline → police d'assurance liée au contrat (dates
inversées, lien étranger et doublon refusés) → les échéances d'assurance remontent : polices
EXPIRING/EXPIRED via /insurance-policies/expiring et document INSURANCE du véhicule via
/vehicle-documents → chaque écriture clé est auditée. Les adaptateurs de scan et de stockage privé
sont simulés en mémoire (même principe que l'adaptateur GPS simulé de R7) ; sans eux l'API répond
fail-closed 503, comportement déjà couvert par les tests du module.
"""

import hashlib
import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.legal import router as legal_router
from app.legal.malware_scan import ScanVerdict
from tests.conftest import API, Api

PDF = b"%PDF-1.7\n1 0 obj\nendobj\n%%EOF\n"


class _FakeScanner:
    def __init__(self) -> None:
        self.verdict = ScanVerdict.CLEAN

    def scan(self, content: bytes) -> ScanVerdict:
        return ScanVerdict.INFECTED if b"EICAR" in content else self.verdict


class _FakeStore:
    """Magasin privé en mémoire ; expose client/bucket comme le store S3 pour la réconciliation."""

    def __init__(self) -> None:
        self.saved: dict[str, bytes] = {}
        self.bucket = "private-legal-test"
        self.client = self

    def put(self, *, key: str, content: bytes, content_type: str = "application/pdf") -> None:
        self.saved[key] = content

    def get(self, *, key: str) -> bytes:
        return self.saved[key]

    def list_objects_v2(self, *, Bucket: str, Prefix: str, MaxKeys: int, **_: object) -> dict:  # type: ignore[type-arg]
        return {
            "Contents": [{"Key": k} for k in sorted(self.saved) if k.startswith(Prefix)],
            "IsTruncated": False,
        }


@pytest.fixture
def legal_adapters(monkeypatch: pytest.MonkeyPatch) -> _FakeStore:
    """Branche les adaptateurs simulés dans le module router (noms résolus à l'import)."""
    store = _FakeStore()
    monkeypatch.setattr(
        legal_router,
        "get_settings",
        lambda: SimpleNamespace(legal_malware_scan_enabled=True, legal_object_storage_enabled=True),
    )
    monkeypatch.setattr(legal_router, "build_contract_malware_scanner", lambda _s: _FakeScanner())
    monkeypatch.setattr(legal_router, "build_private_contract_store", lambda _s: store)
    return store


def test_r9_contrats_documents_assurance_bout_en_bout(
    client: TestClient, api: Api, legal_adapters: _FakeStore
) -> None:
    t = api.tenant(sites=("MINE",))
    admin = t.admin.headers  # TENANT_ADMIN : create/submit/review + fleet.document.manage
    reviewer = api.user(t, "DIRECTION").headers  # legal.contract.review, distinct du créateur
    finance = api.user(t, "FINANCE").headers  # legal.insurance.create/read + fleet.document.read
    conducteur = api.user(t, "DRIVER", "SITE", "MINE")  # aucun droit juridique
    outsider = api.tenant().admin.headers
    site = str(t.sites["MINE"])
    today = datetime.now(UTC).date()
    pdf_headers = {"Content-Type": "application/pdf", "X-Filename": "contrat-transport.pdf"}

    # --- Contrat incomplet : la soumission est refusée ---------------------------------------------
    incomplet = client.post(
        f"{API}/legal-contracts",
        headers=admin,
        json={
            "site_id": site,
            "reference": "R9-C1",
            "title": "Contrat de transport incomplet",
            "contract_type": "TRANSPORT",
            "counterparty_name": "Transporteur Fictif SARL",
        },
    )
    assert incomplet.status_code == 201 and incomplet.json()["status"] == "DRAFT"
    cid_incomplet = incomplet.json()["contract_id"]
    assert client.post(f"{API}/legal-contracts/{cid_incomplet}/submit", headers=admin).status_code == 409
    # Un SHA-256 déclaré sans preuve vérifiée ne suffit pas non plus.
    declare = client.post(
        f"{API}/legal-contracts",
        headers=admin,
        json={
            "site_id": site,
            "reference": "R9-C2",
            "title": "Contrat sans preuve de document",
            "contract_type": "SUPPLIER",
            "counterparty_name": "Fournisseur Fictif",
            "document_sha256": "a" * 64,
        },
    )
    assert declare.status_code == 201, declare.text
    assert (
        client.post(
            f"{API}/legal-contracts/{declare.json()['contract_id']}/submit", headers=admin
        ).status_code
        == 409
    )
    doublon = client.post(
        f"{API}/legal-contracts",
        headers=admin,
        json={
            "site_id": site,
            "reference": "R9-C1",
            "title": "Référence déjà prise",
            "contract_type": "OTHER",
            "counterparty_name": "Autre Contrepartie",
        },
    )
    assert (doublon.status_code, doublon.json()["code"]) == (409, "CONFLICT")
    assert (
        client.post(
            f"{API}/legal-contracts",
            headers=admin,
            json={
                "site_id": site,
                "reference": "R9-C4",
                "title": "Champ non déclaré",
                "contract_type": "OTHER",
                "counterparty_name": "Contrepartie",
                "tenant_id": str(t.tenant_id),
            },
        ).status_code
        == 422
    )

    # --- Prévol du dépôt (preflight) ---------------------------------------------------------------
    pre = f"{API}/legal-contracts/{cid_incomplet}/documents/preflight"
    assert client.post(pre, headers=admin).json() == {"allowed": True}
    assert client.post(pre, headers=conducteur.headers).status_code == 403
    assert client.post(pre, headers=outsider).status_code == 404

    # --- Dépôt : cas non conformes refusés, aucun objet stocké -------------------------------------
    upload = f"{API}/legal-contracts/{cid_incomplet}/documents"
    assert (
        client.post(
            upload,
            headers={**admin, "Content-Type": "text/plain", "X-Filename": "contrat.pdf"},
            content=PDF,
        ).status_code
        == 422
    )  # type mime exigé : application/pdf
    assert (
        client.post(upload, headers={**admin, "Content-Type": "application/pdf"}, content=PDF).status_code
        == 422
    )
    assert (
        client.post(
            upload, headers={**admin, **pdf_headers, "X-Filename": "a/b.pdf"}, content=PDF
        ).status_code
        == 422
    )  # nom de fichier sans séparateur
    assert client.post(upload, headers={**admin, **pdf_headers}, content=b"not a PDF").status_code == 422
    assert (
        client.post(upload, headers={**admin, **pdf_headers}, content=b"%PDF-1.7 sans fin").status_code == 422
    )
    infecte = client.post(
        upload, headers={**admin, **pdf_headers}, content=PDF + b"EICAR-STANDARD-ANTIVIRUS-TEST-FILE"
    )
    assert (infecte.status_code, infecte.json()["code"]) == (422, "VALIDATION_ERROR")
    assert legal_adapters.saved == {}  # les refus ne laissent aucune trace dans le stockage

    # --- Contrat complet : dépôt conforme du PDF dont le SHA a été déclaré -------------------------
    digest = hashlib.sha256(PDF).hexdigest()
    contrat = client.post(
        f"{API}/legal-contracts",
        headers=admin,
        json={
            "site_id": site,
            "reference": "R9-C3",
            "title": "Contrat de transport minier",
            "contract_type": "TRANSPORT",
            "counterparty_name": "Transporteur Fictif SARL",
            "document_sha256": digest,
        },
    )
    assert contrat.status_code == 201, contrat.text
    cid = contrat.json()["contract_id"]
    depot = client.post(
        f"{API}/legal-contracts/{cid}/documents", headers={**admin, **pdf_headers}, content=PDF
    )
    assert depot.status_code == 201 and depot.json()["status"] == "PENDING"
    doc_id = depot.json()["document_id"]

    # --- Vérification par un tiers (le déposant ne se vérifie pas) ---------------------------------
    verifie = f"{API}/legal-contracts/{cid}/documents/{doc_id}/verify"
    assert client.post(verifie, headers=admin).status_code == 404
    fait = client.post(verifie, headers=reviewer)
    assert fait.status_code == 200 and fait.json()["status"] == "VERIFIED"
    assert client.post(verifie, headers=reviewer).status_code == 404  # déjà vérifié : plus PENDING

    # --- Soumission puis décision en quatre-yeux ---------------------------------------------------
    soumission = client.post(f"{API}/legal-contracts/{cid}/submit", headers=admin)
    assert soumission.status_code == 200 and soumission.json()["status"] == "PENDING_REVIEW"
    assert client.post(f"{API}/legal-contracts/{cid}/submit", headers=admin).status_code == 409
    assert (
        client.post(
            f"{API}/legal-contracts/{cid}/documents", headers={**admin, **pdf_headers}, content=PDF
        ).status_code
        == 409
    )  # le contrat n'est plus DRAFT
    decision = f"{API}/legal-contracts/{cid}/decision"
    assert client.post(decision, headers=admin, json={"action": "APPROVE", "note": "auto"}).status_code == 409
    assert client.post(decision, headers=reviewer, json={"action": "RESET", "note": "x"}).status_code == 422
    assert (
        client.post(decision, headers=reviewer, json={"action": "APPROVE", "note": "   "}).status_code == 422
    )
    approuve = client.post(
        decision, headers=reviewer, json={"action": "APPROVE", "note": "Dossier conforme R9"}
    )
    assert approuve.status_code == 200 and approuve.json()["status"] == "APPROVED"
    assert (
        client.post(decision, headers=reviewer, json={"action": "REJECT", "note": "replay"}).status_code
        == 409
    )

    # --- Réconciliation du stockage légal ----------------------------------------------------------
    # Les grants de review sont TENANT_ADMIN/DIRECTION [TENANT] : un lecteur site-scoped est
    # refusé par le RBAC (403) avant même le contrôle de portée de la réconciliation.
    ops_site = api.user(t, "OPS_MANAGER", "SITE", "MINE")
    refus_recon = client.get(f"{API}/legal-contracts/storage-reconciliation", headers=ops_site.headers)
    assert (refus_recon.status_code, refus_recon.json()["code"]) == (403, "PERMISSION_DENIED")
    reconcilie = client.get(f"{API}/legal-contracts/storage-reconciliation", headers=reviewer)
    assert reconcilie.status_code == 200
    assert reconcilie.json() == {"orphan_count": 0, "missing_count": 0, "consistent": True}
    legal_adapters.saved[f"legal/{t.tenant_id}/orpheline.pdf"] = PDF
    orpheline = client.get(f"{API}/legal-contracts/storage-reconciliation", headers=reviewer).json()
    assert (orpheline["orphan_count"], orpheline["consistent"]) == (1, False)

    # --- Police d'assurance liée au contrat --------------------------------------------------------
    police = client.post(
        f"{API}/insurance-policies",
        headers=finance,
        json={
            "site_id": site,
            "policy_number": "POL-R9-001",
            "insurer_name": "Assureur Fictif SA",
            "coverage_type": "FLEET",
            "coverage_start": today.isoformat(),
            "coverage_end": (today + timedelta(days=10)).isoformat(),
            "premium_amount": "1500000",
            "currency": "GNF",
            "contract_id": cid,
        },
    )
    assert police.status_code == 201, police.text
    assert police.json()["contract_id"] == cid and police.json()["currency"] == "GNF"
    assert (
        client.post(
            f"{API}/insurance-policies",
            headers=finance,
            json={
                "site_id": site,
                "policy_number": "POL-R9-BAD",
                "insurer_name": "Assureur Fictif SA",
                "coverage_type": "FLEET",
                "coverage_start": today.isoformat(),
                "coverage_end": (today - timedelta(days=1)).isoformat(),
            },
        ).status_code
        == 422
    )  # dates inversées
    etrangere = client.post(
        f"{API}/insurance-policies",
        headers=finance,
        json={
            "site_id": site,
            "policy_number": "POL-R9-BAD",
            "insurer_name": "Assureur Fictif SA",
            "coverage_type": "FLEET",
            "coverage_start": today.isoformat(),
            "coverage_end": (today + timedelta(days=10)).isoformat(),
            "contract_id": str(uuid.uuid4()),
        },
    )
    assert etrangere.status_code == 404  # contrat inexistant ou d'une autre société
    assert (
        client.post(
            f"{API}/insurance-policies",
            headers=finance,
            json={
                "site_id": site,
                "policy_number": "POL-R9-001",
                "insurer_name": "Assureur Fictif SA",
                "coverage_type": "FLEET",
                "coverage_start": today.isoformat(),
                "coverage_end": (today + timedelta(days=10)).isoformat(),
            },
        ).status_code
        == 409
    )  # numéro déjà pris
    for numero, debut, fin in (
        ("POL-R9-002", today - timedelta(days=365), today - timedelta(days=2)),
        ("POL-R9-003", today - timedelta(days=100), today + timedelta(days=200)),
    ):
        autre = client.post(
            f"{API}/insurance-policies",
            headers=finance,
            json={
                "site_id": site,
                "policy_number": numero,
                "insurer_name": "Assureur Fictif SA",
                "coverage_type": "CARGO",
                "coverage_start": debut.isoformat(),
                "coverage_end": fin.isoformat(),
            },
        )
        assert autre.status_code == 201, autre.text
    liste = client.get(f"{API}/insurance-policies", headers=finance)
    assert liste.status_code == 200 and liste.json()["total"] == 3

    # --- Échéances d'assurance : EXPIRING et EXPIRED remontent, la couverture lointaine non --------
    echeances = client.get(f"{API}/insurance-policies/expiring", headers=finance, params={"within_days": 45})
    assert echeances.status_code == 200, echeances.text
    par_numero = {p["policy_number"]: p["validity"] for p in echeances.json()}
    assert par_numero["POL-R9-001"] == "EXPIRING" and par_numero["POL-R9-002"] == "EXPIRED"
    assert "POL-R9-003" not in par_numero
    assert (
        client.get(
            f"{API}/insurance-policies/expiring", headers=finance, params={"within_days": -1}
        ).status_code
        == 422
    )
    assert (
        client.get(
            f"{API}/insurance-policies/expiring", headers=finance, params={"within_days": 366}
        ).status_code
        == 422
    )

    # --- Échéance d'assurance d'un véhicule (document) ---------------------------------------------
    category = next(
        c
        for c in client.get(f"{API}/vehicle-categories", headers=admin).json()
        if c["code"] == "RIGID_DUMP_TRUCK"
    )
    vehicule = client.post(
        f"{API}/vehicles",
        headers=admin,
        json={
            "site_id": site,
            "vehicle_category_id": category["vehicle_category_id"],
            "fleet_number": "R9-CAMION-01",
        },
    )
    assert vehicule.status_code == 201, vehicule.text
    assurance = client.post(
        f"{API}/vehicles/{vehicule.json()['vehicle_id']}/documents",
        headers=admin,
        json={
            "doc_type": "INSURANCE",
            "reference": "ASS-R9-1",
            "valid_until": (today + timedelta(days=10)).isoformat(),
        },
    )
    assert assurance.status_code == 201, assurance.text
    dues = client.get(f"{API}/vehicle-documents", headers=finance, params={"within_days": 45})
    assert dues.status_code == 200, dues.text
    (item,) = [d for d in dues.json() if d["doc_type"] == "INSURANCE"]
    assert (item["reference"], item["validity"]) == ("ASS-R9-1", "EXPIRING")

    # --- Chaque écriture clé est auditée -----------------------------------------------------------
    def _actions(**params: object) -> set[str]:
        items = client.get(f"{API}/audit-events", headers=admin, params=params).json()["items"]
        return {e["action"] for e in items}

    journal_doc = _actions(entity_id=doc_id)
    assert {"legal.contract.document.upload", "legal.contract.document.verify"} <= journal_doc
    journal_contrat = _actions(entity_id=cid)
    assert {"legal.contract.submit", "legal.contract.review"} <= journal_contrat
    journal = client.get(f"{API}/audit-events", headers=admin, params={"page_size": 200}).json()["items"]
    assert {"legal.contract.storage_reconciliation.read"} <= {e["action"] for e in journal}
    refus = [
        e
        for e in journal
        if e["action"] == "legal.contract.create"
        and e["outcome"] == "DENIED"
        and e["actor_user_id"] == str(conducteur.user_id)
    ]
    assert refus, "le refus 403 du DRIVER doit être audité avec le compte et la permission"
