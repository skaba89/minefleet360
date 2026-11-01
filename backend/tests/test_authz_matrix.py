"""Tests d'autorisation GÉNÉRÉS depuis authz_matrix.yaml (D-09, MATRICE_RBAC §7.2).

L'oracle vient du YAML et de la table de décision D-05, jamais des décorateurs de routes.
- ST-01 : inventaire route ↔ permission (une route sans permission déclarée fait échouer le build).
- ST-02 : pour chaque route × (rôle, portée) non autorisé → 403 PERMISSION_DENIED, audité.
- Isolation : pour chaque route « item » autorisée, l'identifiant d'un objet d'un autre tenant
  donne un 404 indiscernable d'un UUID inexistant, sans modification.
"""

import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.authz.matrix import load_matrix
from app.legal import router as legal_router
from tests.conftest import API, Api, TenantFixture

MATRIX = load_matrix()
PARAM = re.compile(r"\{(\w+)\}")
SAMPLE_BODIES: dict[tuple[str, str], dict[str, object]] = {
    ("POST", "/fuel/pumps/{fuel_pump_id}/anomaly-cases"): {
        "start_reading_id": "00000000-0000-4000-8000-000000000011",
        "end_reading_id": "00000000-0000-4000-8000-000000000012",
    },
    ("POST", "/fuel/anomaly-cases/{fuel_pump_anomaly_case_id}/events"): {
        "event_type": "ACKNOWLEDGED",
        "justification": "Contrôle documentaire requis",
    },
    ("POST", "/vehicles/{vehicle_id}/gps/tracker"): {"device_id": "gps-test"},
    ("POST", "/drivers/{driver_id}/gps-account"): {"user_account_id": None},
    ("POST", "/me/gps/shares/{share_id}/positions"): {
        "latitude": 9.5,
        "longitude": -13.7,
        "accuracy_m": 10,
        "recorded_at": "2026-01-01T10:00:00+00:00",
    },
    ("PATCH", "/sites/{site_id}"): {"name": "Nom modifié"},
    ("PATCH", "/users/{user_id}"): {"display_name": "Nom-Test modifié"},
    ("PATCH", "/tenant"): {"display_name": "Nom modifié"},
    ("PATCH", "/vehicles/{vehicle_id}"): {"notes": "Note fictive"},
    ("POST", "/vehicles/{vehicle_id}/status"): {"status": "IN_MAINTENANCE"},
    ("POST", "/vehicles/{vehicle_id}/retire"): {"reason_code": "END_OF_LIFE"},
    ("PATCH", "/drivers/{driver_id}"): {"last_name": "Nom-Test"},
    ("POST", "/drivers/{driver_id}/status"): {"status": "UNAVAILABLE", "unavailability_reason": "LEAVE"},
    ("POST", "/drivers/{driver_id}/licenses"): {
        "license_number": "PERMIS-FICTIF-9999",
        "category_code": "C",
        "issue_date": "2020-01-01",
        "expiry_date": "2030-01-01",
    },
    ("PATCH", "/driver-licenses/{license_id}"): {"status_note": "Note fictive"},
    ("POST", "/drivers/{driver_id}/qualifications"): {
        "qualification_type": "SAFETY_TRAINING",
        "valid_from": "2024-01-01",
    },
    ("POST", "/driver-qualifications/{qualification_id}/revoke"): {"status": "SUSPENDED"},
    ("POST", "/vehicle-assignments/{vehicle_assignment_id}/suspend"): {"reason_code": "WEATHER"},
    ("POST", "/vehicle-assignments/{vehicle_assignment_id}/complete"): {},
    ("POST", "/vehicle-assignments/{vehicle_assignment_id}/cancel"): {"reason_code": "PLAN_CHANGED"},
    ("PATCH", "/site-locations/{site_location_id}"): {"name": "Lieu modifié"},
    ("PATCH", "/materials/{material_id}"): {"name": "Matière modifiée"},
    ("POST", "/missions/{mission_id}/events"): {"event_type": "SUSPENDED", "reason_code": "WEATHER"},
    ("POST", "/vehicles/{vehicle_id}/meter-readings"): {"meter_kind": "ODOMETER_KM", "value": 10},
    ("POST", "/vehicles/{vehicle_id}/meter-resets"): {
        "meter_kind": "ODOMETER_KM",
        "value": 1,
        "reset_reason": "METER_REPLACED",
    },
    ("POST", "/vehicles/{vehicle_id}/documents"): {
        "doc_type": "SITE_ACCESS_PERMIT",
        "reference": "ACCES-FICTIF-1",
        "valid_until": "2030-01-01",
    },
    ("PUT", "/vehicle-categories/{category_id}/required-documents"): {"doc_types": ["INSURANCE"]},
    ("POST", "/vehicle-documents/{vehicle_document_id}/withdraw"): {"reason_code": "ENTRY_ERROR"},
    ("POST", "/part-replenishments/{replenishment_id}/decision"): {"action": "APPROVE", "note": "Revu"},
    ("POST", "/work-orders/{work_order_id}/decision"): {"action": "APPROVE"},
    ("POST", "/work-orders/{work_order_id}/progress"): {"action": "NOTE", "diagnosis": "Diagnostic fictif"},
    ("POST", "/work-orders/{work_order_id}/labour"): {"minutes": 10, "performed_on": "2026-01-01"},
    ("POST", "/fuel/tanks"): {
        "site_id": "00000000-0000-0000-0000-000000000001",
        "code": "CUVE-TEST",
        "fuel_type": "DIESEL",
        "capacity_liters": 10000,
    },
    ("POST", "/fuel/pumps"): {
        "fuel_tank_id": "00000000-0000-0000-0000-000000000001",
        "code": "POMPE-TEST",
        "name": "Pompe test",
    },
    ("PUT", "/fuel/pumps/{fuel_pump_id}/anomaly-tolerance"): {
        "tolerance_liters": 5,
        "tolerance_percent": 1,
    },
    ("POST", "/fuel/pumps/{fuel_pump_id}/meter-readings"): {
        "cumulative_liters": 100,
        "measured_at": "2026-10-29T10:00:00+00:00",
        "source": "MANUAL",
        "source_reference": "RELEVE-TEST-1",
    },
    ("POST", "/fuel/tanks/{fuel_tank_id}/receipts"): {
        "liters": 100,
        "reference": "BL-FICTIF-1",
        "occurred_at": "2026-10-29T10:00:00+00:00",
    },
    ("POST", "/fuel/tanks/{fuel_tank_id}/threshold"): {"low_stock_threshold_liters": 500},
    ("POST", "/fuel/tanks/{fuel_tank_id}/stocktakes"): {
        "counted_liters": 100,
        "reference": "INV-TEST-1",
        "reason_code": "MEASUREMENT",
        "occurred_at": "2026-10-29T10:00:00+00:00",
    },
    ("POST", "/fuel/issues"): {
        "fuel_tank_id": "00000000-0000-0000-0000-000000000001",
        "vehicle_id": "00000000-0000-0000-0000-000000000002",
        "driver_id": "00000000-0000-0000-0000-000000000003",
        "liters": 20,
        "requested_at": "2026-01-01T10:00:00+00:00",
    },
    ("POST", "/fuel/issues/{fuel_issue_id}/decision"): {"decision": "APPROVED"},
    ("POST", "/fuel/purchases/{fuel_purchase_order_id}/decision"): {"decision": "APPROVED"},
    ("POST", "/fuel/purchases/{fuel_purchase_order_id}/receipts"): {
        "liters": 100,
        "delivery_reference": "BL-ACHAT-FICTIF-1",
        "occurred_at": "2026-10-29T10:00:00+00:00",
    },
    ("POST", "/weighing-tickets/{weighing_ticket_id}/approve"): {},
    ("POST", "/weighing-tickets/{weighing_ticket_id}/void"): {"reason_code": "ENTRY_ERROR"},
    ("POST", "/weighing-tickets/{weighing_ticket_id}/correct"): {
        "weighbridge_location_id": str(uuid.uuid4()),
        "ticket_number": "T-CORR-1",
        "weighed_at": "2026-01-01T10:00:00+00:00",
        "gross_kg": 50000,
        "tare_kg": 20000,
        "reason_code": "ENTRY_ERROR",
    },
}


@dataclass(frozen=True)
class Persona:
    role: str
    scope: str
    headers: dict[str, str]

    @property
    def label(self) -> str:
        return f"{self.role}/{self.scope}"


@dataclass
class World:
    a: TenantFixture
    b: TenantFixture
    personas: list[Persona]
    b_personas: dict[str, Persona]
    a_objects: dict[str, uuid.UUID]


@pytest.fixture(scope="module")
def world(api: Api, client: TestClient) -> World:
    a, b = api.tenant(), api.tenant()
    personas = [Persona("PLATFORM_ADMIN", "PLATFORM", api.platform())]
    for code, role in MATRIX.roles.items():
        if role.tenant_kind != "CUSTOMER":
            continue
        for scope in role.allowed_scopes:
            account = api.user(a, code, scope, "S1" if scope == "SITE" else None)
            personas.append(Persona(code, scope, account.headers))
    b_personas = {
        "TENANT_ADMIN": Persona("TENANT_ADMIN", "TENANT", b.admin.headers),
        "AUDITOR": Persona("AUDITOR", "TENANT", api.user(b, "AUDITOR").headers),
        "HR": Persona("HR", "TENANT", api.user(b, "HR").headers),
        "OPS_MANAGER": Persona("OPS_MANAGER", "TENANT", api.user(b, "OPS_MANAGER").headers),
    }
    hr = api.user(a, "HR")
    assignment = client.get(
        f"{API}/role-assignments", headers=a.admin.headers, params={"user_id": str(hr.user_id)}
    ).json()["items"][0]["user_role_assignment_id"]
    event = client.get(f"{API}/audit-events", headers=a.admin.headers).json()["items"][0]["audit_event_id"]
    category = client.get(f"{API}/vehicle-categories", headers=a.admin.headers).json()[0][
        "vehicle_category_id"
    ]
    vehicle = client.post(
        f"{API}/vehicles",
        headers=a.admin.headers,
        json={"site_id": str(a.sites["S1"]), "vehicle_category_id": category, "fleet_number": "PARC-001"},
    ).json()["vehicle_id"]
    driver = client.post(
        f"{API}/drivers",
        headers=hr.headers,
        json={
            "site_id": str(a.sites["S1"]),
            "employee_number": "MAT-001",
            "last_name": "Nom-Test",
            "first_name": "A",
        },
    ).json()["driver_id"]
    license_id = client.post(
        f"{API}/drivers/{driver}/licenses",
        headers=hr.headers,
        json=SAMPLE_BODIES[("POST", "/drivers/{driver_id}/licenses")],
    ).json()["driver_license_id"]
    qualification = client.post(
        f"{API}/drivers/{driver}/qualifications",
        headers=hr.headers,
        json={
            "qualification_type": "DRIVING_AUTHORIZATION",
            "vehicle_category_id": category,
            "valid_from": "2024-01-01",
        },
    ).json()["driver_qualification_id"]
    ops = next(p for p in personas if p.role == "OPS_MANAGER" and p.scope == "TENANT")
    vehicle_assignment = client.post(
        f"{API}/vehicle-assignments",
        headers=ops.headers,
        json={
            "vehicle_id": vehicle,
            "driver_id": driver,
            "valid_from": (datetime.now(UTC) + timedelta(days=7)).isoformat(),
        },
    )
    assert vehicle_assignment.status_code == 201, vehicle_assignment.text
    places = [
        client.post(
            f"{API}/site-locations",
            headers=a.admin.headers,
            json={"site_id": str(a.sites["S1"]), "code": code, "name": f"Lieu {code}", "kind": kind},
        ).json()["site_location_id"]
        for code, kind in (("FOSSE-1", "LOADING_POINT"), ("VERSE-1", "DUMP_POINT"))
    ]
    material = client.post(
        f"{API}/materials", headers=a.admin.headers, json={"code": "BAUX", "name": "Bauxite"}
    ).json()["material_id"]
    mission = client.post(
        f"{API}/missions",
        headers=ops.headers,
        json={
            "vehicle_assignment_id": vehicle_assignment.json()["vehicle_assignment_id"],
            "origin_location_id": places[0],
            "destination_location_id": places[1],
            "material_id": material,
            "planned_start": (datetime.now(UTC) + timedelta(days=7)).isoformat(),
        },
    )
    assert mission.status_code == 201, mission.text
    weighing_ticket = _weighed_rotation(client, a, hr, ops, category, places, material)
    document = client.post(
        f"{API}/vehicles/{vehicle}/documents",
        headers=a.admin.headers,
        json={"doc_type": "ROAD_PERMIT", "reference": "RP-FICTIF-1", "valid_until": "2030-01-01"},
    )
    assert document.status_code == 201, document.text
    work_order = client.post(
        f"{API}/work-orders",
        headers=ops.headers,
        json={"vehicle_id": vehicle, "symptom_code": "OTHER", "priority": "LOW"},
    )
    assert work_order.status_code == 201, work_order.text
    fuel_tank = client.post(
        f"{API}/fuel/tanks",
        headers=a.admin.headers,
        json={
            "site_id": str(a.sites["S1"]),
            "code": "CUVE-RBAC",
            "fuel_type": "DIESEL",
            "capacity_liters": 10000,
        },
    )
    assert fuel_tank.status_code == 201, fuel_tank.text
    fuel_pump = client.post(
        f"{API}/fuel/pumps",
        headers=a.admin.headers,
        json={
            "fuel_tank_id": fuel_tank.json()["fuel_tank_id"],
            "code": "POMPE-RBAC",
            "name": "Pompe RBAC",
        },
    )
    assert fuel_pump.status_code == 201, fuel_pump.text
    readings = []
    for number, minutes in ((100, 10), (120, 5)):
        response = client.post(
            f"{API}/fuel/pumps/{fuel_pump.json()['fuel_pump_id']}/meter-readings",
            headers=a.admin.headers,
            json={
                "cumulative_liters": number,
                "measured_at": (datetime.now(UTC) - timedelta(minutes=minutes)).isoformat(),
                "source": "MANUAL",
                "source_reference": f"RBAC-READ-{number}",
            },
        )
        assert response.status_code == 201, response.text
        readings.append(response.json()["fuel_pump_meter_reading_id"])
    anomaly = client.post(
        f"{API}/fuel/pumps/{fuel_pump.json()['fuel_pump_id']}/anomaly-cases",
        headers=a.admin.headers,
        json={"start_reading_id": readings[0], "end_reading_id": readings[1]},
    )
    assert anomaly.status_code == 201, anomaly.text
    objects = {
        "work_order_id": uuid.UUID(work_order.json()["work_order_id"]),
        "vehicle_document_id": uuid.UUID(document.json()["vehicle_document_id"]),
        "weighing_ticket_id": weighing_ticket,
        "site_location_id": uuid.UUID(places[0]),
        "material_id": uuid.UUID(material),
        "mission_id": uuid.UUID(mission.json()["mission_id"]),
        "vehicle_assignment_id": uuid.UUID(vehicle_assignment.json()["vehicle_assignment_id"]),
        "vehicle_id": uuid.UUID(vehicle),
        "category_id": uuid.UUID(category),
        "driver_id": uuid.UUID(driver),
        "license_id": uuid.UUID(license_id),
        "qualification_id": uuid.UUID(qualification),
        "site_id": a.sites["S1"],
        "user_id": hr.user_id,
        "assignment_id": uuid.UUID(assignment),
        "event_id": uuid.UUID(event),
        "tenant_id": a.tenant_id,
        "fuel_tank_id": uuid.UUID(fuel_tank.json()["fuel_tank_id"]),
        "fuel_pump_id": uuid.UUID(fuel_pump.json()["fuel_pump_id"]),
        "fuel_pump_anomaly_case_id": uuid.UUID(anomaly.json()["fuel_pump_anomaly_case_id"]),
    }
    return World(a, b, personas, b_personas, objects)


def _weighed_rotation(  # type: ignore[no-untyped-def]
    client: TestClient, a: TenantFixture, hr, ops: Persona, category: str, places: list[str], material: str
) -> uuid.UUID:
    """Lot 2b : affectation active, mission chargée et pesée en saisie dégradée (approbation testable)."""
    vehicle = client.post(
        f"{API}/vehicles",
        headers=a.admin.headers,
        json={"site_id": str(a.sites["S1"]), "vehicle_category_id": category, "fleet_number": "PARC-002"},
    ).json()["vehicle_id"]
    driver = client.post(
        f"{API}/drivers",
        headers=hr.headers,
        json={
            "site_id": str(a.sites["S1"]),
            "employee_number": "MAT-002",
            "last_name": "Nom-Test",
            "first_name": "B",
        },
    ).json()["driver_id"]
    client.post(
        f"{API}/drivers/{driver}/licenses",
        headers=hr.headers,
        json={
            **SAMPLE_BODIES[("POST", "/drivers/{driver_id}/licenses")],
            "license_number": "PERMIS-FICTIF-9998",
        },
    )
    client.post(
        f"{API}/drivers/{driver}/qualifications",
        headers=hr.headers,
        json={
            "qualification_type": "DRIVING_AUTHORIZATION",
            "vehicle_category_id": category,
            "valid_from": "2024-01-01",
        },
    )
    assignment = client.post(
        f"{API}/vehicle-assignments",
        headers=ops.headers,
        json={"vehicle_id": vehicle, "driver_id": driver, "valid_from": datetime.now(UTC).isoformat()},
    )
    assert assignment.status_code == 201, assignment.text
    mission = client.post(
        f"{API}/missions",
        headers=ops.headers,
        json={
            "vehicle_assignment_id": assignment.json()["vehicle_assignment_id"],
            "origin_location_id": places[0],
            "destination_location_id": places[1],
            "material_id": material,
            "planned_start": datetime.now(UTC).isoformat(),
        },
    ).json()
    url = f"{API}/missions/{mission['mission_id']}"
    for event in ("DEPARTED", "ARRIVED_LOADING", "LOADED"):
        version = client.get(url, headers=ops.headers).headers["ETag"]
        done = client.post(
            f"{url}/events", headers={**ops.headers, "If-Match": version}, json={"event_type": event}
        )
        assert done.status_code == 200, done.text
    rotation = client.get(url, headers=ops.headers).json()["rotations"][0]["rotation_id"]
    bridge = client.post(
        f"{API}/site-locations",
        headers=a.admin.headers,
        json={"site_id": str(a.sites["S1"]), "code": "PONT-1", "name": "Pont 1", "kind": "WEIGHBRIDGE"},
    ).json()["site_location_id"]
    ticket = client.post(
        f"{API}/weighing-tickets",
        headers=ops.headers,
        json={
            "rotation_id": rotation,
            "weighbridge_location_id": bridge,
            "ticket_number": "T-0001",
            "source": "MANUAL_DEGRADED",
            "degraded_reason": "WEIGHBRIDGE_DOWN",
            "weighed_at": datetime.now(UTC).isoformat(),
            "gross_kg": 50000,
            "tare_kg": 20000,
        },
    )
    assert ticket.status_code == 201, ticket.text
    return uuid.UUID(ticket.json()["weighing_ticket_id"])


def _routes() -> list[tuple[str, str, str]]:
    return [
        (perm.name, route.method, route.path)
        for perm in MATRIX.permissions.values()
        if perm.tranche != "later"
        for route in perm.routes
    ]


def _call(client: TestClient, method: str, path: str, headers: dict[str, str], ids: dict[str, uuid.UUID]):  # type: ignore[no-untyped-def]
    url = API + PARAM.sub(lambda m: str(ids.get(m.group(1), uuid.uuid4())), path)
    body = SAMPLE_BODIES.get((method, path))
    return client.request(method, url, headers={**headers, "If-Match": '"1"'}, json=body)


# --- ST-01 --------------------------------------------------------------------------------------------


def test_st01_every_route_declares_exactly_the_matrix_permission(client: TestClient) -> None:
    """Inventaire via le schéma OpenAPI (indépendant des structures internes du routeur FastAPI).

    `x-permission` est dérivé de la dépendance `Require` réellement attachée à la route (SecuredRoute).
    """
    declared = MATRIX.route_permissions()
    schema = client.get(f"{API}/openapi.json").json()
    seen: set[tuple[str, str]] = set()
    problems = []
    for full_path, operations in schema["paths"].items():
        path = full_path.removeprefix(API)
        for method, operation in operations.items():
            key = (method.upper(), path)
            seen.add(key)
            permission = operation.get("x-permission")
            if key in MATRIX.public_routes:
                if permission is not None:
                    problems.append(f"{key} est publique mais exige {permission}")
            elif declared.get(key) != permission:
                problems.append(f"{key}: code={permission} matrice={declared.get(key)}")
    missing = (set(declared) | set(MATRIX.public_routes)) - seen
    assert problems == [] and missing == set()


def test_st01_openapi_exposes_x_permission(client: TestClient) -> None:
    schema = client.get(f"{API}/openapi.json").json()
    for (method, path), permission in MATRIX.route_permissions().items():
        assert schema["paths"][API + path][method.lower()]["x-permission"] == permission


# --- ST-02 (refus) ------------------------------------------------------------------------------------


def _denied_cases() -> list[tuple[str, str, str, str, str]]:
    personas = [("PLATFORM_ADMIN", "PLATFORM")] + [
        (code, scope)
        for code, role in MATRIX.roles.items()
        if role.tenant_kind == "CUSTOMER"
        for scope in role.allowed_scopes
    ]
    return [
        (permission, method, path, role, scope)
        for permission, method, path in _routes()
        for role, scope in personas
        if scope not in MATRIX.permissions[permission].grants.get(role, ())
    ]


@pytest.mark.parametrize(("permission", "method", "path", "role", "scope"), _denied_cases())
def test_st02_role_without_permission_gets_403(
    client: TestClient, world: World, permission: str, method: str, path: str, role: str, scope: str
) -> None:
    persona = next(p for p in world.personas if p.role == role and p.scope == scope)
    resp = _call(client, method, path, persona.headers, world.a_objects)
    assert resp.status_code == 403, (persona.label, resp.text)
    assert resp.json()["code"] == "PERMISSION_DENIED"


def test_st02_denials_are_audited(client: TestClient, world: World) -> None:
    hr = next(p for p in world.personas if p.role == "HR" and p.scope == "TENANT")
    client.get(f"{API}/audit-events", headers=hr.headers)
    events = client.get(
        f"{API}/audit-events", headers=world.a.admin.headers, params={"action": "audit.event.read"}
    ).json()["items"]
    assert any(e["outcome"] == "DENIED" and e["reason"] == "PERMISSION_DENIED" for e in events)


# --- ST-02 (accès autorisés en lecture) ---------------------------------------------------------------


def _allowed_reads() -> list[tuple[str, str, str, str]]:
    cases = []
    for permission, method, path in _routes():
        if method != "GET":
            continue
        for role, scopes in MATRIX.permissions[permission].grants.items():
            cases.extend((path, permission, role, scope) for scope in scopes)
    return cases


@pytest.mark.parametrize(("path", "permission", "role", "scope"), _allowed_reads())
def test_st02_granted_reads_succeed_within_scope(
    client: TestClient,
    world: World,
    path: str,
    permission: str,
    role: str,
    scope: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    persona = next(p for p in world.personas if p.role == role and p.scope == scope)
    if path == "/legal-contracts/storage-reconciliation":
        # S3 is intentionally disabled in the CI test environment; preserve the real RBAC gate.
        monkeypatch.setattr(
            legal_router,
            "build_private_contract_store",
            lambda _settings: SimpleNamespace(client=object(), bucket="test-private"),
        )
        monkeypatch.setattr(
            legal_router,
            "summarize_tenant_contract_storage",
            lambda **_kwargs: SimpleNamespace(orphan_count=0, missing_count=0, consistent=True),
        )
    resp = _call(client, "GET", path, persona.headers, world.a_objects)
    assert resp.status_code == 200, (persona.label, permission, resp.text)


def test_site_scoped_role_sees_only_its_site(client: TestClient, world: World) -> None:
    dispatcher = next(p for p in world.personas if p.role == "DISPATCHER")
    listed = client.get(f"{API}/sites", headers=dispatcher.headers).json()
    assert [s["site_id"] for s in listed["items"]] == [str(world.a.sites["S1"])] and listed["total"] == 1
    other = client.get(f"{API}/sites/{world.a.sites['S2']}", headers=dispatcher.headers)
    assert other.status_code == 404 and other.json()["code"] == "NOT_FOUND"


# --- Isolation inter-tenant ---------------------------------------------------------------------------


def _item_routes() -> list[tuple[str, str, str, str]]:
    cases = []
    for permission, method, path in _routes():
        if "{" not in path or path.startswith("/platform"):
            continue
        for role in ("TENANT_ADMIN", "AUDITOR", "HR", "OPS_MANAGER"):
            if "TENANT" in MATRIX.permissions[permission].grants.get(role, ()):
                cases.append((permission, method, path, role))
                break
    return cases


def _strip(body: dict) -> dict:  # type: ignore[type-arg]
    return {k: v for k, v in body.items() if k != "request_id"}


@pytest.mark.parametrize(("permission", "method", "path", "role"), _item_routes())
def test_isolation_foreign_object_is_indistinguishable_from_missing(
    client: TestClient, world: World, permission: str, method: str, path: str, role: str
) -> None:
    persona = world.b_personas[role]
    before = client.get(f"{API}/audit-events", headers=world.a.admin.headers).json()["total"]
    foreign = _call(client, method, path, persona.headers, world.a_objects)
    missing = _call(client, method, path, persona.headers, {})
    assert foreign.status_code == missing.status_code == 404, (permission, foreign.text)
    assert _strip(foreign.json()) == _strip(missing.json())
    assert client.get(f"{API}/audit-events", headers=world.a.admin.headers).json()["total"] == before


def test_isolation_lists_never_include_other_tenant(client: TestClient, world: World) -> None:
    b_admin = world.b.admin.headers
    sites = client.get(f"{API}/sites", headers=b_admin).json()
    users = client.get(f"{API}/users", headers=b_admin).json()
    events = client.get(f"{API}/audit-events", headers=b_admin).json()
    assert {s["site_id"] for s in sites["items"]}.isdisjoint({str(x) for x in world.a.sites.values()})
    assert str(world.a_objects["user_id"]) not in {u["user_account_id"] for u in users["items"]}
    assert str(world.a_objects["event_id"]) not in {e["audit_event_id"] for e in events["items"]}


def test_isolation_foreign_reference_in_body_is_422(client: TestClient, world: World) -> None:
    resp = client.post(
        f"{API}/users",
        headers=world.b.admin.headers,
        json={
            "email": f"x.{uuid.uuid4().hex[:6]}@example.com",
            "display_name": "Nom-Test X",
            "role_code": "DISPATCHER",
            "scope_type": "SITE",
            "site_id": str(world.a.sites["S1"]),
        },
    )
    assert resp.status_code == 422 and resp.json()["code"] == "REFERENCE_NOT_FOUND"


def test_isolation_tenant_id_in_body_is_rejected(client: TestClient, world: World) -> None:
    resp = client.post(
        f"{API}/sites",
        headers=world.b.admin.headers,
        json={"code": "ZZ", "name": "Site intrus", "site_type": "MINE", "tenant_id": str(world.a.tenant_id)},
    )
    assert resp.status_code == 422 and resp.json()["code"] == "VALIDATION_ERROR"
