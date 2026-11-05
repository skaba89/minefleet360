# État vérifié de MineFleet 360 — 5 novembre 2026

> **Source de vérité :** code et PR fusionnées de `main@1d780d7` (#357).
> Photo prise avant les modifications de la branche courante. Les contrôles de CI sur
> `main` doivent être reconsultés pour vérifier leur résultat final.
> Cette page remplace la photographie du 2 novembre qui décrivait #309 comme ouverte.

## GitHub et qualité

- Les PR #348 à #357 sont fusionnées dans `main` ; aucune PR ouverte lors de l'observation.
- Dernière PR #357 : les sept contrôles de la PR sont réussis, après correction des tests frontend.
- La suite backend dépasse le seuil de couverture de 85 % dans les journaux vérifiés précédemment,
  mais la couverture exacte du HEAD actuel n'est **pas** attestée ici.
- GitHub Actions : vérification des types et build frontend, lint/mypy/tests backend, navigateur,
  isolation multi-tenant, parcours démo, scans SAST et secrets.
- Les scripts de sauvegarde, restauration, préproduction et supervision existent dans
  `infra/deploy/` : leur présence dans le dépôt **ne prouve pas** leur exécution sur VPS.

## Fonctionnalités présentes dans le code

| Domaine | État du code | Validation manquante |
|---|---|---|
| Multi-tenant, sites, comptes, RBAC, MFA, RLS, audit | Avancé et testé | audit externe et recette multi-organisations réelle |
| Parc, véhicules, conducteurs, affectations | Avancé et testé | recette métier sur flotte réelle |
| Missions, dispatch, pesées | Avancé et testé | exploitation minière et concurrence sous charge |
| Maintenance, préventif, coûts et fiabilité | Avancé | rapprochement et validation des coûts réels |
| Pièces, magasins, stocks, pneus | Avancé | inventaire et rapprochement physique |
| Carburant, achats, inventaires | Avancé | intégrations stations/pompes réelles |
| HSE, inspections, incidents, hors-ligne | Avancé | essais terrain et conformité locale |
| GPS téléphone et traceurs | Ingestion authentifiée, carte, vitesse, alertes, historique | traceur réel, réseau mobile, latence p95 |
| SSE GPS événementiel | PostgreSQL LISTEN/NOTIFY, revalidation RLS, tests de fan-out | multi-processus/multi-machines, charge réelle et résilience |
| GPS téléphone temporairement hors ligne | Tampon RAM 12 points / 100 s, reprise séquentielle, purge à l'arrêt | synchronisation durable sécurisée et tests Android écran verrouillé |
| Contrats, assurances | Socle structuré | cycle documentaire et gouvernance complète |
| Sous-traitants, SLA, rentabilité par mission | Partiel ou absent selon le parcours | implémentation et validation métier |

## Score et interprétation

- **70,3/100** : seul score détaillé formalisé dans `MATURITY_SCORECARD.md` au 30 octobre,
  désormais **obsolète** pour les fonctionnalités HSE, pièces/pneus et GPS.
- **81/100** : estimation indicative discutée le 5 novembre à partir des progrès de code ;
  **ce n'est pas une mesure indépendante ni une certification de production**.
- Une vraie nouvelle note doit être calculée à partir d'une grille avec preuves par capacité,
  tests exécutés sur le HEAD, essais terrain, restauration, sécurité et qualité opérationnelle.

## NO-GO pour la commercialisation et le déploiement large sans preuves supplémentaires

1. Pilote terrain avec consentement, traceurs réels et Android sur réseau guinéen intermittent.
2. Essai multi-processus GPS avec objectifs de latence p95, capacité et dégradations mesurées.
3. Restauration effective de sauvegarde isolée, RPO/RTO publiés et alerting testé.
4. Contrôles de rétention GPS/HSE, confidentialité et obligations locales validés.
5. Recette de bout en bout sur véritables processus miniers, stocks, carburant et maintenance.

**État d'un déploiement VPS : non vérifié depuis GitHub.** Les fichiers et les notes d'un
déploiement ancien ne suffisent pas à confirmer que le commit courant est en production.

## Étape de consolidation active

La branche `fix/gps-phone-expiry-and-status-20261105` sécurise l'arrêt de la collecte
GPS après expiration de la session de partage, avec test de non-régression, et actualise
cette photographie. La branche reste soumise aux mêmes contrôles CI que les PR précédentes.
