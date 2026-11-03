"""Garde-fou statique : une reprise de données dans une migration doit voir les lignes de toutes les sociétés.

Les tables métier sont en RLS forcée, y compris pour le propriétaire `mf_owner` qui exécute les migrations :
sans société dans le contexte, un `DELETE` ou un `UPDATE` ne voit aucune ligne et ne fait rien, sans erreur.
Le retour arrière échouait ensuite sur une contrainte (ex. 0031 sur une base peuplée). Toute requête de
modification hors corps de fonction doit donc être précédée, dans le même script, de
`ALTER TABLE <t> NO FORCE ROW LEVEL SECURITY` ou d'une politique temporaire
`CREATE POLICY … ON <t> … TO mf_owner`.
"""

import re
from pathlib import Path

VERSIONS = Path(__file__).resolve().parents[1] / "alembic" / "versions"
DML = re.compile(r"^\s*(?:DELETE\s+FROM|UPDATE)\s+([a-z_]+)", re.IGNORECASE | re.MULTILINE)
FUNCTION_BODY = re.compile(r"\$(\w*)\$.*?\$\1\$", re.DOTALL)


def _uncovered(sql: str) -> list[str]:
    sql = FUNCTION_BODY.sub("", sql)
    problems = []
    for match in DML.finditer(sql):
        table = match.group(1).lower()
        before = sql[: match.start()]
        no_force = re.search(rf"ALTER\s+TABLE\s+{table}\s+NO\s+FORCE\s+ROW\s+LEVEL\s+SECURITY", before, re.I)
        policy = re.search(rf"CREATE\s+POLICY\s+\w+\s+ON\s+{table}\b[^;]*\bTO\s+mf_owner", before, re.I)
        if not (no_force or policy):
            problems.append(table)
    return problems


def test_detector_flags_uncovered_dml() -> None:
    assert _uncovered("DELETE FROM fuel_stock_movement WHERE x;") == ["fuel_stock_movement"]
    assert _uncovered("ALTER TABLE t NO FORCE ROW LEVEL SECURITY;\nUPDATE t SET a = 1;") == []
    assert _uncovered("CREATE POLICY p ON t FOR UPDATE TO mf_owner USING (true);\nUPDATE t SET a = 1;") == []
    assert _uncovered("CREATE FUNCTION f() RETURNS void AS $$\nBEGIN\n  DELETE FROM t;\nEND $$;") == []


def test_migration_data_changes_bypass_forced_rls() -> None:
    offenders = {
        path.name: tables
        for path in sorted(VERSIONS.glob("[0-9]*.py"))
        if (tables := _uncovered(path.read_text(encoding="utf-8")))
    }
    assert offenders == {}
