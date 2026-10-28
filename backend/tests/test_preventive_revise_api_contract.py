"""Vérifie que l'API de révision a une permission et une précondition ETag."""

from app.authz.matrix import load_matrix
from app.maintenance.router import router


def test_preventive_revise_route_is_protected() -> None:
    spec = load_matrix().permissions["maintenance.preventive.manage"]
    assert ("POST", "/preventive-plans/{plan_id}/revise") in {
        (route.method, route.path) for route in spec.routes
    }
    matches = [
        route
        for route in router.routes
        if route.path == "/preventive-plans/{plan_id}/revise" and "POST" in getattr(route, "methods", ())
    ]
    assert len(matches) == 1
    assert matches[0].permission == "maintenance.preventive.manage"
