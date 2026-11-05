# Suivi différentiel — 5 novembre 2026

Référence : `main@e2be9d7a184cff396d2a59f1da9804e4c4de343b`, comparé à l'audit
`docs/audit/PRODUCT_READINESS_SCORE.md` établi sur `main@000ee08`.
Ce document distingue les preuves disponibles dans le dépôt des validations non exécutées
indépendamment lors de sa rédaction.

## Score

**Référence auditée : 62/100 (ancienne révision). Nouveau score : non calculé.**
La grille originale est conservée. Les PR récentes améliorent les périmètres GPS,
maintenance et documentation, mais aucun point supplémentaire n'est attribué avant un
nouveau passage des critères et des preuves de tests sur la révision actuelle.
Ne pas assimiler le pourcentage de couverture des tests à un score de maturité produit.

## Écarts effectivement comblés depuis la référence

| Preuve | Domaine | Changement |
| --- | --- | --- |
| PR #337 et #339 | Maintenance | Finalisation de l'entretien sur relevés et évaluation manuelle d'échéances |
| PR #340 | GPS | Carte interactive MapLibre multi-engins, fond de carte auto-hébergeable |
| PR #341 | GPS | Cap mesuré et replay animé avec signalement des positions estimées |
| PR #342 | GPS | Alertes de vitesse et franchissement de zone à l'ingestion |
| PR #343 | Maintenance | Évaluation quotidienne des échéances et sonde de tâches planifiées |
| PR #344 | GPS | Alerte de perte de signal, balayage périodique |
| PR #345 | GPS | Préférences de notification e-mail/SMS, outbox et regroupement anti-avalanche |

Ces PR sont fusionnées dans l'historique de `main` à la révision de référence. Les
résultats de tests indiqués dans leurs descriptions ne remplacent pas un nouveau
contrôle de la CI ni un essai terrain.

## Restant à vérifier ou à réaliser

### GPS — P0
- Rafraîchissement toujours par interrogation toutes les 15 secondes ;
  mesurer la latence de bout en bout avant de choisir SSE ou WebSocket.
- Aucun boîtier de fournisseur réel validé ; exiger documentation protocolaire,
  mesures de terrain et tests d'ingestion avant de parler de compatibilité.
- Fond PMTiles de Guinée prévu, mais rendu réel non vérifié sur un serveur équipé.
- Notifications SMS : interface développée, fournisseur payant non sélectionné ;
  aucun SMS de production ne peut être présumé livré.

### Offline — P0
- Mode HSE existant ; missions, maintenance et carburant hors ligne non validés.
- Vérifier sur appareil réel le chiffrement local, l'expiration de session, la
  révocation des accès et la synchronisation après coupure.

### Sécurité et exploitation — P0 avant production
- Contrôles existants : Ruff (dont règles S), mypy, pytest, pip-audit, npm audit,
  essais d'isolation multi-tenant, MFA.
- Cette PR ajoute deux contrôles distincts : Bandit sur le code Python avec
  sévérité ET confiance élevées (blocage), et Gitleaks sur l'historique Git
  (blocage). Le rapport JSON Bandit est conservé 14 jours.
- Les découvertes de sévérité moyenne nécessitent un second passage explicite :
  ce premier filtre n'est **pas** une validation de sécurité complète.
- Les nouveaux jobs ne sont pas automatiquement des contrôles obligatoires
  de protection de `main` : après leur passage en vert, le propriétaire doit
  vérifier et renforcer la règle de protection, sans contourner les tests.
- Revue d'intrusion, avis juridique guinéen, sauvegardes/restaurations réelles,
  fournisseur d'e-mails de production et pilote client restent non validés.

### SaaS et produit — P1
- Abonnements, quotas, facturation et onboarding autonome encore absents de
  la matrice d'audit ; à réauditer avant implémentation.
- Tableaux de bord par rôle, planning atelier, copilote IA et bilinguisme
  encore partiels ou absents selon l'audit de référence.

## Contrôle de cette tranche

- Code modifié : `.github/workflows/security-static.yml` (CI dédiée).
- Aucune migration, route API, permission ou donnée client modifiée.
- Aucun test de bout en bout ou scan exécuté localement via le connecteur GitHub.
- Ne déclarer le lot prêt qu'après contrôles GitHub terminés et réussis ;
  toute erreur de scan doit être analysée et corrigée, non ignorée.
- Aucune fusion et aucun déploiement autorisés par cette documentation.

## Suivant, après validation CI

1. Mesurer la latence GPS actuelle et cartographier les chemins d'authentification.
2. Concevoir le flux SSE/WebSocket tenant/site-scope avec reconnexion et replay
   des événements, puis PR de code séparée avec tests RLS et E2E.
3. Tester les fonds PMTiles sur serveur et l'intégration d'un vrai traceur.
