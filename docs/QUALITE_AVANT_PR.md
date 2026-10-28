# Contrôles obligatoires avant une Pull Request

Le pipeline `.github/workflows/ci.yml` reste la **source de vérité** : lint, format, types, migrations, isolation/RLS, tests, audits et frontend. Les contrôles locaux servent à éviter des PR rouges dues à des erreurs immédiates.

## Installation développeur
1. Installer Python 3.12 et créer un environnement virtuel pour `backend`.
2. Installer les dépendances de développement : `cd backend && pip install -e ".[dev]"`.
3. Installer Node.js 22, puis `cd frontend && npm ci`.
4. Facultatif (Mac/Linux/WSL ou Git Bash avec `bash` et outils backend disponibles) : `pip install pre-commit`, puis `pre-commit install` depuis la racine.

## Windows PowerShell
Depuis la racine du dépôt : `powershell -ExecutionPolicy Bypass -File scripts/check-before-pr.ps1`.
La commande s'arrête à la première erreur et retourne un échec. Une base PostgreSQL/PostGIS de test initialisée et les variables `MF_*` sont nécessaires aux tests backend. Ne pas utiliser une base de production.

## Correction automatique du format
Dans `backend` : `ruff check . --fix` puis `ruff format .`. Relancer `ruff check . && ruff format --check .` et tous les autres contrôles avant de pousser. Ne pas désactiver mypy, l'inventaire RBAC, les tests RLS ou les audits pour obtenir artificiellement une CI verte.

## Exigences avant fusion
- CI GitHub Actions verte sur le **dernier** commit de la PR.
- Revue sécurité pour les permissions, les migrations et les données multi-tenant.
- Aucun déploiement production implicite.
- Des tests temporels MFA/TOTP ne doivent pas dépendre du passage réel d'une fenêtre de 30 secondes.
- Les E2E Playwright demandent une pile dédiée et restent à exécuter selon `frontend/README.md` : la CI actuelle ne les lance pas.
- Sur un ordinateur sans tous les outils, la CI reste obligatoire ; signaler clairement les vérifications impossibles localement.
