# MINEFLEET 360

Plateforme web de gestion des flottes et opérations minières, conçue pour une exploitation multi-tenant et multi-site. Ce dépôt contient une application en développement actif, et non plus uniquement le kit de démarrage Claude Code.

> **État :** développement actif. La présence d'une fonctionnalité dans le dépôt ne vaut pas validation d'un déploiement de production. Vérifier la CI, les migrations, les sauvegardes, la sécurité et les essais terrain avant tout pilote.

## Architecture

- **API :** Python 3.12, FastAPI, SQLAlchemy, Alembic.
- **Données :** PostgreSQL/PostGIS ; politiques d'isolation tenant et site (RLS) selon les modules.
- **Interface :** React, TypeScript, Vite ; libellés en français.
- **Qualité :** GitHub Actions (lint Ruff, mypy, tests backend et couverture minimale de 85 %, audit des dépendances, tests/typecheck/build frontend).
- **Exploitation :** environnement de développement local documenté dans les scripts et sous-projets.

## Parcours présents dans le code

- Gestion des organisations/sites, identités, rôles, autorisations et journal d'audit.
- Flotte, conducteurs et affectations, missions et parcours de maintenance (consulter les écrans/API pour le périmètre exact).
- Géolocalisation : consultation des positions, partage volontaire depuis le navigateur d'un téléphone, provisioning d'une clé de traceur et ingestion JSON HTTPS. Un appareil propriétaire exige un adaptateur spécifique.
- Carburant : cuves, réceptions et sorties, demandes et décisions séparées, inventaires physiques, seuils et alertes, mesures de consommation/écarts, fournisseurs, commandes et livraisons partielles.

Pour les règles métier et les limites vérifiables :
- [Suivi GPS et interface](docs/LIVE_LOCATION_AND_INTERFACE.md)
- [Gestion carburant](docs/FUEL_INVENTORY.md)
- [Roadmap](docs/ROADMAP.md)

## Démarrer en local

### API et base

Voir les scripts PowerShell dans `scripts/` et la configuration de `infra/`. Préparer les variables d'environnement locales avant de lancer Docker Compose ; ne jamais publier les secrets. Les commandes de création d'administrateur et de données fictives doivent être exécutées uniquement dans l'environnement approprié.

### Interface

```powershell
cd frontend
npm ci
npm run dev
```

Ouvrir `http://localhost:5173`, avec l'API locale démarrée. Instructions et prérequis détaillés : [frontend/README.md](frontend/README.md).

## Contrôles qualité

```bash
cd backend
ruff check .
ruff format --check .
mypy app
pytest -q -p no:warnings --cov=app --cov-branch --cov-report=term-missing:skip-covered --cov-fail-under=85
```

```bash
cd frontend
npm ci
npm run typecheck
npm test
npm run build
```

La CI configure aussi une base PostgreSQL/PostGIS de test, les migrations et les audits de dépendances : [workflow CI](.github/workflows/ci.yml).

**Limite importante :** les tests navigateur Playwright nécessitent actuellement une pile locale et des données fictives ; ils ne sont pas exécutés automatiquement par le workflow CI décrit ci-dessus. Voir [les consignes E2E](frontend/README.md).

## Points à valider avant un déploiement réel

1. Exécuter et examiner la CI de la révision exacte à déployer ; corriger toutes les régressions.
2. Tester les migrations sur une copie représentative, les sauvegardes et une restauration complète.
3. Revoir les autorisations, l'isolation inter-tenant, les secrets et l'accès aux données de localisation.
4. Exécuter les tests navigateur de bout en bout et des essais GPS avec matériels et réseaux réels.
5. Documenter la conservation des données GPS, la supervision, les alertes et les procédures de reprise.

## Ressources de conception

Le dépôt conserve les instructions, agents et skills Claude Code pour assister les développements. Ces ressources ne remplacent ni le code, ni les tests, ni les revues de sécurité.
