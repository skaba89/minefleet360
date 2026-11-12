# Protocole de pilote fermé — MineFleet 360

> Statut : **protocole prêt, exécution conditionnée** — aucun jalonnement ne démarre tant que les
> 8 conditions bloquantes du `docs/qa/GO_NO_GO.md` ne sont pas levées avec preuves datées
> (staging réel, coffre, isolation en recette, juridique, traceur physique, Android réel, SLO
> GPS, supervision éprouvée). Ce document prépare l'exécution ; il ne la remplace pas.
>
> Créé le 2026-11-12 (phase 7 de la feuille de route). Base produit : `main@404056c` — produit
> SaaS complet côté logiciel (4 lots de commercialisation livrés : plans/quotas #418,
> abonnements #419, facturation sans encaissement #420, quotas appliqués #422,
> support/onboarding/réversibilité #423).

## 1. Objectif et hors périmètre

**Objectif :** démontrer, sur un site minier réel et avec des données opérationnelles, que
MineFleet 360 couvre le cycle de gestion d'une flotte minière guinéenne (identité, sites,
véhicules, conducteurs, affectations, missions et pesées, atelier, préventif, carburant,
HSE, documents réglementaires, suivi GPS temps réel) **et** le cadre SaaS
(abonnement activé par la plateforme, limites du plan appliquées, facturation interne
sans encaissement, support opérationnel), sans incident de sécurité ni de donnée.

**Hors périmètre du pilote :** encaissement (aucun moyen de paiement — le règlement se gère
hors application pendant le pilote) ; promesse de disponibilité contractuelle (SLA) ; vente ;
déploiement multi-clients ; intégration ponts-bascules automatiques (les pesées restent
saisies via l'application ou l'API ; le lot 5 du plan initial reste séparé).

## 2. Conditions préalables (toutes avec preuve datée avant J0)

1. **Staging isolé** : phases A/B du runbook `docs/ops/RECETTE_STAGING_VALIDATION.md`
   exécutées et consignées (checklist readiness, migration+rollback), séquencées par le plan
   `docs/ops/PLAN_EXECUTION_STAGING.md`, puis C/D avec approbation explicite du propriétaire.
2. **Sauvegarde/restauration** : round-trip réel depuis le coffre retenu avec RPO/RTO mesurés, selon
   `docs/ops/PROTOCOLE_RESTAURATION_EXTERNE.md` (14 contrôles, incidents simulés, preuve R1 datée).
3. **Isolation** : suite croisée A/B (2 sociétés fictives + 1 société pilote) sur la recette
   réelle — le refus 404 neutre vérifié sur les routes cross-tenant, y compris les nouvelles
   routes SaaS (`overview`, `export`).
4. **Juridique** : notice de confidentialité GPS/salariés et conditions validées par un
   professionnel du droit guinéen ; consentement des conducteurs tracé (document signé
   archivé hors application, référence notée dans le journal).
5. **Traceur physique** : essai daté du modèle/firmware exact selon
   `docs/GPS_FOURNISSEUR_CAHIER.md` (adaptateur `minefleet-json-v1` seul admis) et le protocole
   `docs/qa/PROTOCOLE_ESSAI_GPS_PHYSIQUE.md` (banc L1–L9, terrain T1–T10, rapport de qualification).
6. **Android réel** : matrice d'appareils exécutée (au moins 2 appareils Android physiques,
   arrière-plan, réseau faible) selon `docs/qa/PROTOCOLE_ESSAI_ANDROID_REEL.md` (10 scénarios).
7. **SLO GPS** : benchmark sur staging avec seuils métier signés (p95/p99, taux d'erreur).
8. **Supervision** : un incident injecté sur staging, alerte reçue et acquittée, exercice
   consigné.

**Prérequis produit (fait, à revérifier à J0) :** CI verte sur le commit déployé ; migration
`alembic upgrade head` rejouée sur une copie ; compte `PLATFORM_ADMIN` opérationnel ;
socle SaaS vérifié (plan pilote créé, quotas visés, facturation DRAFT possible).

## 3. Périmètre fonctionnel et scénarios obligatoires

| Domaine | Scénarios obligatoires du pilote | Preuve attendue |
|---|---|---|
| Provisioning | création de la société pilote par la plateforme, invitation du `TENANT_ADMIN`, activation, checklist `/demarrage` à 100 % | journal d'audit + capture de la checklist |
| Plans/quotas | plan pilote avec limites (`max_users`, `max_vehicles`, `max_gps_trackers`), refus `QUOTA_EXCEEDED` constaté à la borne, libération par réforme/révocation constatée | journal + captures |
| Flotte | sites, véhicules, conducteurs, affectations, échéances documentaires | volumétrie journalisée |
| Missions/pesées | missions réelles, pesées saisies (pont-bascule manuel), corrections avec justification, indicateurs mesuré/à approuver séparés | export des indicateurs de fin de période |
| GPS temps réel | traceurs liés, SSE temps réel sur le site, zones, alertes acquittées, historique | mesures p95 côté serveur + retours terrain |
| Atelier/carburant | OT, pièces avec valorisation, réappro quatre-yeux, réceptions carburant | cohérence valorisation (rapprochement) |
| HSE | inspections, double regard, incident, offline terrain (Android réel) | journal offline + synchronisations |
| SaaS/abonnement | abonnement TRIAL→ACTIVE par la plateforme, statut effectif visible côté société, facture DRAFT→ISSUED (GNF, taxe), aucune action d'encaissement | facture exportée + journal |
| Support | utilisation effective de `/plateforme/support` par l'équipe plateforme pendant le pilote | journal d'exploitation |
| Réversibilité | export JSON hebdomadaire par le `TENANT_ADMIN`, vérification de lisibilité hors application | fichier exporté daté |

## 4. Client, site et volumétrie cibles (à consigner à l'approbation)

Champs à remplir **avant J0** par le responsable du pilote (ce protocole refuse les
généralités : chaque champ est une décision consignée) :

- Client pilote : `【nom du client】` — contact : `【nom, fonction】`.
- Site : `【site minier】` — fuseau `Africa/Conakry`, locale `fr-GN` (défauts produit).
- Volumétrie visée : `【p.ex. 1 site, 15 véhicules, 10 conducteurs, 8 traceurs, 20 utilisateurs】`
  (le plan pilote doit couvrir cette volumétrie avec une marge ≥ 20 %).
- Durée : `【p.ex. 45 jours calendaires】` — jalons J0, J+7 (onboarding complet), J+15
  (revue intermédiaire), J+30 (évaluation), J+45 (décision GO/NO-GO pilote → suite).
- Approbations : `【responsable produit】` et `【direction】` signent ce protocole avant J0.

## 5. Données, confidentialité et consentement

- **Données opérationnelles réelles** (missions, pesées, positions GPS, interventions) :
  collectées sous le fondement du contrat de pilote signé ; finalités limitées à la gestion
  de flotte ; rétention conformée au `document_retention_days` du plan pilote et à la
  politique validée juridiquement.
- **Consentement conducteurs** : notice individuelle signée avant tout partage GPS ; les
  refus sont sans sanction et le partage « Mon partage GPS » reste sous contrôle du
  conducteur (design produit existant).
- **Aucune donnée simulée mélangée aux données terrain** (règle du `GO_NO_GO.md`) : la base
  de démonstration reste séparée (`is_demo`, société de démonstration dédiée).
- **Journal des accès plateforme** : tout accès de l'équipe plateforme aux données de la
  société pilote passe par la vue support (lecture) et est consigné dans le journal du
  pilote (qui, quand, pourquoi).

## 6. Rôles et réponse aux incidents (RACI)

| Rôle | Personne (à consigner) | Responsabilités |
|---|---|---|
| Responsable pilote | `【…】` | jalons, revues, rapport final, décision |
| Exploitant plateforme (PLATFORM_ADMIN) | `【…】` | provisioning, abonnement, facturation, support, sauvegardes |
| Support société (TENANT_ADMIN pilote) | `【…】` | onboarding, utilisateurs, retours terrain |
| Référent incident | `【…】` | qualification, escalade, communication |
| Relève des preuves | `【…】` | journal quotidien, captures, exports, archives |

**Circuit d'incident :** tout incident est qualifié (bloquant / majeur / mineur) dans le
journal au plus tard le jour ouvré ; un incident bloquant (perte de données, fuite
cross-tenant, GPS muet > 24 h, impossibilité de saisir une pesée) **arrête le pilote** (§8)
jusqu'à analyse ; aucun contournement manuel direct en base (les correctifs passent par une
PR testée et un déploiement versionné avec rollback documenté).

## 7. Critères de succès mesurables (à la fin du pilote)

Tous mesurés depuis l'application et le journal (pas d'impression d'ensemble) :

1. **Adoption** : ≥ 80 % des missions du site créées dans l'application sur les 30 derniers
   jours ; ≥ 2 rôles métiers différents en usage hebdomadaire (hors admin).
2. **GPS** : p95 de bout en bout dans le seuil signé (prérequis 7) ; ≥ 90 % des véhicules
   équipés rapportant régulièrement ; 0 alerte GPS non acquittée > 48 h.
3. **Pesées/missions** : cycle complet mission → pesée → correction testé au moins 3 fois
   réellement ; indicateurs de tonnages cohérents avec les relevés papier du site
   (rapprochement documenté).
4. **Stabilité** : 0 incident bloquant ; incidents majeurs documentés et fermés ; aucune
   erreur serveur inexpliquée dans les journaux.
5. **SaaS** : quotas appliqués constatés (1 refus documenté minimum si la borne est
   atteinte, sinon marges) ; facture mensuelle émise (DRAFT→ISSUED) et vue par la société ;
   export réversibilité réalisé ≥ 2 fois.
6. **Satisfaction** : entretien de fin de pilote avec le TENANT_ADMIN et 2 utilisateurs
   métiers (guide d'entretien en annexe du journal).

## 8. Critères d'arrêt immédiat

- Fuite de données cross-tenant constatée (toute route, toute société).
- Perte de données opérationnelles non récupérable (au-delà du RPO mesuré).
- Incident de sécurité (compromission de compte plateforme, secret exposé).
- Retrait du consentement de la direction du client ou de la conformité juridique.

En cas d'arrêt : gel des écritures, export réversibilité immédiat remis au client, purge
planifiée (§9), revue post-mortem consignée.

## 9. Fin de pilote : données et suppression

1. **Restitution** : export JSON réversibilité complet (`GET /tenant/export`) remis au
   client ; les exports métiers détaillés (CSV existants par domaine) complètent si besoin.
2. **Décision** : suite du pilote (extension), bascule vers contrat de service (hors
   application : contrat, SLA, tarif approuvés au préalable), ou clôture.
3. **Clôture** (si le client ne poursuit pas) : suspension de l'abonnement puis
   annulation (terminal), désactivation des comptes, purge des documents à l'échéance de
   rétention du plan, puis suppression de la société par la plateforme selon la procédure
   d'exploitation (jamais un `DELETE` direct en base).
4. **Vérification** : la société ne répond plus (404 neutre sur ses routes), aucune donnée
   résiduelle accessible, journal conservé selon la politique d'audit.

## 10. Journal du pilote (modèle)

Le journal est un registre daté (fichier versionné ou ticket) tenu à chaque évènement
significatif ; colonnes minimales : date/heure (UTC+1 Conakry), auteur, type (fait / décision
/ incident / preuve ajoutée), description, lien vers la preuve (capture, export, rapport
d'exécution). Le rapport final du pilote (§7 critères + journal + entretiens) est le
document d'entrée de la décision GO commercial.

---

**Signatures d'approbation du protocole (avant J0) :**

| Rôle | Nom | Date | Signature |
|---|---|---|---|
| Responsable pilote | | | |
| Exploitant plateforme | | | |
| Direction | | | |
