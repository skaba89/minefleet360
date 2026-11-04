# Audit d'architecture

État au 4 novembre 2026, `main@000ee08`. Il complète `docs/ARCHITECTURE.md`.

## Constat

| Élément | État | Appréciation |
|---|---|---|
| Monolithe modulaire FastAPI | 16 modules métier, routeurs sécurisés (`SecuredRoute`), matrice d'autorisations unique | **adapté** : rien ne justifie aujourd'hui des microservices |
| PostgreSQL 16 + PostGIS | 58 migrations Alembic, contraintes riches, RLS forcée | **point fort** : l'intégrité est garantie en base, pas seulement dans le code |
| Contrat d'API | OpenAPI exporté ; types TypeScript générés et vérifiés en CI | **point fort** |
| Frontend React/TypeScript + TanStack Query | 42 pages, client typé, PWA | correct ; pas de design system formalisé ni d'i18n |
| Temps réel | interrogation périodique (15 s) des dernières positions | **suffisant pour la démo**, limite pour un centre de contrôle (latence, charge) |
| Ingestion GPS | requête HTTP synchrone par position, idempotence par séquence | correcte jusqu'à quelques centaines de traceurs ; aucune file d'attente |
| Stockage GPS | table unique, index par engin et date, purge de rétention | à partitionner par mois au-delà de quelques dizaines de millions de positions |
| Tâches planifiées | timers systemd (digest HSE, supervision) | pas de planificateur applicatif ; la tâche quotidienne préventive devra suivre ce modèle |
| Observabilité | journaux JSON, sondes de santé | pas de métriques ni de traces |
| Performance | mesurée (`PERFORMANCE_DEMO.md`) : ~44 req/s avec 2 processus, CPU Python limitant | levier : nombre de processus (`MF_API_WORKERS`), puis optimisation par écran |

## Recommandations (justifiées par une mesure ou un besoin)

1. **Temps réel GPS** : diffuser les positions par Server-Sent Events (une seule connexion HTTP sortante, sans
   dépendance nouvelle côté serveur) quand la carte temps réel sera livrée. À mesurer : latence de bout en bout et
   nombre de connexions par processus. Un broker (Redis, NATS) n'est justifié qu'au-delà d'un processus API par
   machine.
2. **Partitionnement des positions** : à déclencher sur mesure (volumétrie mensuelle de la première exploitation
   réelle), pas avant.
3. **Observabilité** : OpenTelemetry (traces + métriques HTTP et SQL) quand une instance de production existera,
   pour mesurer les SLO réels.
4. **Pas de nouvelle dépendance** sans mesure ou exigence : chaque ajout (fond de carte, broker, IA) passera par une
   décision documentée (coût, licence, exploitation).
