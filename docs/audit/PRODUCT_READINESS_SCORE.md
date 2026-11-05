# Score de maturité produit — 5 novembre 2026

Référence : `main@fd1820bb2b74c889bec126c51c6f41dda5bb08fa` (PR #361 fusionnée).  
Score : **70/100**, inchangé après ajout d'une preuve CI de restauration synthétique. La grille sépare l'état du dépôt des preuves d'exploitation. Voir la méthode, les domaines et les critères de notation dans [l'audit industriel](INDUSTRIAL_READINESS_2026.md).

## Comparaison datée

- **70/100** : note dépôt recalculée le 5 novembre après les PR GPS #340–#359. N'est ni certification ni score de commercialisation.
- **62/100** : ancienne base du 4 novembre (#338), cohérente avec l'état GPS avant carte multi-véhicules, alertes et SSE événementiel; elle n'est plus la note courante.
- **81/100** : estimation antérieure non certifiée, conservée comme historique, sans méthode indépendante ni preuves terrain associées.

Les trois workflows du HEAD sont verts et la CI restaure un dump synthétique. Aucune validation de traceur réel, restore d'une sauvegarde opérationnelle/distante, staging, SLA p95/p99, pilote ou conformité locale n'est incluse dans la note. Le score n'augmente pas : cette preuve ne démontre ni RPO/RTO ni reprise d'un environnement opérationnel.
