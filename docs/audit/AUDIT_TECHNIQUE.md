# Audit technique — MINEFLEET 360

Date : 26 octobre 2026. Référence : `main`, commit `2e3b803b5c4227f8c17da9d2bd86570e07e3d844`.

## Conclusion

Un monolithe modulaire backend réel existe : organization, identity, authz, audit, fleet et workforce. Le MVP opérationnel n'est pas terminé : aucune interface, affectation, mission, rotation ou maintenance fonctionnelle. Préserver ce socle plutôt que recommencer.

## Périmètre et méthode

139 fichiers récupérés au commit figé, contenus vérifiés par empreinte Git, inventaire dans `preuves/INVENTAIRE.md`, index AST dans `preuves/INDEX_CODE.md`. Lecture des modèles, six migrations, contrats publics, routes, services, schémas, tests, configurations et documentation. Revues spécialisées sécurité, base et métier/frontend, suivant CLAUDE.md et les skills locaux security-review, test-quality, delivery-review. Les documents de revues précédents constituent du contexte, pas une preuve de réussite actuelle.

Le clone Git direct a échoué faute d'authentification CLI. Historique récent examiné via API GitHub : cadrage `3a92c05`, socle `5eb542a`, limitation/changement de mot de passe `433bf9d`, démo OVH `7613d31` et `14da906`, flotte/personnel `f7ad86f`, corrections QA/sécurité `6544deb`, `3b69246`, `2e3b803`. La copie locale est reconstruite; son commit initial local ne remplace pas l'historique distant.

## Vérification effective

Installation isolée Python 3.12.14 : `uv pip install --python .venv/bin/python -e './backend[dev]' pip-audit==2.10.1` réussie.

| Contrôle local, depuis backend | Résultat |
|---|---|
| `../.venv/bin/ruff check .` | Réussi |
| `../.venv/bin/ruff format --check .` | 69 fichiers conformes |
| `../.venv/bin/mypy app` | Réussi, 52 fichiers |
| `../.venv/bin/pip-audit --skip-editable --timeout 10` | Aucune vulnérabilité connue, paquet local éditable exclu |
| `../.venv/bin/pytest -q -x` avec variables synthétiques de test | Erreur de préparation : PostgreSQL localhost:5432 indisponible; aucun test métier validé localement |
| Conteneurs et migrations locales | Non exécutés : Docker/psql absents |

La première tentative pytest sans configuration a échoué sur les paramètres obligatoires. La seconde, configurée, confirme le blocage DB. Aucun de ces échecs ne prouve une régression métier.

Preuve distante indépendante : run [40261183198](https://github.com/skaba89/minefleet360/actions/runs/40261183198), même SHA, job backend 121373723432, journaux consultés : **1162 passed, couverture 92 %**, Ruff, mypy et pip-audit réussis. Extraits sélectionnés dans `preuves/CI_VERIFIEE.txt`. Pas de nouvelle exécution distante lancée par cet audit.

## Anomalies transversales

| ID | Gravité | Fichier/preuve | Impact | Correction proposée |
|---|---|---|---|---|
| MET-01 | Haute | organization/service.py:289-313 : `_site_blockers` retourne toujours `[]` | Désactivation d'un site contenant des ressources métier | Contrats flotte/personnel, gardes réelles et verrouillage cohérent |
| MVP-01 | Haute pour livraison | Inventaire complet sans frontend/package.json; LIVRAISON_TRANCHE_1B.md:52 | Aucun parcours utilisateur démontrable | Tranche UI intégrée aux API existantes |
| DOC-01 | Moyenne | docs/ARCHITECTURE.md:3,57; docs/PLAN_LOT1.md:3 affirment absence de code | Mauvaise lecture de l'avancement | Distinguer architecture cible, état courant et reste à faire |
| QA-01 | Moyenne | tests/conftest.py:30-65, fixtures DB et client autouse | Même les tests purs nécessitent une DB; vérification locale réduite | Séparer tests unitaires indépendants et intégration réelle, sans simuler RLS |

Les chemins backend du tableau sont relatifs à `backend/app/`. Voir les rapports spécialisés pour les autres anomalies et leurs corrections. Aucun secret réel utilisé, aucune production modifiée, aucune fonctionnalité supprimée. Audit large du snapshot, sans certification de sécurité exhaustive : charge, restauration, navigateur et contre-tests DB nouveaux restent à exécuter.
