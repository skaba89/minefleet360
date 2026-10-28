"""Génère frontend/src/lib/permissions.generated.ts depuis backend/app/authz/authz_matrix.yaml.

L'interface n'affiche que les actions autorisées ; elle ne doit jamais diverger de la matrice serveur
(revue SEC1C). Usage : `python scripts/gen_permissions.py` (écrit) ou `--check` (échoue si périmé, CI).
"""

import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
MATRIX = ROOT / "backend" / "app" / "authz" / "authz_matrix.yaml"
TARGET = ROOT / "frontend" / "src" / "lib" / "permissions.generated.ts"


def render() -> str:
    permissions = yaml.safe_load(MATRIX.read_text(encoding="utf-8"))["permissions"]
    grants = {
        name: {role: list(scopes) for role, scopes in sorted((spec.get("grants") or {}).items())}
        for name, spec in sorted(permissions.items())
        if spec["tranche"] != "later" or name in {"maintenance.preventive.manage", "maintenance.preventive.read"}
    }
    body = json.dumps(grants, indent=2, ensure_ascii=False)
    return (
        "// FICHIER GÉNÉRÉ par scripts/gen_permissions.py depuis backend/app/authz/authz_matrix.yaml.\n"
        "// Ne pas modifier à la main : relancer le script après tout changement de la matrice.\n"
        f"export const GRANTS = {body} as const satisfies Record<string, Record<string, readonly string[]>>;\n\n"
        "export type Permission = keyof typeof GRANTS;\n"
    )


def main() -> int:
    content = render()
    if "--check" in sys.argv:
        current = TARGET.read_text(encoding="utf-8") if TARGET.exists() else ""
        if current.replace("\r\n", "\n") != content:
            import difflib

            print("".join(difflib.unified_diff(current.splitlines(keepends=True), content.splitlines(keepends=True), fromfile="committed", tofile="expected")), file=sys.stderr)
            print(f"{TARGET} est périmé : lancer python scripts/gen_permissions.py", file=sys.stderr)
            return 1
        return 0
    TARGET.write_text(content, encoding="utf-8", newline="\n")
    print(f"écrit : {TARGET.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
