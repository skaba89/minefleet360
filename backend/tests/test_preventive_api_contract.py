"""Contrat API de consultation préventive et vérification de la matrice RBAC."""

from app.authz.matrix import load_matrix
from app.main import create_app


def test_preventive_read_routes_registered_and_protected() -> None:
    matrix = load_matrix()
    routes = matrix.route_permissions()
    paths = (
        "/vehicles/{vehicle_id}/preventive-plans",
        "/vehicles/{vehicle_id}/preventive-dues",
    )
    for path in paths:
        assert routes[("GET", path)] == "maintenance.preventive.read"
    app = create_app()
    registered = {(method, route.path) for route in app.routes for method in getattr(route, "methods", ())}
    for path in paths:
        assert ("GET", "/api/v1" + path) in registered


def test_preventive_read_denies_unlisted_roles() -> None:
    grants = load_matrix().permissions["maintenance.preventive.read"].grants
    assert "DRIVER" not in grants
    assert "FINANCE" not in grants
    assert grants["DISPATCHER"] == ("SITE",)
