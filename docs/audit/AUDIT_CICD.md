# Audit CI/CD et exploitation

Commit `2e3b803`, 26 octobre 2026.

## CI vérifiée

`.github/workflows/ci.yml` : push main et pull requests; permissions contents:read; timeout 20 min; Python 3.12; service PostgreSQL/PostGIS; bootstrap des rôles; secrets éphémères; Ruff lint/format; mypy strict; pytest avec couverture branches et seuil 85 %; pip-audit. Le run [40261183198](https://github.com/skaba89/minefleet360/actions/runs/40261183198) du SHA audité est vert : 1162 tests, 92 % de couverture, scans réussis. Un run ancien `40209848138` a échoué, suivi de runs réussis; ne pas confondre ce passé avec l'état du snapshot.

La CI vérifie le backend sur base reconstruite. Elle ne valide ni frontend absent, ni déploiement/rollback, ni restauration, ni upgrade avec données préexistantes. Aucun workflow de CD production trouvé. Protection de branche, reviewers obligatoires et politique de fusion : non vérifiés, ne pas les supposer actifs.

## Conteneurs et démo

backend/Dockerfile : runtime non root (uid10001), dépendances directes épinglées. Compose démo : DB sans port publié, Caddy HTTPS, secrets propriétaire réservés au job migrate, API avec ses propres secrets. backup.sh applique umask077. Build, démarrage, restauration et accessibilité réseau non exécutés localement (Docker absent).

| ID | Gravité | Fichier et preuve | Impact | Correction proposée |
|---|---|---|---|---|
| OPS-01 / SEC-01 | Haute | infra/deploy/docker-compose.demo.yml, commande API --workers 2; core/ratelimit.py mémoire locale | Démo déjà multiworker malgré hypothèse une instance du limiteur | Limitation partagée; mesure provisoire explicite un worker, sans la considérer durable |
| CI-01 | Moyenne | ci.yml ne construit pas l'image runtime | CI verte sans preuve que l'image livrable fonctionne | Build runtime, smoke health/readiness et permissions non root |
| CI-02 | Moyenne | backend/pyproject.toml épingle directes; aucun lock de transitives dans inventaire | Résolution variable entre machines/dates | Lock reproductible avec hashes, mise à jour contrôlée et audit du lock |
| CI-03 | Moyenne | tests/conftest.py reconstruit la base vide | Upgrade réel non vérifié | Job/test d'upgrade peuplé avec rôle de migration réel |
| CI-04 | Moyenne | ci.yml sans rapports persistés de couverture/scans | Diagnostic et preuve historique dépendants des logs | Artifacts de couverture/JUnit/scans assainis, rétention définie |
| OPS-02 | Moyenne | infra/deploy/backup.sh sans scénario automatisé de restauration | Sauvegarde non démontrée exploitable | Test de restauration périodique isolée, RPO/RTO et stockage hors machine définis |
| CI-05 | Faible | checkout@v4, setup-python@v5 et images par tags | Références mutables, alerte runtime Node20 visible dans logs | Épingler actions/images par digest/SHA et automatiser mises à jour |

Aucun déploiement réalisé. Les configurations OVH sont une démonstration, pas une attestation de préparation production. Le transport email provisoire est détaillé dans AUDIT_SECURITE.md.
