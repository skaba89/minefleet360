"""Rejeu du score de maturité (docs/MATURITY_SCORECARD.md) — même grille, mêmes poids.

Rejoue la grille de l'audit du 30 octobre 2026 (main@3c4bb02, 70,3/100) sur l'état
courant de `main`. Chaque évolution de score citée dans le document correspond à
une entrée ci-dessous ; l'exécution vérifie que la base du 30 octobre retombe
exactement sur 73,4 / 56,7 / 76,5 -> 70,3 avant d'imprimer les nouveaux agrégats.

Usage : python3 scripts/replay_maturity_scorecard.py
"""

# (capacité, score 30 oct, score courant — rejeu du 13 novembre 2026, main@2cc3599)
FONCTIONNEL = [
    ("Sociétés et sites", 92, 92),
    ("Utilisateurs et permissions", 91, 91),
    ("Parc et véhicules", 88, 88),
    ("Conducteurs et habilitations", 86, 86),
    ("Affectations", 84, 84),
    ("Missions et rotations", 82, 82),
    ("Maintenance corrective/préventive", 78, 83),
    ("Carburant et achats", 83, 83),
    ("Documents réglementaires", 84, 86),
    ("GPS et géolocalisation", 75, 85),
    ("Pesées et production", 82, 82),
    ("Pièces et pneus", 20, 58),
    ("HSE", 25, 62),
    ("Reporting/tableaux de bord", 58, 65),
]
METIER_MINIER = [
    ("Opérations quotidiennes", 82, 84),
    ("Dispatching et transport", 82, 82),
    ("Gestion des équipements", 85, 85),
    ("Productivité/disponibilité", 65, 65),
    ("Maintenance des engins", 78, 82),
    ("Approvisionnements", 72, 78),
    ("Coût par équipement", 40, 60),
    ("Gestion des équipes", 55, 55),
    ("Prévention des incidents", 25, 62),
    ("Sous-traitants", 20, 20),
    ("Rentabilité des opérations", 20, 20),
]
TECHNIQUE = [
    ("Architecture", 86, 86),
    ("Qualité du code", 84, 85),
    ("Base de données", 88, 89),
    ("Sécurité", 87, 88),
    ("Isolation multi-tenant", 92, 93),
    ("Tests automatisés", 89, 91),
    ("CI/CD", 78, 82),
    # Performance +1 (13 nov, #438) : mesure de production de la qualité du suivi GPS
    # (GET /gps/metrics : latence d'ingestion p50/p95/p99, fraîcheur par engin, obsolescence),
    # même standard de preuve que le +1 du 12 nov (workflow de benchmark) — code, tests, CI.
    ("Performance", 70, 72),
    ("Sauvegarde/restauration", 58, 64),
    ("Observabilité", 52, 56),
    ("Interface utilisateur", 78, 82),
    ("Déploiement", 68, 71),
    ("Résilience", 64, 66),
]

WEIGHTS = {"fonctionnel": 0.40, "metier": 0.25, "technique": 0.35}
BASELINE = {"fonctionnel": 73.4, "metier": 56.7, "technique": 76.5}


def _avg(rows: list[tuple[str, int, int]], index: int) -> float:
    return sum(row[index] for row in rows) / len(rows)


def main() -> None:
    f0, f1 = _avg(FONCTIONNEL, 1), _avg(FONCTIONNEL, 2)
    m0, m1 = _avg(METIER_MINIER, 1), _avg(METIER_MINIER, 2)
    t0, t1 = _avg(TECHNIQUE, 1), _avg(TECHNIQUE, 2)

    # Contrôle : la colonne du 30 octobre doit retomber sur l'audit initial.
    for label, computed, expected in (
        ("fonctionnel", f0, BASELINE["fonctionnel"]),
        ("metier", m0, BASELINE["metier"]),
        ("technique", t0, BASELINE["technique"]),
    ):
        if abs(computed - expected) > 0.05:
            raise SystemExit(
                f"base du 30 octobre dérivée pour {label} : {computed:.1f} != {expected:.1f}"
            )

    g0 = (
        WEIGHTS["fonctionnel"] * f0 + WEIGHTS["metier"] * m0 + WEIGHTS["technique"] * t0
    )
    g1 = (
        WEIGHTS["fonctionnel"] * f1 + WEIGHTS["metier"] * m1 + WEIGHTS["technique"] * t1
    )

    print(f"Fonctionnel   : {f0:.1f} -> {f1:.1f}")
    print(f"Métier minier : {m0:.1f} -> {m1:.1f}")
    print(f"Technique     : {t0:.1f} -> {t1:.1f}")
    print(f"Global        : {g0:.1f} -> {g1:.1f} ({g1 - g0:+.1f})")
    for name, rows in (
        ("Fonctionnel", FONCTIONNEL),
        ("Métier minier", METIER_MINIER),
        ("Technique", TECHNIQUE),
    ):
        moved = [(cap, a, b) for cap, a, b in rows if a != b]
        print(f"{name} : {len(moved)} capacités modifiées")
        for cap, a, b in moved:
            print(f"  {cap}: {a} -> {b} ({b - a:+d})")


if __name__ == "__main__":
    main()
