"""HSE-2 — checklists, inspections, non-conformités, preuves photo (docs/LIVRAISON_HSE2.md)."""

import hashlib
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError

from app.core.config import get_settings
from app.hse import inspections
from app.legal.malware_scan import ScanVerdict
from tests.conftest import API, Account, Api, TenantFixture

JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 64
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


class MemoryStore:
    def __init__(self) -> None:
        self.objects: dict[str, tuple[bytes, str]] = {}

    def put(self, *, key: str, content: bytes, content_type: str = "application/pdf") -> None:
        self.objects[key] = (content, content_type)

    def get(self, *, key: str) -> bytes:
        return self.objects[key][0]


class FakeScanner:
    verdict = ScanVerdict.CLEAN

    def scan(self, content: bytes) -> ScanVerdict:
        return self.verdict


@dataclass
class World:
    t: TenantFixture
    other: TenantFixture
    hse: Account
    hse2: Account
    ops: Account
    mechanic: Account
    mechanic_s2: Account
    other_hse: Account
    vehicle: str
    vehicle_s2: str


def _vehicle(client: TestClient, t: TenantFixture, site: str) -> str:
    category = client.get(f"{API}/vehicle-categories", headers=t.admin.headers).json()[0][
        "vehicle_category_id"
    ]
    resp = client.post(
        f"{API}/vehicles",
        headers=t.admin.headers,
        json={
            "site_id": str(t.sites[site]),
            "vehicle_category_id": category,
            "fleet_number": f"I-{uuid.uuid4().hex[:6]}",
        },
    )
    assert resp.status_code == 201, resp.text
    return str(resp.json()["vehicle_id"])


@pytest.fixture(scope="module")
def w(api: Api, client: TestClient) -> World:
    t, other = api.tenant(), api.tenant()
    return World(
        t=t,
        other=other,
        hse=api.user(t, "HSE"),
        hse2=api.user(t, "HSE"),
        ops=api.user(t, "OPS_MANAGER"),
        mechanic=api.user(t, "MECHANIC", "SITE", "S1"),
        mechanic_s2=api.user(t, "MECHANIC", "SITE", "S2"),
        other_hse=api.user(other, "HSE"),
        vehicle=_vehicle(client, t, "S1"),
        vehicle_s2=_vehicle(client, t, "S2"),
    )


@pytest.fixture
def storage(monkeypatch: pytest.MonkeyPatch) -> MemoryStore:
    store = MemoryStore()
    FakeScanner.verdict = ScanVerdict.CLEAN
    monkeypatch.setattr(inspections, "build_evidence_store", lambda _settings: store)
    monkeypatch.setattr(inspections, "build_evidence_scanner", lambda _settings: FakeScanner())
    return store


ITEMS = [
    {"key": "freins", "label": "Freins de service efficaces", "critical": True},
    {"key": "eclairage", "label": "Éclairage et gyrophare", "critical": False},
    {"key": "extincteur", "label": "Extincteur présent et vérifié", "critical": True},
]


def _template(client: TestClient, w: World, code: str, target: str = "VEHICLE", items=None):  # type: ignore[no-untyped-def]
    return client.post(
        f"{API}/hse/checklist-templates",
        headers=w.hse.headers,
        json={"code": code, "name": f"Checklist {code}", "target_type": target, "items": items or ITEMS},
    )


def _inspect(client: TestClient, w: World, template: dict, headers=None, **extra):  # type: ignore[no-untyped-def,type-arg]
    answers = extra.pop(
        "answers",
        [{"item_key": i["key"], "result": "COMPLIANT"} for i in template["items"]],
    )
    body = {
        "site_id": str(w.t.sites["S1"]),
        "hse_checklist_template_id": template["hse_checklist_template_id"],
        "vehicle_id": w.vehicle,
        "performed_at": (datetime.now(UTC) - timedelta(minutes=30)).isoformat(),
        "answers": answers,
        **extra,
    }
    return client.post(f"{API}/hse/inspections", headers=headers or w.mechanic.headers, json=body)


def _upload(client: TestClient, headers: dict[str, str], inspection_id: str, content: bytes, ctype: str):  # type: ignore[no-untyped-def]
    return client.post(
        f"{API}/hse/inspections/{inspection_id}/evidence",
        headers={**headers, "Content-Type": ctype},
        content=content,
    )


def test_template_versions_are_immutable(client: TestClient, w: World) -> None:
    code = f"PRE-{uuid.uuid4().hex[:6]}"
    v1 = _template(client, w, code).json()
    assert v1["version"] == 1 and v1["active"] is True
    v2 = _template(client, w, code, items=ITEMS[:2]).json()
    assert v2["version"] == 2
    listed = client.get(f"{API}/hse/checklist-templates", headers=w.mechanic.headers).json()
    mine = [t for t in listed if t["code"] == code]
    assert [t["version"] for t in mine] == [2]  # seule la dernière version est proposée
    everything = client.get(
        f"{API}/hse/checklist-templates", headers=w.hse.headers, params={"include_inactive": True}
    ).json()
    assert [t["version"] for t in everything if t["code"] == code] == [2, 1]
    stale = _inspect(client, w, v1)
    assert stale.status_code == 422 and stale.json()["code"] == "REFERENCE_NOT_FOUND"
    duplicate_keys = _template(client, w, f"DUP-{uuid.uuid4().hex[:4]}", items=[ITEMS[0], ITEMS[0]])
    assert duplicate_keys.status_code == 422
    assert _template(client, w, code).status_code == 201
    forbidden = client.post(
        f"{API}/hse/checklist-templates",
        headers=w.mechanic.headers,
        json={"code": "X", "name": "Interdit", "target_type": "VEHICLE", "items": ITEMS},
    )
    assert forbidden.status_code == 403
    engine = create_engine(get_settings().database_url(), pool_size=1, max_overflow=0)
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(w.t.tenant_id)})
            with pytest.raises(DBAPIError):
                conn.execute(
                    text(
                        "UPDATE hse_checklist_template SET items = '[]'::jsonb "
                        "WHERE hse_checklist_template_id = :i"
                    ),
                    {"i": v1["hse_checklist_template_id"]},
                )
            conn.rollback()
    finally:
        engine.dispose()


def test_inspection_nonconformity_actions_and_summary(client: TestClient, w: World) -> None:
    template = _template(client, w, f"VEH-{uuid.uuid4().hex[:6]}").json()
    ok = _inspect(client, w, template)
    assert ok.status_code == 201, ok.text
    assert ok.json()["result"] == "PASS" and ok.json()["reference"].startswith("INS-")
    no_nc = client.post(
        f"{API}/hse/inspections/{ok.json()['hse_inspection_id']}/actions",
        headers=w.hse.headers,
        json={"title": "Rien", "owner_user_id": str(w.ops.user_id), "due_date": date.today().isoformat()},
    )
    assert no_nc.status_code == 422 and no_nc.json()["code"] == "HSE_NO_NONCONFORMITY"

    answers = [
        {"item_key": "freins", "result": "NON_COMPLIANT", "comment": "Course de pédale excessive"},
        {"item_key": "eclairage", "result": "NON_COMPLIANT", "comment": "Gyrophare HS"},
        {"item_key": "extincteur", "result": "NOT_APPLICABLE"},
    ]
    failed = _inspect(client, w, template, answers=answers, note="Engin consigné")
    assert failed.status_code == 201, failed.text
    inspection = failed.json()
    assert inspection["result"] == "FAIL"
    assert inspection["nonconformities"] == 2 and inspection["critical_nonconformities"] == 1
    assert inspection["answers"][0]["label"] == "Freins de service efficaces"
    iid = inspection["hse_inspection_id"]

    owners = client.get(f"{API}/hse/inspections/{iid}/action-owners", headers=w.hse.headers).json()
    assert str(w.ops.user_id) in {o["user_account_id"] for o in owners}
    created = client.post(
        f"{API}/hse/inspections/{iid}/actions",
        headers=w.hse.headers,
        json={
            "title": "Remplacer le maître-cylindre",
            "owner_user_id": str(w.ops.user_id),
            "due_date": (date.today() + timedelta(days=3)).isoformat(),
        },
    )
    assert created.status_code == 201, created.text
    action = created.json()
    assert action["hse_inspection_id"] == iid and action["hse_incident_id"] is None
    assert action["parent_reference"] == inspection["reference"]
    # Le cycle d'action HSE-1 s'applique tel quel : réalisation par le responsable, vérification par un tiers.
    done = client.post(
        f"{API}/hse/corrective-actions/{action['hse_corrective_action_id']}/complete",
        headers={**w.ops.headers, "If-Match": f'"{action["row_version"]}"'},
        json={"completion_note": "Maître-cylindre remplacé, essai concluant"},
    )
    assert done.status_code == 200, done.text
    verified = client.post(
        f"{API}/hse/corrective-actions/{action['hse_corrective_action_id']}/decision",
        headers={**w.hse.headers, "If-Match": f'"{done.json()["row_version"]}"'},
        json={"action": "VERIFY"},
    )
    assert verified.status_code == 200 and verified.json()["status"] == "VERIFIED"
    detail = client.get(f"{API}/hse/inspections/{iid}", headers=w.hse.headers).json()
    assert detail["actions"][0]["status"] == "VERIFIED" and detail["open_actions"] == 0
    summary = client.get(f"{API}/hse/summary", headers=w.hse.headers).json()
    assert summary["inspections"] >= 2 and summary["failed_inspections"] >= 1


def test_inspection_validation(client: TestClient, w: World) -> None:
    template = _template(client, w, f"VAL-{uuid.uuid4().hex[:6]}").json()
    partial = _inspect(client, w, template, answers=[{"item_key": "freins", "result": "COMPLIANT"}])
    assert partial.status_code == 422
    unknown = [{"item_key": i["key"], "result": "COMPLIANT"} for i in template["items"]] + [
        {"item_key": "inconnu", "result": "COMPLIANT"}
    ]
    assert _inspect(client, w, template, answers=unknown).status_code == 422
    no_comment = [
        {"item_key": "freins", "result": "NON_COMPLIANT"},
        {"item_key": "eclairage", "result": "COMPLIANT"},
        {"item_key": "extincteur", "result": "COMPLIANT"},
    ]
    assert _inspect(client, w, template, answers=no_comment).status_code == 422
    assert _inspect(client, w, template, vehicle_id=None).status_code == 422
    assert _inspect(client, w, template, vehicle_id=w.vehicle_s2).json()["code"] == "REFERENCE_NOT_FOUND"
    future = (datetime.now(UTC) + timedelta(hours=2)).isoformat()
    assert _inspect(client, w, template, performed_at=future).status_code == 422
    area = _template(client, w, f"ZONE-{uuid.uuid4().hex[:6]}", target="WORK_AREA").json()
    assert _inspect(client, w, area, vehicle_id=None).status_code == 422
    assert _inspect(client, w, area, vehicle_id=None, area_note="Fosse nord, banquette 3").status_code == 201


def test_evidence_upload_scan_storage_and_access(client: TestClient, w: World, storage: MemoryStore) -> None:
    template = _template(client, w, f"PH-{uuid.uuid4().hex[:6]}").json()
    iid = _inspect(client, w, template).json()["hse_inspection_id"]
    uploaded = _upload(client, w.mechanic.headers, iid, JPEG, "image/jpeg")
    assert uploaded.status_code == 201, uploaded.text
    evidence = uploaded.json()
    assert evidence["sha256"] == hashlib.sha256(JPEG).hexdigest()
    ((key, (stored, ctype)),) = storage.objects.items()
    assert stored == JPEG
    assert key.startswith(f"hse/{w.t.tenant_id}/") and key.endswith(".jpg") and ctype == "image/jpeg"
    fetched = client.get(f"{API}/hse/evidence/{evidence['hse_evidence_id']}/content", headers=w.hse.headers)
    assert fetched.status_code == 200 and fetched.content == JPEG
    assert fetched.headers["content-type"] == "image/jpeg"
    assert (
        fetched.headers["x-content-type-options"] == "nosniff"
        and "no-store" in fetched.headers["cache-control"]
    )
    detail = client.get(f"{API}/hse/inspections/{iid}", headers=w.hse.headers).json()
    assert [e["hse_evidence_id"] for e in detail["evidence"]] == [evidence["hse_evidence_id"]]

    assert _upload(client, w.mechanic.headers, iid, PNG, "image/png").status_code == 201
    disguised = _upload(client, w.mechanic.headers, iid, b"%PDF-1.7 fake", "image/jpeg")
    assert disguised.status_code == 422
    assert _upload(client, w.mechanic.headers, iid, JPEG, "image/gif").status_code == 422
    too_big = _upload(client, w.mechanic.headers, iid, b"\xff\xd8\xff" + b"\x00" * 2_000_000, "image/jpeg")
    assert too_big.status_code == 422
    FakeScanner.verdict = ScanVerdict.INFECTED
    assert _upload(client, w.mechanic.headers, iid, JPEG, "image/jpeg").status_code == 422
    FakeScanner.verdict = ScanVerdict.ERROR
    assert _upload(client, w.mechanic.headers, iid, JPEG, "image/jpeg").status_code == 503
    assert len(storage.objects) == 2  # rien n'est stocké sans verdict CLEAN

    for headers in (w.mechanic_s2.headers, w.other_hse.headers):
        assert client.get(
            f"{API}/hse/evidence/{evidence['hse_evidence_id']}/content", headers=headers
        ).status_code in (
            403,
            404,
        )
        assert _upload(client, headers, iid, JPEG, "image/jpeg").status_code == 404
    # Le mécanicien réalise l'inspection mais ne relit pas le registre ni les photos.
    assert (
        client.get(
            f"{API}/hse/evidence/{evidence['hse_evidence_id']}/content", headers=w.mechanic.headers
        ).status_code
        == 403
    )


def test_evidence_fails_closed_without_configured_services(client: TestClient, w: World) -> None:
    template = _template(client, w, f"NC-{uuid.uuid4().hex[:6]}").json()
    iid = _inspect(client, w, template).json()["hse_inspection_id"]
    # Environnement de test : ni stockage privé ni antivirus configurés → refus explicite, rien d'enregistré.
    assert _upload(client, w.mechanic.headers, iid, JPEG, "image/jpeg").status_code == 503
    assert client.get(f"{API}/hse/inspections/{iid}", headers=w.hse.headers).json()["evidence"] == []


def test_scope_and_isolation(client: TestClient, w: World) -> None:
    template = _template(client, w, f"ISO-{uuid.uuid4().hex[:6]}").json()
    iid = _inspect(client, w, template).json()["hse_inspection_id"]
    for headers in (w.other_hse.headers,):
        assert client.get(f"{API}/hse/inspections/{iid}", headers=headers).status_code == 404
        listed = client.get(f"{API}/hse/inspections", headers=headers).json()
        assert iid not in {i["hse_inspection_id"] for i in listed["items"]}
        foreign_tpl = _inspect(client, w, template, headers=headers)
        assert foreign_tpl.status_code == 422
    s2 = _inspect(client, w, template, headers=w.mechanic_s2.headers)
    assert s2.status_code == 422 and s2.json()["code"] == "REFERENCE_NOT_FOUND"  # site S1 hors de sa portée
    other_templates = client.get(f"{API}/hse/checklist-templates", headers=w.other_hse.headers).json()
    assert template["hse_checklist_template_id"] not in {
        t["hse_checklist_template_id"] for t in other_templates
    }
    engine = create_engine(get_settings().database_url(), pool_size=1, max_overflow=0)
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(w.t.tenant_id)})
            with pytest.raises(DBAPIError):
                conn.execute(
                    text("UPDATE hse_inspection SET result = 'PASS' WHERE hse_inspection_id = :i"), {"i": iid}
                )
            conn.rollback()
    finally:
        engine.dispose()
