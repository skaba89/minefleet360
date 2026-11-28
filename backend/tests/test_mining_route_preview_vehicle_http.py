"""HTTP contract of the vehicle-restricted route preview (Phase 9).

The resolver must serve the latest ingested technical profile of a vehicle
parked at the requested site; the restriction evaluation fails closed. These
checks pin the HTTP surface: compatible vehicle, overweight version 2 (latest
wins), missing or foreign vehicles, vehicle parked elsewhere, missing
evidence, category mismatch.
"""

import uuid
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.core.db import new_session
from app.core.tenancy import set_tenant_context
from tests.conftest import API, Api

DEPARTURE = "2026-11-20T08:00:00Z"
HORIZON = "2026-11-20T09:00:00Z"


def _base(api: Api):
    """One tenant whose draft survey has one 110 m / 20 s segment, restricted
    (40 t, 30 km/h, gabarits 4500/3500/13000, pentes 80/60) and opened to the
    vehicle category, plus one vehicle with a complete technical profile."""
    tenant = api.tenant()
    site = tenant.sites["S1"]
    ops = api.user(tenant, "OPS_MANAGER", "SITE", site="S1")
    categories = api.client.get("/api/v1/vehicle-categories", headers=tenant.admin.headers)
    assert categories.status_code == 200, categories.text
    category = next(row for row in categories.json() if row["is_active"])
    created = api.client.post(
        "/api/v1/vehicles",
        headers=tenant.admin.headers,
        json={
            "site_id": str(site),
            "vehicle_category_id": category["vehicle_category_id"],
            "fleet_number": "PREVIEW-1",
            "make": "Synthetic",
            "model": "Truck",
        },
    )
    assert created.status_code == 201, created.text
    vehicle = uuid.UUID(created.json()["vehicle_id"])
    revision = uuid4()
    nodes = {}
    with new_session() as db:
        set_tenant_context(db, tenant.tenant_id)
        params = {"t": tenant.tenant_id, "s": site, "r": revision}
        db.execute(
            text(
                "INSERT INTO mining_route_revision (tenant_id, site_id, revision_id, version, provenance) "
                "VALUES (:t, :s, :r, 1, 'Synthetic survey')"
            ),
            params,
        )
        for key, longitude in (("a", -13.5), ("b", -13.499)):
            params[key] = uuid4()
            nodes[key] = params[key]
            db.execute(
                text(
                    "INSERT INTO mining_route_node (tenant_id, site_id, revision_id, node_id, "
                    "position, provenance) "
                    "VALUES (:t, :s, :r, :node, ST_SetSRID(ST_Point(:lon, 9.5), 4326), 'Synthetic survey')"
                ),
                {**params, "node": params[key], "lon": longitude},
            )
        params["segment"] = uuid4()
        db.execute(
            text(
                "INSERT INTO mining_route_segment (tenant_id, site_id, revision_id, segment_id, "
                "origin_id, destination_id, path, distance_m, duration_seconds, provenance) "
                "SELECT :t, :s, :r, :segment, a.node_id, b.node_id, ST_MakeLine(a.position,b.position), "
                "110, 20, 'Synthetic survey' FROM mining_route_node a, mining_route_node b "
                "WHERE a.node_id = :a AND b.node_id = :b"
            ),
            params,
        )
        db.execute(
            text(
                "INSERT INTO mining_road_restriction (tenant_id, site_id, revision_id, segment_id, "
                "max_gross_mass_kg, max_speed_kmh, max_height_mm, max_width_mm, max_length_mm, "
                "uphill_permille, downhill_permille, provenance) "
                "VALUES (:t, :s, :r, :segment, 40000, 30, 4500, 3500, 13000, 80, 60, 'Synthetic survey')"
            ),
            params,
        )
        db.execute(
            text(
                "INSERT INTO mining_road_allowed_category (tenant_id, site_id, revision_id, segment_id, "
                "vehicle_category_id) VALUES (:t, :s, :r, :segment, :category)"
            ),
            {**params, "category": category["vehicle_category_id"]},
        )
        db.execute(
            text(
                "INSERT INTO mining_vehicle_profile (tenant_id, vehicle_id, version, tare_mass_kg, "
                "max_gross_mass_kg, height_mm, width_mm, length_mm, max_uphill_permille, "
                "max_downhill_permille, max_speed_kmh, provenance) "
                "VALUES (:t, :v, :version, 20000, :gross, 4000, 3000, 12000, 90, 90, 30, 'Synthetic')"
            ),
            {"t": tenant.tenant_id, "v": vehicle, "version": 1, "gross": 40000},
        )
        db.commit()
    return tenant, site, revision, nodes, vehicle, ops


def _preview(
    client: TestClient,
    headers: dict[str, str],
    site,
    revision,
    origin,
    destination,
    vehicle=None,
):
    params = {
        "origin_id": str(origin),
        "destination_id": str(destination),
        "departure": DEPARTURE,
        "horizon": HORIZON,
    }
    if vehicle is not None:
        params["vehicle_id"] = str(vehicle)
    return client.get(
        f"{API}/sites/{site}/mining/revisions/{revision}/route-preview", headers=headers, params=params
    )


def test_restricted_preview_with_compatible_vehicle(api: Api) -> None:
    _tenant, site, revision, nodes, vehicle, ops = _base(api)
    resp = _preview(api.client, ops.headers, site, revision, nodes["a"], nodes["b"], vehicle)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["found"] is True
    # Plafond de vitesse 30 km/h : ceil(110 m × 3,6 / 30) = 14 s < référence 20 s.
    assert body["distance_m"] == 110 and body["duration_seconds"] == 20


def test_latest_profile_version_wins_fail_closed(api: Api) -> None:
    tenant, site, revision, nodes, vehicle, ops = _base(api)
    with new_session() as db:
        set_tenant_context(db, tenant.tenant_id)
        db.execute(
            text(
                "INSERT INTO mining_vehicle_profile (tenant_id, vehicle_id, version, tare_mass_kg, "
                "max_gross_mass_kg, height_mm, width_mm, length_mm, max_uphill_permille, "
                "max_downhill_permille, max_speed_kmh, provenance) "
                "VALUES (:t, :v, 2, 20000, 45000, 4000, 3000, 12000, 90, 90, 30, 'Synthetic v2')"
            ),
            {"t": tenant.tenant_id, "v": vehicle},
        )
        db.commit()
    resp = _preview(api.client, ops.headers, site, revision, nodes["a"], nodes["b"], vehicle)
    assert resp.status_code == 200, resp.text
    assert resp.json()["found"] is False and resp.json()["nodes"] == []


def test_vehicle_profile_unresolvable_cases(api: Api) -> None:
    tenant, site, revision, nodes, _vehicle, ops = _base(api)
    # Véhicule inconnu ou d'un autre tenant : 404 indiscernable.
    missing = _preview(api.client, ops.headers, site, revision, nodes["a"], nodes["b"], uuid4())
    assert missing.status_code == 404 and missing.json()["code"] == "NOT_FOUND"
    other = api.tenant()
    other_site = other.sites["S1"]
    other_created = api.client.post(
        "/api/v1/vehicles",
        headers=other.admin.headers,
        json={
            "site_id": str(other_site),
            "vehicle_category_id": next(
                row["vehicle_category_id"]
                for row in api.client.get("/api/v1/vehicle-categories", headers=other.admin.headers).json()
                if row["is_active"]
            ),
            "fleet_number": "FOREIGN-1",
        },
    )
    assert other_created.status_code == 201, other_created.text
    foreign = _preview(
        api.client, ops.headers, site, revision, nodes["a"], nodes["b"], other_created.json()["vehicle_id"]
    )
    assert foreign.status_code == 404 and foreign.json()["code"] == "NOT_FOUND"
    # Véhicule du tenant mais garé sur un autre site : problème de permission.
    moved = api.client.post(
        "/api/v1/vehicles",
        headers=tenant.admin.headers,
        json={
            "site_id": str(tenant.sites["S2"]),
            "vehicle_category_id": next(
                row["vehicle_category_id"]
                for row in api.client.get("/api/v1/vehicle-categories", headers=tenant.admin.headers).json()
                if row["is_active"]
            ),
            "fleet_number": "PARKED-S2",
        },
    )
    assert moved.status_code == 201, moved.text
    parked = _preview(
        api.client, ops.headers, site, revision, nodes["a"], nodes["b"], moved.json()["vehicle_id"]
    )
    assert parked.status_code == 403 and parked.json()["code"] == "PERMISSION_DENIED"
    # Véhicule sans preuve technique : référence insoluble.
    bare = api.client.post(
        "/api/v1/vehicles",
        headers=tenant.admin.headers,
        json={
            "site_id": str(site),
            "vehicle_category_id": next(
                row["vehicle_category_id"]
                for row in api.client.get("/api/v1/vehicle-categories", headers=tenant.admin.headers).json()
                if row["is_active"]
            ),
            "fleet_number": "NO-PROFILE",
        },
    )
    assert bare.status_code == 201, bare.text
    unprofiled = _preview(
        api.client, ops.headers, site, revision, nodes["a"], nodes["b"], bare.json()["vehicle_id"]
    )
    assert unprofiled.status_code == 422 and unprofiled.json()["code"] == "REFERENCE_NOT_FOUND"
    assert any(d["field"] == "vehicle_id" for d in unprofiled.json()["details"])


def test_category_mismatch_fails_closed(api: Api) -> None:
    tenant, site, revision, nodes, vehicle, ops = _base(api)
    vehicle_category = api.client.get(f"{API}/vehicles/{vehicle}", headers=tenant.admin.headers).json()[
        "vehicle_category_id"
    ]
    active = [
        row["vehicle_category_id"]
        for row in api.client.get("/api/v1/vehicle-categories", headers=tenant.admin.headers).json()
        if row["is_active"]
    ]
    assert len(active) >= 2, "la recette exige au moins deux catégories actives"
    other_category = next(cid for cid in active if cid != vehicle_category)
    with new_session() as db:
        set_tenant_context(db, tenant.tenant_id)
        # mining_road_allowed_category est INSERT-only (RLS) : on change la
        # catégorie du véhicule pour rompre l'autorisation du tronçon.
        db.execute(
            text("UPDATE vehicle SET vehicle_category_id = :other WHERE tenant_id = :t AND vehicle_id = :v"),
            {"t": tenant.tenant_id, "v": vehicle, "other": other_category},
        )
        db.commit()
    resp = _preview(api.client, ops.headers, site, revision, nodes["a"], nodes["b"], vehicle)
    assert resp.status_code == 200, resp.text
    assert resp.json()["found"] is False
