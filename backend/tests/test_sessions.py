"""Écran « Mes sessions » : liste, révocation volontaire (own) et administrative (any).

Permissions identity.session.revoke_own/any — avant ce chantier elles étaient orphelines
(aucune route) : tout échec ici doit faire échouer la concordance YAML↔OpenAPI de test_authz_matrix.
"""

import uuid

import pytest

from tests.conftest import API, PASSWORD, Api, TenantFixture, bearer

COOKIE = "mf_refresh"


def login_cookie(api: Api, tenant: TenantFixture, email: str) -> str:
    """Connexion dédiée dont on capture le cookie de refresh avant la connexion suivante."""
    resp = api.client.post(
        f"{API}/auth/login",
        json={"workspace_code": tenant.code, "email": email, "password": PASSWORD},
    )
    assert resp.status_code == 200, resp.text
    value = resp.cookies.get(COOKIE)
    assert value, "cookie de refresh absent de la réponse de connexion"
    return value


def refresh_with(api: Api, cookie: str) -> int:
    return api.client.post(f"{API}/auth/refresh", cookies={COOKIE: cookie}).status_code


@pytest.mark.parametrize(
    ("method", "path"),
    [("get", "/me/sessions"), ("post", "/me/sessions/revoke-others")],
)
def test_sessions_exigent_l_authentification(api: Api, method: str, path: str) -> None:
    # Sans jeton : 401 avant même la vérification de permission.
    resp = getattr(api.client, method)(f"{API}{path}")
    assert resp.status_code == 401


def test_liste_marque_la_session_courante(api: Api) -> None:
    tenant = api.tenant()
    email = tenant.admin.email
    login_cookie(api, tenant, email)
    login_cookie(api, tenant, email)
    sessions = api.client.get(f"{API}/me/sessions", headers=tenant.admin.headers).json()
    assert len(sessions) >= 2
    assert sum(1 for s in sessions if s["is_current"]) == 1


def test_revoque_une_session_precise_et_invalide_son_refresh(api: Api) -> None:
    tenant = api.tenant()
    # Connexion ciblée : on conserve ses headers et son cookie pour la reconnaître dans la liste.
    resp = api.client.post(
        f"{API}/auth/login",
        json={"workspace_code": tenant.code, "email": tenant.admin.email, "password": PASSWORD},
    )
    assert resp.status_code == 200, resp.text
    headers_cible = bearer(resp.json()["access_token"])
    ancien_cookie = resp.cookies.get(COOKIE)
    assert ancien_cookie
    login_cookie(api, tenant, tenant.admin.email)  # une autre session, non ciblée

    sessions = api.client.get(f"{API}/me/sessions", headers=headers_cible).json()
    cible = next(s for s in sessions if s["is_current"])

    assert (
        api.client.post(
            f"{API}/me/sessions/{cible['auth_session_id']}/revoke", headers=tenant.admin.headers
        ).status_code
        == 204
    )

    restantes = api.client.get(f"{API}/me/sessions", headers=tenant.admin.headers).json()
    assert cible["auth_session_id"] not in {s["auth_session_id"] for s in restantes}
    assert len(restantes) >= 2  # la session des headers admin et l'autre connexion restent actives
    # La session révoquée ne peut plus se rafraîchir.
    assert refresh_with(api, ancien_cookie) == 401


def test_revoque_toutes_les_autres_sessions(api: Api) -> None:
    tenant = api.tenant()
    # La session courante des headers admin est celle créée par api.tenant() : capturer son cookie.
    cookie_courante = api.client.cookies.get(COOKIE)
    assert cookie_courante
    cookie1 = login_cookie(api, tenant, tenant.admin.email)
    cookie2 = login_cookie(api, tenant, tenant.admin.email)

    resp = api.client.post(f"{API}/me/sessions/revoke-others", headers=tenant.admin.headers)
    assert resp.status_code == 200
    revoked = resp.json()["revoked"]
    assert revoked >= 2
    restantes = api.client.get(f"{API}/me/sessions", headers=tenant.admin.headers).json()
    assert len(restantes) == 1
    assert restantes[0]["is_current"]
    assert refresh_with(api, cookie1) == 401
    assert refresh_with(api, cookie2) == 401
    # La session courante, conservée, peut toujours se rafraîchir.
    assert refresh_with(api, cookie_courante) == 200


def test_session_etrangere_indiscernable(api: Api) -> None:
    tenant = api.tenant()
    # Une session d'un autre tenant ne peut être ni listée ni révoquée (404 indiscernable).
    autre: TenantFixture = api.tenant(sites=())
    theirs = api.client.get(f"{API}/me/sessions", headers=autre.admin.headers).json()
    assert theirs, "l'autre tenant doit avoir au moins une session active"
    cible = theirs[0]["auth_session_id"]

    resp = api.client.post(f"{API}/me/sessions/{cible}/revoke", headers=tenant.admin.headers)
    assert resp.status_code == 404
    # La cible reste intacte côté propriétaire.
    still = api.client.get(f"{API}/me/sessions", headers=autre.admin.headers).json()
    assert cible in {s["auth_session_id"] for s in still}


def test_admin_revoque_les_sessions_d_un_utilisateur(api: Api) -> None:
    tenant = api.tenant()
    driver = api.user(tenant, "DRIVER", scope="SITE", site="S1")
    cookie_driver = login_cookie(api, tenant, driver.email)

    resp = api.client.post(f"{API}/users/{driver.user_id}/sessions/revoke", headers=tenant.admin.headers)
    assert resp.status_code == 200
    assert resp.json()["revoked"] >= 1
    assert refresh_with(api, cookie_driver) == 401

    # Utilisateur inconnu : 404 indiscernable (UUID aléatoire).
    inconnu = uuid.uuid4()
    assert (
        api.client.post(f"{API}/users/{inconnu}/sessions/revoke", headers=tenant.admin.headers).status_code
        == 404
    )

    # Un rôle sans identity.session.revoke_any est refusé (403 audité).
    hr = api.user(tenant, "HR", scope="TENANT")
    resp_hr = api.client.post(f"{API}/users/{driver.user_id}/sessions/revoke", headers=hr.headers)
    assert resp_hr.status_code == 403
    assert resp_hr.json()["code"] == "PERMISSION_DENIED"


def test_revocations_sont_auditees(api: Api) -> None:
    tenant = api.tenant()
    driver = api.user(tenant, "DRIVER", scope="SITE", site="S1")
    api.client.post(f"{API}/users/{driver.user_id}/sessions/revoke", headers=tenant.admin.headers)
    api.client.post(f"{API}/me/sessions/revoke-others", headers=tenant.admin.headers)

    events = api.client.get(
        f"{API}/audit-events", headers=tenant.admin.headers, params={"action": "user.revoke_user_sessions"}
    ).json()
    assert any(str(driver.user_id) == (e.get("entity_id") or "") for e in events["items"])
    own = api.client.get(
        f"{API}/audit-events", headers=tenant.admin.headers, params={"action": "user.revoke_own_session"}
    ).json()
    assert own["total"] >= 1
