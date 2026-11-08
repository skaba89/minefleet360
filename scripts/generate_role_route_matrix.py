"""Génère docs/qa/ROLE_PAGE_ACTION_MATRIX.md depuis les sources de vérité du dépôt.

Sources :
  - backend/app/authz/authz_matrix.yaml : rôles, permissions, routes API, grants (source machine RBAC) ;
  - frontend/src/App.tsx : routes React Router (parsées par expression régulière) ;
  - frontend/src/components/Layout.tsx et frontend/src/pages/AdminPages.tsx : entrées de menu
    (carte statique ci-dessous, revérifiée par --check contre le texte des fichiers).

Usage : `python scripts/generate_role_route_matrix.py` (écrit) ou `--check` (échoue si périmé, CI).
Le script ne modifie que le document généré ; il ne juge pas l'exactitude fonctionnelle (voir §Limites).
"""

import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
MATRIX = ROOT / "backend" / "app" / "authz" / "authz_matrix.yaml"
APP_TSX = ROOT / "frontend" / "src" / "App.tsx"
LAYOUT_TSX = ROOT / "frontend" / "src" / "components" / "Layout.tsx"
ADMIN_TSX = ROOT / "frontend" / "src" / "pages" / "AdminPages.tsx"
TARGET = ROOT / "docs" / "qa" / "ROLE_PAGE_ACTION_MATRIX.md"

# Carte des entrées de menu réelles du code UI (Layout.tsx l.28-73, AdminPages.tsx l.52-62).
# rule: "any" = au moins une permission suffit (comportement Layout) ; site_scoped = can(..., siteId).
MENU_ENTRIES: list[dict[str, object]] = [
    {
        "path": "/plateforme/societes",
        "label": "Sociétés clientes",
        "domain": "Plateforme",
        "permissions": ["organization.tenant.list"],
        "rule": "any",
        "site_scoped": False,
        "source": "Layout.tsx:29",
    },
    {
        "path": "/plateforme/nouvelle-societe",
        "label": "Nouvelle société",
        "domain": "Plateforme",
        "permissions": ["organization.tenant.create"],
        "rule": "any",
        "site_scoped": False,
        "source": "Layout.tsx:30",
    },
    {
        "path": "/plateforme/etat",
        "label": "État des services",
        "domain": "Plateforme",
        "permissions": ["organization.tenant.list"],
        "rule": "any",
        "site_scoped": False,
        "source": "Layout.tsx:31",
    },
    {
        "path": "/vehicules",
        "label": "Véhicules",
        "domain": "Flotte",
        "permissions": ["fleet.vehicle.read"],
        "rule": "any",
        "site_scoped": False,
        "source": "Layout.tsx:32",
    },
    {
        "path": "/vehicules/echeances",
        "label": "Échéances documents",
        "domain": "Flotte",
        "permissions": ["fleet.document.read"],
        "rule": "any",
        "site_scoped": False,
        "source": "Layout.tsx:33",
    },
    {
        "path": "/flotte-gps",
        "label": "Flotte GPS",
        "domain": "GPS",
        "permissions": ["fleet.vehicle.read"],
        "rule": "any",
        "site_scoped": False,
        "source": "Layout.tsx:34",
    },
    {
        "path": "/flotte-gps/zones",
        "label": "Zones GPS",
        "domain": "GPS",
        "permissions": ["fleet.geofence.read"],
        "rule": "any",
        "site_scoped": False,
        "source": "Layout.tsx:35",
    },
    {
        "path": "/flotte-gps/alertes",
        "label": "Alertes GPS",
        "domain": "GPS",
        "permissions": ["fleet.gps_alert.read"],
        "rule": "any",
        "site_scoped": False,
        "source": "Layout.tsx:36",
    },
    {
        "path": "/mon-suivi",
        "label": "Mon partage GPS",
        "domain": "GPS",
        "permissions": ["fleet.gps.share"],
        "rule": "any",
        "site_scoped": False,
        "source": "Layout.tsx:37",
    },
    {
        "path": "/conducteurs",
        "label": "Conducteurs",
        "domain": "RH terrain",
        "permissions": ["workforce.driver.read"],
        "rule": "any",
        "site_scoped": False,
        "source": "Layout.tsx:38",
    },
    {
        "path": "/affectations",
        "label": "Affectations",
        "domain": "RH terrain",
        "permissions": ["assignment.vehicle_assignment.read"],
        "rule": "any",
        "site_scoped": False,
        "source": "Layout.tsx:39",
    },
    {
        "path": "/missions",
        "label": "Missions",
        "domain": "Dispatch",
        "permissions": ["dispatch.mission.read"],
        "rule": "any",
        "site_scoped": False,
        "source": "Layout.tsx:40",
    },
    {
        "path": "/atelier",
        "label": "Atelier",
        "domain": "Maintenance",
        "permissions": ["maintenance.work_order.read"],
        "rule": "any",
        "site_scoped": False,
        "source": "Layout.tsx:41",
    },
    {
        "path": "/atelier/fiabilite",
        "label": "Fiabilité parc",
        "domain": "Maintenance",
        "permissions": ["maintenance.reliability.read"],
        "rule": "any",
        "site_scoped": False,
        "source": "Layout.tsx:42",
    },
    {
        "path": "/maintenance",
        "label": "Maintenance (préventif)",
        "domain": "Maintenance",
        "permissions": ["maintenance.preventive.read"],
        "rule": "any",
        "site_scoped": False,
        "source": "Layout.tsx:43",
    },
    {
        "path": "/carburant",
        "label": "Carburant",
        "domain": "Carburant",
        "permissions": [
            "fuel.stock.read",
            "fuel.stock.manage",
            "fuel.issue.request",
            "fuel.stocktake.record",
            "fuel.stock.threshold",
            "fuel.purchase.read",
            "fuel.purchase.create",
        ],
        "rule": "any",
        "site_scoped": False,
        "source": "Layout.tsx:44-55",
    },
    {
        "path": "/pneus",
        "label": "Pneus",
        "domain": "Maintenance",
        "permissions": ["maintenance.tyre.read"],
        "rule": "any",
        "site_scoped": False,
        "source": "Layout.tsx:56",
    },
    {
        "path": "/pieces",
        "label": "Pièces",
        "domain": "Maintenance",
        "permissions": ["maintenance.parts.read"],
        "rule": "any",
        "site_scoped": True,
        "source": "Layout.tsx:57",
    },
    {
        "path": "/hse",
        "label": "Sécurité (HSE)",
        "domain": "HSE",
        "permissions": [
            "hse.incident.read",
            "hse.incident.report",
            "hse.inspection.perform",
        ],
        "rule": "any",
        "site_scoped": False,
        "source": "Layout.tsx:58-65",
    },
    {
        "path": "/hse/inspections",
        "label": "Inspections HSE",
        "domain": "HSE",
        "permissions": ["hse.inspection.read", "hse.inspection.perform"],
        "rule": "any",
        "site_scoped": False,
        "source": "Layout.tsx:66",
    },
    {
        "path": "/hse/checklists",
        "label": "Checklists HSE",
        "domain": "HSE",
        "permissions": ["hse.checklist.manage"],
        "rule": "any",
        "site_scoped": False,
        "source": "Layout.tsx:67",
    },
    {
        "path": "/pesees",
        "label": "Pesées",
        "domain": "Dispatch",
        "permissions": ["dispatch.weighing.read"],
        "rule": "any",
        "site_scoped": False,
        "source": "Layout.tsx:68",
    },
    {
        "path": "/juridique",
        "label": "Contrats & assurances",
        "domain": "Juridique",
        "permissions": ["legal.contract.read", "legal.insurance.read"],
        "rule": "any",
        "site_scoped": True,
        "source": "Layout.tsx:69",
    },
    {
        "path": "/couts",
        "label": "Coût complet",
        "domain": "Pilotage",
        "permissions": ["cost.vehicle.read"],
        "rule": "any",
        "site_scoped": False,
        "source": "Layout.tsx:70",
    },
    {
        "path": "/indicateurs",
        "label": "Indicateurs",
        "domain": "Pilotage",
        "permissions": ["dispatch.indicators.read"],
        "rule": "any",
        "site_scoped": False,
        "source": "Layout.tsx:71",
    },
    {
        "path": "/administration",
        "label": "Administration",
        "domain": "Administration",
        "permissions": [
            "organization.site.create",
            "identity.user.read",
            "audit.event.read",
            "dispatch.location.manage",
            "dispatch.material.manage",
        ],
        "rule": "any",
        "site_scoped": False,
        "source": "Layout.tsx:72 + AdminPages.tsx:80-88",
    },
]

ADMIN_TABS: list[dict[str, object]] = [
    {
        "path": "/administration/sites",
        "label": "Administration · Sites",
        "domain": "Administration",
        "permissions": ["organization.site.create"],
        "rule": "any",
        "site_scoped": False,
        "source": "AdminPages.tsx:53",
        "source_token": 'to: "sites"',
    },
    {
        "path": "/administration/lieux-matieres",
        "label": "Administration · Lieux et matières",
        "domain": "Administration",
        "permissions": ["dispatch.location.manage", "dispatch.material.manage"],
        "rule": "any",
        "site_scoped": False,
        "source": "AdminPages.tsx:54-61",
        "source_token": 'to: "lieux-matieres"',
    },
    {
        "path": "/administration/documents-exiges",
        "label": "Administration · Documents exigés",
        "domain": "Administration",
        "permissions": ["fleet.vehicle_category.manage"],
        "rule": "any",
        "site_scoped": False,
        "source": "AdminPages.tsx:62",
        "source_token": 'to: "documents-exiges"',
    },
    {
        "path": "/administration/utilisateurs",
        "label": "Administration · Utilisateurs et rôles",
        "domain": "Administration",
        "permissions": ["identity.user.read"],
        "rule": "any",
        "site_scoped": False,
        "source": "AdminPages.tsx:63",
        "source_token": 'to: "utilisateurs"',
    },
    {
        "path": "/administration/journal",
        "label": "Administration · Journal d'audit",
        "domain": "Administration",
        "permissions": ["audit.event.read"],
        "rule": "any",
        "site_scoped": False,
        "source": "AdminPages.tsx:64",
        "source_token": 'to: "journal"',
    },
]

# Permissions attendues pour les routes de détail non couvertes par une entrée de menu (fiche X).
# "any" = la page est censée être accessible à au moins un des deux droits ; vérifié en E2E par rôle.
DETAIL_ROUTE_PERMISSIONS: dict[str, list[str]] = {
    "/vehicules/:vehicleId": ["fleet.vehicle.read"],
    "/conducteurs/:driverId": ["workforce.driver.read"],
    "/missions/:missionId": ["dispatch.mission.read"],
    "/atelier/:workOrderId": ["maintenance.work_order.read"],
    "/hse/:incidentId": ["hse.incident.read", "hse.incident.report"],
    "/hse/inspections/:inspectionId": ["hse.inspection.read", "hse.inspection.perform"],
    "/pneus/:tyreId": ["maintenance.tyre.read"],
    "/mon-compte/securite": [],  # page personnelle : tout compte authentifié (aucune permission)
    "*": [],  # 404 UI : toute session authentifiée (garde Protected)
}

# Sous-routes imbriquées : chemin JSX relatif -> préfixe réel dans l'URL finale.
CHILD_ROUTE_PREFIX: dict[str, str] = {
    "/sites": "/administration",
    "/lieux-matieres": "/administration",
    "/documents-exiges": "/administration",
    "/utilisateurs": "/administration",
    "/journal": "/administration",
}

ROUTE_RE = re.compile(r'<Route path="([^"]+)" element=\{<(\w+)')
UI_PUBLIC_ROUTES = {
    "/connexion",
    "/activation",
    "/reinitialisation",
    "/mot-de-passe-oublie",
}


def load_matrix() -> tuple[dict, dict]:
    data = yaml.safe_load(MATRIX.read_text(encoding="utf-8"))
    return data["roles"], data["permissions"]


def parse_ui_routes() -> list[tuple[str, str]]:
    routes = ROUTE_RE.findall(APP_TSX.read_text(encoding="utf-8"))
    return routes


def menu_visible(entry: dict[str, object], granted: set[str]) -> bool:
    permissions = set(entry["permissions"])  # type: ignore[arg-type]
    if not permissions:
        return True
    if entry["rule"] == "any":
        return bool(granted & permissions)
    return permissions <= granted


def render() -> str:
    roles, permissions = load_matrix()
    ui_routes = parse_ui_routes()
    layout_text = LAYOUT_TSX.read_text(encoding="utf-8") + ADMIN_TSX.read_text(
        encoding="utf-8"
    )
    role_names = list(roles.keys())

    # garde anti-dérive : la carte statique doit toujours correspondre aux fichiers sources.
    for entry in MENU_ENTRIES + ADMIN_TABS:
        token = entry.get("source_token", entry["path"])
        if token not in layout_text:
            raise SystemExit(f"entrée de menu absente des sources UI : {entry['path']}")
        for perm in entry["permissions"]:  # type: ignore[union-attr]
            if perm not in permissions:
                raise SystemExit(f"permission inconnue dans la matrice YAML : {perm}")
            if perm not in layout_text:
                raise SystemExit(f"permission absente des sources UI : {perm}")

    granted_by_role: dict[str, set[str]] = {role: set() for role in role_names}
    routes_by_permission: dict[str, list[str]] = {}
    for name, spec in permissions.items():
        for role in spec.get("grants") or {}:
            granted_by_role[role].update({name})
        for route in spec.get("routes") or []:
            routes_by_permission.setdefault(name, []).append(
                f"{route['method']} {route['path']}"
            )

    out: list[str] = []
    w = out.append
    w("# Matrice rôles × menus × routes × permissions (générée)")
    w("")
    w("- Document généré, sans horodatage pour rester déterministe (`--check` en CI).")
    w(
        "- Sources de vérité : `backend/app/authz/authz_matrix.yaml` (RBAC machine), "
        "`frontend/src/App.tsx` (routes), `frontend/src/components/Layout.tsx` + `frontend/src/pages/AdminPages.tsx` (menus)."
    )
    w(
        "- Vérification anti-dérive : `python scripts/generate_role_route_matrix.py --check`."
    )
    w("")
    w(
        "> **Portée et limites.** Ce document décrit ce que le code *autorise*, pas ce qui est *prouvé fonctionnel* : "
        "l'exécution navigateur par rôle est couverte par le workflow CI `e2e-isolation.yml` (jobs `tenant-isolation` "
        "et `demo-journeys`) et non par ce document. Une case « visible » signifie que la condition de menu du code "
        "est satisfaite par les grants du rôle ; la page peut ensuite renvoyer une erreur métier légitime (403/404)."
    )
    w("")

    # 1. Comptes et rôles
    w("## 1. Comptes et rôles")
    w("")
    w("| Rôle | Portées autorisées | Type de tenant | Assignable par le client |")
    w("|---|---|---|---|")
    for role, spec in roles.items():
        w(
            f"| `{role}` | {' / '.join(spec['allowed_scopes'])} | {spec['tenant_kind']} | "
            f"{'oui' if spec.get('assignable_by_tenant') else 'non'} |"
        )
    w("")
    w(
        "Rôles optionnels : "
        + ", ".join(f"`{r}`" for r, s in roles.items() if s.get("optional"))
        + "."
    )
    w("")

    # 2. Matrice rôles x menus
    w("## 2. Menus visibles par rôle (condition de menu du code × grants YAML)")
    w("")
    entries = MENU_ENTRIES + ADMIN_TABS
    header = "| Menu | Domaine |" + "".join(f" `{r}` |" for r in role_names)
    w(header)
    w("|---|---|" + "---|" * len(role_names))
    for entry in entries:
        row = f"| [{entry['label']}]({entry['path']}) | {entry['domain']} |"
        for role in role_names:
            row += f" {'✓' if menu_visible(entry, granted_by_role[role]) else '—'} |"
        w(row)
    w("")
    w(
        "Pages toujours accessibles à tout compte authentifié : Accueil (`/`), Mon compte · sécurité "
        "(`/mon-compte/securite`), déconnexion. L'accueil s'adapte au rôle (vue plateforme, tableau de bord flotte "
        "ou liste des rôles du compte)."
    )
    w("")

    # 3. Routes UI
    w("## 3. Routes UI protégées (`frontend/src/App.tsx`)")
    w("")
    w("| Route | Composant | Permission(s) attendue(s) |")
    w("|---|---|---|")
    for raw_path, component in ui_routes:
        path = raw_path if raw_path == "*" else f"/{raw_path.lstrip('/')}"
        display = (
            CHILD_ROUTE_PREFIX.get(path, "") + path
            if path in CHILD_ROUTE_PREFIX
            else path
        )
        if path in UI_PUBLIC_ROUTES:
            w(f"| `{display}` | `{component}` | publique (non authentifié) |")
            continue
        perms = DETAIL_ROUTE_PERMISSIONS.get(path)
        if perms is None:
            match = [e for e in entries if e["path"] == display]
            perms = list(match[0]["permissions"]) if match else []  # type: ignore[index]
        if not perms:
            label = (
                "toute session authentifiée"
                if component in {"AdminLayout", "NotFoundPage", "SecurityPage"}
                else "détail imbriqué (cf. parent)"
            )
            w(f"| `{display}` | `{component}` | {label} |")
        else:
            w(
                f"| `{display}` | `{component}` | {' ou '.join(f'`{p}`' for p in perms)} |"
            )
    w("")
    w(
        "Route attrape-tout `*` : page « Page introuvable » (404 UI) dans le shell authentifié ; "
        "les routes publiques inconnues sont redirigées vers `/connexion` par la garde `Protected`."
    )
    w("")

    # 4. Permissions et routes API
    w("## 4. Permissions API : routes et rôles accordés")
    w("")
    w("| Permission | Tranche | Routes API | Rôles accordés |")
    w("|---|---|---|---|")
    for name, spec in permissions.items():
        routes = routes_by_permission.get(name, [])
        granted = ", ".join(
            f"`{r}`" for r, _s in sorted((spec.get("grants") or {}).items())
        )
        route_text = (
            "<br>".join(f"`{r}`" for r in routes) if routes else "*(aucune route)*"
        )
        w(
            f"| `{name}` | {spec.get('tranche', '?')} | {route_text} | {granted or '—'} |"
        )
    w("")

    # 5. Compteurs par rôle
    w("## 5. Couverture par rôle")
    w("")
    w("| Rôle | Permissions | Routes API accessibles |")
    w("|---|---:|---:|")
    for role in role_names:
        perms = granted_by_role[role]
        route_count = sum(len(routes_by_permission.get(p, [])) for p in perms)
        w(f"| `{role}` | {len(perms)} | {route_count} |")
    w("")

    # 6. Anomalies détectées mécaniquement
    w("## 6. Anomalies détectées mécaniquement")
    w("")
    orphan = [n for n, s in permissions.items() if not (s.get("routes") or [])]
    later_with_routes = [
        n
        for n, s in permissions.items()
        if s.get("tranche") == "later" and (s.get("routes") or [])
    ]
    w(
        f"- Permissions déclarées sans route : {', '.join(f'`{n}`' for n in orphan) if orphan else 'aucune'}."
    )
    w(
        f"- Permissions marquées `tranche: later` avec routes implémentées : "
        f"{', '.join(f'`{n}`' for n in later_with_routes) if later_with_routes else 'aucune'}."
    )
    w(
        "- `organization.tenant.list` porte aussi le GET item `/platform/tenants/{{tenant_id}}` "
        "(dénommage list/read assumé, documenté dans l'en-tête du YAML)."
    )
    w("")

    # 7. Contrats de test
    w("## 7. Contrats de test associés")
    w("")
    w(
        "- Générés depuis le YAML : `backend/tests/test_authz_matrix.py` (concordance route↔permission, refus 403 audité, "
        "portée site) et `frontend/src/lib/permissions.generated.ts` (garde CI `gen_permissions.py --check`)."
    )
    w(
        "- Exécution navigateur par rôle : `.github/workflows/e2e-isolation.yml` (9 specs `e2e/`, parcours démo par rôle "
        "`e2e-demo/`, smoke public `e2e-smoke/`, hors-ligne `e2e-field/`)."
    )
    w(
        "- Toute évolution de la matrice RBAC doit régénérer ce document (`--check` recommandé en CI frontend)."
    )
    w("")
    return "\n".join(out) + "\n"


def main() -> int:
    content = render()
    if "--check" in sys.argv:
        current = TARGET.read_text(encoding="utf-8") if TARGET.exists() else ""
        if current != content:
            import difflib

            print(
                "".join(
                    difflib.unified_diff(
                        current.splitlines(keepends=True),
                        content.splitlines(keepends=True),
                        fromfile="committed",
                        tofile="expected",
                    )
                ),
                file=sys.stderr,
            )
            print(
                f"{TARGET} est périmé : lancer python scripts/generate_role_route_matrix.py",
                file=sys.stderr,
            )
            return 1
        print("matrice à jour")
        return 0
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    TARGET.write_text(content, encoding="utf-8", newline="\n")
    print(f"écrit : {TARGET.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
