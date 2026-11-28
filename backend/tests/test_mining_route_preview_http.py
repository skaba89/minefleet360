"""HTTP contract for the advisory draft route preview (Phase 8).

The service carries the depth (single MVCC snapshot, closures, explicit
unavailable result, no partial route); these checks pin the HTTP surface:
status codes, payloads, validations and the isolation of foreign revisions.
"""

from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.core.db import new_session
from app.core.tenancy import set_tenant_context
from tests.conftest import API, Api

DEPARTURE = "2026-11-20T08:00:00Z"
HORIZON = "2026-11-20T09:00:00Z"


def _base(api: Api):
    """One tenant with a two-node draft survey connected by a 110 m / 20 s segment."""
    tenant = api.tenant()
    site = tenant.sites["S1"]
    ops = api.user(tenant, "OPS_MANAGER", "SITE", site="S1")
    dispatcher = api.user(tenant, "DISPATCHER", "SITE", site="S1")
    hr = api.user(tenant, "HR", "TENANT")
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
        db.commit()
    return tenant, site, revision, nodes, ops, dispatcher, hr


def _preview(
    client: TestClient,
    headers: dict[str, str],
    site,
    revision,
    origin,
    destination,
    departure: str = DEPARTURE,
    horizon: str = HORIZON,
):
    return client.get(
        f"{API}/sites/{site}/mining/revisions/{revision}/route-preview",
        headers=headers,
        params={
            "origin_id": str(origin),
            "destination_id": str(destination),
            "departure": departure,
            "horizon": horizon,
        },
    )


def test_route_preview_found(api: Api) -> None:
    _tenant, site, revision, nodes, ops, _, _ = _base(api)
    resp = _preview(api.client, ops.headers, site, revision, nodes["a"], nodes["b"])
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["found"] is True
    assert body["nodes"] == [str(nodes["a"]), str(nodes["b"])]
    assert body["distance_m"] == 110 and body["duration_seconds"] == 20
    assert len(body["segment_ids"]) == 1


def test_route_preview_unavailable_is_explicit_and_partial_free(api: Api) -> None:
    _tenant, site, revision, _, ops, _, _ = _base(api)
    resp = _preview(api.client, ops.headers, site, revision, uuid4(), uuid4())
    assert resp.status_code == 200, resp.text
    assert resp.json() == {
        "found": False,
        "nodes": [],
        "segment_ids": [],
        "distance_m": None,
        "duration_seconds": None,
    }


def test_route_preview_unknown_revision_is_404(api: Api) -> None:
    _tenant, site, _, nodes, ops, _, _ = _base(api)
    resp = _preview(api.client, ops.headers, site, uuid4(), nodes["a"], nodes["b"])
    assert resp.status_code == 404 and resp.json()["code"] == "NOT_FOUND"


def test_route_preview_validations(api: Api) -> None:
    _tenant, site, revision, nodes, ops, _, _ = _base(api)
    cases = [
        # Origine et destination identiques : aucun itinéraire trivial n'a de sens.
        {"origin_id": nodes["a"], "destination_id": nodes["a"]},
        # Datetimes naïves refusées (convention audit router) : une fenêtre sans fuseau
        # ne peut pas filtrer des fermetures en timestamptz.
        {"origin_id": nodes["a"], "destination_id": nodes["b"], "departure": "2026-11-20T08:00:00"},
        {"origin_id": nodes["a"], "destination_id": nodes["b"], "horizon": "2026-11-20T09:00:00"},
        # Fenêtre inversée puis fenêtre au-delà du plafond de 92 jours (101 jours).
        {"origin_id": nodes["a"], "destination_id": nodes["b"], "departure": HORIZON, "horizon": DEPARTURE},
        {
            "origin_id": nodes["a"],
            "destination_id": nodes["b"],
            "horizon": "2027-03-01T09:00:00Z",
        },
    ]
    for case in cases:
        params = {
            "origin_id": str(case.get("origin_id", "")),
            "destination_id": str(case.get("destination_id", "")),
            "departure": case.get("departure", DEPARTURE),
            "horizon": case.get("horizon", HORIZON),
        }
        resp = api.client.get(
            f"{API}/sites/{site}/mining/revisions/{revision}/route-preview",
            headers=ops.headers,
            params=params,
        )
        assert resp.status_code == 422 and resp.json()["code"] == "VALIDATION_ERROR", (case, resp.text)


def test_route_preview_denied_without_permission(api: Api) -> None:
    _tenant, site, revision, nodes, _, _, hr = _base(api)
    resp = _preview(api.client, hr.headers, site, revision, nodes["a"], nodes["b"])
    assert resp.status_code == 403 and resp.json()["code"] == "PERMISSION_DENIED"


def test_route_preview_foreign_revision_is_indistinguishable(api: Api) -> None:
    _tenant, site, revision, _, _, _, _admin_holder = _base(api)
    other = api.tenant()
    other_admin = api.user(other, "TENANT_ADMIN", "TENANT")
    resp = _preview(api.client, other_admin.headers, site, revision, uuid4(), uuid4())
    assert resp.status_code == 404 and resp.json()["code"] == "NOT_FOUND"
