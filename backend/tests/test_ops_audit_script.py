"""Garde-fou CI : le script d'audit staging est strictement en lecture seule.

`infra/deploy/audit-staging-readonly.sh` rejoue la phase A du runbook
`docs/ops/RECETTE_STAGING_VALIDATION.md`. Ce test verrouille sa portée : syntaxe
valide, aucun ordre mutateur dans le corps du script, garde MF_ENV=staging
présente et mode plan proposé. Toute tentative d'y glisser une mutation (apply,
rollback, compose up/down/pull, backup, DDL/DML) doit faire échouer la CI.
"""

import subprocess
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "infra" / "deploy" / "audit-staging-readonly.sh"

# Aucun de ces fragments ne doit apparaître dans le corps du script (lecture seule par construction).
INTERDITS = (
    "staging-release.sh apply",
    "staging-release.sh rollback",
    "compose up",
    "compose down",
    "compose pull",
    "bash backup.sh",
    "upload-offsite-backup.sh",
    "alembic downgrade",
    "alembic upgrade",
    "DROP ",
    "TRUNCATE",
    "DELETE FROM",
    "INSERT INTO",
    "UPDATE app.",
    "systemctl start",
    "systemctl stop",
    "systemctl restart",
    "verify-restore.sh",
)


def test_script_exists_and_parses() -> None:
    assert SCRIPT.is_file(), SCRIPT
    # Entrée de confiance : chemin statique du dépôt, exécution sans shell (noqa justifiée).
    subprocess.run(["/bin/bash", "-n", str(SCRIPT)], check=True)  # noqa: S603


def test_script_contains_no_mutation_command() -> None:
    body = SCRIPT.read_text(encoding="utf-8")
    # Seul le code exécutable est inspecté : l'en-tête documente les interdits et cite
    # légitimement les commandes interdites ; un ordre mutateur dans du CODE doit échouer.
    code_only = "\n".join(line for line in body.splitlines() if not line.lstrip().startswith("#"))
    for interdit in INTERDITS:
        assert interdit not in code_only, f"ordre mutateur interdit présent : {interdit!r}"


def test_script_guards_configuration_and_offers_plan_mode() -> None:
    body = SCRIPT.read_text(encoding="utf-8")
    # Garde de mire : refuse de tourner ailleurs que sur staging (même contrôle que la release).
    assert "MF_ENV=" in body  # la valeur est lue depuis .env.prod, jamais codée en dur
    assert '!= "staging"' in body
    # Mode plan : la vérification de portée ne doit rien exécuter.
    assert "--plan" in body
    assert "bash -c" in body  # exécution différée (aucune substitution au moment du plan)
    # Le .env.prod n'est jamais affiché (aucun secret dans le rapport).
    assert "cat .env.prod" not in body and "source .env.prod" not in body
