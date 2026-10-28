"""Contrat RBAC et contrôle de concurrence pour la suspension préventive."""

from app.authz.matrix import load_matrix
from app.maintenance.router import router


def test_preventive_suspend_route_has_manage_permission() -> None:
    spec = load_matrix().permissions["maintenance.preventive.manage"]
    assert ("POST", "/preventive-plans/{plan_id}/suspend") in {
        (route.method, route.path) for route in spec.routes
    }
    matches = [
        route
        for route in router.routes
        if route.path == "/preventive-plans/{plan_id}/suspend" and "POST" in getattr(route, "methods", ())
    ]
    assert len(matches) == 1
    assert matches[0].permission == "maintenance.preventive.manage"
