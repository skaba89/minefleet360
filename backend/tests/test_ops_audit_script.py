"""Garde-fou CI : le script d'audit staging est strictement en lecture seule.

`infra/deploy/audit-staging-readonly.sh` rejoue la phase A du runbook
`docs/ops/RECETTE_STAGING_VALIDATION.md`. Ce test verrouille sa portée : syntaxe
valide, aucun ordre mutateur dans le corps du script, garde MF_ENV=staging
présente et mode plan proposé. Toute tentative d'y glisser une mutation (apply,
rollback, compose up/down/pull, backup, DDL/DML) doit faire échouer la CI.
"""

import re
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
    "UPDATE public.",
    "systemctl start",
    "systemctl stop",
    "systemctl restart",
    "verify-restore.sh",
    " run --rm",  # démarre un conteneur ; sans env de release, compose construit une image
    "compose build",
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


def test_a4_targets_public_schema_and_mirrors_global_tables() -> None:
    """Régression staging 2026-11-16 : les tables métier sont dans public, pas dans app.

    La liste blanche des tables hors RLS du script doit rester identique à GLOBAL_TABLES
    (test d'isolation de la base) : une table ajoutée d'un côté seulement fait échouer la CI.
    """
    body = SCRIPT.read_text(encoding="utf-8")
    assert "app.insurance_policy" not in body and "app.legal_contract" not in body
    assert "public.insurance_policy" in body and "public.legal_contract" in body
    assert 'grep -qx "A4 verdict : OK"' in body  # A4 échoue réellement sur écart

    script_match = re.search(r'^A4_GLOBAL_TABLES="([^"]+)"$', body, re.MULTILINE)
    assert script_match, "A4_GLOBAL_TABLES absent du script"
    script_tables = set(re.findall(r"'([a-z_]+)'", script_match.group(1)))

    database_test = SCRIPT.parents[2] / "backend" / "tests" / "test_database.py"
    block = re.search(r"GLOBAL_TABLES = \{(.*?)\n\}", database_test.read_text(encoding="utf-8"), re.S)
    assert block, "GLOBAL_TABLES introuvable dans test_database.py"
    expected = set(re.findall(r'"([a-z_]+)"', block.group(1)))
    assert script_tables == expected


def test_a2_reads_schema_revision_without_starting_a_container() -> None:
    """Régression staging 2026-11-16 : A2 construisait minefleet-api:local via `run --rm migrate`."""
    body = SCRIPT.read_text(encoding="utf-8")
    assert "SELECT version_num FROM alembic_version" in body
    assert "check_schema_revision" not in "\n".join(
        line for line in body.splitlines() if not line.lstrip().startswith("#")
    )


def test_a3_verifies_both_images_and_slsa_v1() -> None:
    body = SCRIPT.read_text(encoding="utf-8")
    for image in ("api", "web"):
        lines = [
            line
            for line in body.splitlines()
            if f"/{image}@sha256:" in line and "cosign verify" in line
        ]
        assert len(lines) == 2
        assert any("cosign verify --" in line for line in lines)
        assert any(
            "cosign verify-attestation --type https://slsa.dev/provenance/v1" in line for line in lines
        )
        assert all("release-images" in line for line in lines)


def test_release_workflow_signs_and_verifies_buildx_provenance() -> None:
    workflow = SCRIPT.parents[2] / ".github" / "workflows" / "release-images.yml"
    body = workflow.read_text(encoding="utf-8")
    assert "provenance: mode=max,version=v1" in body
    assert ".Provenance.SLSA" in body
    assert "buildDefinition" in body and "runDetails" in body
    assert "cosign attest --yes --type https://slsa.dev/provenance/v1" in body
    assert "cosign verify-attestation --type https://slsa.dev/provenance/v1" in body
    assert '--certificate-identity "$WORKFLOW_IDENTITY"' in body
