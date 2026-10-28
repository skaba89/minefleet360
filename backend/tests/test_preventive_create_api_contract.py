"""Contrat RBAC de l'API de création des plans préventifs."""

from app.authz.matrix import load_matrix
from app.maintenance.router import router


def test_preventive_create_route_has_dedicated_permission() -> None:
    spec = load_matrix().permissions["maintenance.preventive.manage"]
    assert spec.grants == {"OPS_MANAGER": ("TENANT", "SITE"), "WORKSHOP_CHIEF": ("TENANT", "SITE")}
    matches = [
        route
        for route in router.routes
        if route.path == "/preventive-plans" and "POST" in getattr(route, "methods", ())
    ]
    assert len(matches) == 1
    assert matches[0].permission == "maintenance.preventive.manage"
