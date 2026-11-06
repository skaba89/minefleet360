# Feuille de route — 70 vers 85 puis 95

Baseline au 6 novembre 2026 : `main@089d801`, score dépôt 70/100 selon `docs/audit/INDUSTRIAL_READINESS_2026.md`. Les seuils 85 et 95 ne seront validés qu’à partir de preuves d’exploitation, pas du nombre de PR.

## Backlog avec dépendances et critères

| ID | Priorité | Lot | Problème / risque | Dépend de | Acceptation | Statut actuel |
|---|---|---|---|---|---|---|
| A0 | P0 | Audit de référence et inventaire des preuves | Docs d’état et score doivent suivre les preuves fusionnées sans confondre CI et terrain | HEAD fixé | 8 documents cohérents; aucune preuve terrain inventée; CI HEAD référencée | Fusionnée (#360–#371), validation terrain non applicable |
| R1 | P0 | Restauration isolée | La CI couvre le transport rclone local, chiffrement, checksum, déchiffrement, restore, propriétaires/ACL/RLS et démarrage API; elle ne couvre pas un coffre externe ni staging/RPO/RTO | environnement staging isolé, archive distante chiffrée réelle | restore complet chronométré, contrôles tables/migrations, démarrage API, procédure et alerting | Chaîne synthétique automatisée; coffre externe et recette staging à faire |
| R2 | P0 | Relance staging et rollback | Manifeste immuable et script staging fusionnés dans #372; répétition réelle non démontrée | images publiées par digest, accès infra, migrations compatibles | installation reproductible, health/readiness, rollback répété sans toucher prod | Outillage/CI validés; exécution staging à faire |
| G1 | P0 | Pilote matériel GPS | Registre d’adaptateurs versionné et chaîne sécurisée présents; aucun modèle/firmware certifié | spécification fournisseur, appareil réel et partenaire/consentement | preuve d’auth, décodage, duplicat, ordre, replay, rétention, révocation par modèle | Architecture en code; fixtures fournisseur, laboratoire et terrain à faire |
| G2 | P0 | Benchmark bout en bout GPS | Harnais REST/SSE expurgé avec p50/p95/p99 et rounds de reconnexion; capacité infra et ingestion→UI non mesurées | staging représentatif, dataset synthétique | résultats bruts CPU/RAM/DB/latences/p50/p95/p99/pertes à plusieurs niveaux de concurrence | Harnais en CI; exécution staging à faire |
| P1 | P1 | Offline Android HSE | E2E ne remplace pas le test Android réseau dégradé | appareils cibles et jeux fictifs | synchronisation idempotente, conflits, retrait droits, expédition/retour réseau vérifiés | À faire |
| P2 | P1 | GPS téléphone durable | Le tampon RAM ne résiste pas à fermeture/suspension | revue chiffrement et conformité approuvée | aucun code avant architecture approuvée; tests effacement et séparation multi-tenant | Bloqué par décision sécurité |
| M1 | P1 | Recette métier minière | Coûts, pneus, carburant, HSE, pesées et atelier non rapprochés physiquement | client pilote, procédures métier | scénarios signés par personas; écarts connus et expliqués | À faire |
| S1 | P1 | Sous-traitants et rentabilité | Contrats/SLA/prestations et coût complet sous-traitant incomplets | entretiens et règles métier | règles et cas de facturation validés avant schéma/API | À faire |
| C1 | P1 | Onboarding et support SaaS | Client ne peut pas encore acheter/activer/gérer son abonnement par un processus complet | modèle de support/prix/coûts | onboarding, import, formation, support, suspension et sortie testés | À faire |
| C2 | P1 | Économie et tarifs | Prix non soutenus par coût réel ni entretiens | mesure infra, support et cible client | modèle de coût par flotte + validation 3+ prospects/pilotes | À faire |
| X1 | P2 | Expansion régionale/internationale | Langues, devises, hébergement, rétention et règles pays inconnus | choix des marchés | matrice marché par marché revue par professionnels | À faire |

## Jalons de maturité

### 85/100 — pilote terrain maîtrisé

À attribuer uniquement lorsque :

- R1/R2 et G1/G2 sont validés en staging avec rapports, observations et artefacts expurgés;
- isolation entre deux tenants testée en conditions d’exploitation;
- parcours HSE et mission acceptés par les personnes concernées;
- aucune vulnérabilité critique/élevée ouverte sans décision formelle;
- consentement GPS, arrêt, conservation et procédure de support définis;
- données pilotes fictives ou autorisées, accès tracé et procédure incident testée.

### 90/100 — service industrialisé

Ajouter ensuite restauration répétée, déploiement/rollback standard, alerting réel, opérations d’incident, budget de capacité, mise à jour contrôlée et sécurité d’infrastructure répétée.

### 95/100 — SaaS B2B commercialisable

N’attribuer qu’après plusieurs pilotes, onboarding et support testés, contrat/SLA et politique de confidentialité examinés, économie unitaire calculée, prix testés avec clients, rétention observée et processus d’exploitation réellement tenus.

## Tableau de suivi des lots

Transitions autorisées : **À faire → En cours → PR ouverte → CI validée → Fusionnée → Validée en recette → Validée sur le terrain**. Une étape ne se déduit pas de la précédente. Le dernier état doit citer une preuve de recette ou un compte rendu client.

Le registre d’adaptateurs et le harnais de benchmark réduisent le risque d’intégration, mais ne justifient aucune hausse du score sans exécution staging et matériel réel.
