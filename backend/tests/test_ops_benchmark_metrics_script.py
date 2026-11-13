"""Garde-fou CI : la relève SLO GPS de recette est strictement en lecture seule.

`scripts/gps/benchmark_metrics.py` relève les agrégats de `GET /gps/metrics`
(prérequis n°6 du GO/NO-GO, mesure livrée par #438). Ce test verrouille sa
portée : syntaxe valide, aucune mutation (aucun verbe d'écriture HTTP, aucun
shell-out, aucune commande d'exploitation), garde MF_ENV=production, bornes de
fenêtre et jeton jamais affiché. Toute tentative d'y glisser une écriture doit
faire échouer la CI.
"""

import py_compile
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "gps" / "benchmark_metrics.py"

# Aucun de ces fragments ne doit apparaître dans le code du script (lecture seule par construction).
INTERDITS = (
    '"POST"',
    '"PUT"',
    '"DELETE"',
    '"PATCH"',
    "method=",
    "subprocess",
    "os.system",
    "eval(",
    "exec(",
    "alembic",
    "compose ",
    "systemctl",
    "docker ",
)


def test_script_exists_and_compiles() -> None:
    assert SCRIPT.is_file(), SCRIPT
    py_compile.compile(str(SCRIPT), doraise=True)


def test_script_contains_no_mutation_or_shellout() -> None:
    body = SCRIPT.read_text(encoding="utf-8")
    # Seul le code est inspecté : l'en-tête documente la portée et cite légitimement
    # les commandes interdites ; un ordre mutateur dans du CODE doit échouer.
    code_only = "\n".join(line for line in body.splitlines() if not line.lstrip().startswith("#"))
    for interdit in INTERDITS:
        assert interdit not in code_only, f"fragment interdit présent : {interdit!r}"


def test_script_guards_and_readonly_get() -> None:
    body = SCRIPT.read_text(encoding="utf-8")
    # Garde de mire : refus explicite en production (même convention que benchmark_latest).
    assert 'MF_ENV' in body and '== "production"' in body
    # URL validée (HTTPS hors localhost, sans identifiants) avant tout appel.
    assert "validate_base_url(url)" in body
    # Le jeton ne sert qu'à l'en-tête et n'est jamais affiché : aucune ligne print ne le mentionne.
    assert '{"Authorization": "Bearer " + token' in body
    print_lines = [line for line in body.splitlines() if "print(" in line]
    assert print_lines and all("token" not in line for line in print_lines)
    # Plafond de taille de réponse et bornes de fenêtre contractuelles (1..1440).
    assert "1_000_000" in body
    assert "1 <= minutes <= 1440" in body
    # Codes de sortie distincts : 2 sur refus d'authentification, 1 sur tout autre échec.
    assert "return 2" in body and "return 0 if failures == 0 else 1" in body
