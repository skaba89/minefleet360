# Protocole de validation facturation et coût-servi (S1 + C2) — préparation d'entretiens

> **Statut** : protocole de préparation — **aucun tarif fixé, aucun schéma/API, aucune décision produit**. Il structure les entretiens et mesures que la roadmap exige **avant** toute ouverture de chantier.
> **Date** : 13 novembre 2026.
> **Sources** : `ROADMAP_85_TO_95.md` S1 (« règles et cas de facturation validés avant schéma/API », source « entretiens et règles métier ») et C2 (« modèle de coût par flotte + validation 3+ prospects/pilotes », source « mesure infra, support et cible client ») ; `REGLES_METIER.md` RM-077 (base tonnage **mesuré approuvé** par défaut ; toute autre base doit être contractuelle) et RM-026 ; `COMMERCIAL_LAUNCH_PLAN.md` (offres candidates, composantes du coût-servi, test de volonté de payer) ; `GO_NO_GO.md` (produit SaaS complet côté logiciel #418/#419/#420/#422/#423 ; « tarifs restent des paramètres non approuvés — arbitrage coût-servi + entretiens clients à faire ; aucun chantier de code »).

## 1. Ce que ce protocole ne fait pas

- **Aucun schéma, aucune API** : la gate S1 (« validés **avant** schéma/API ») reste fermée tant que les règles ne sont pas signées.
- **Aucun tarif ni quota** : la règle du plan de lancement s'applique — ne rien fixer avant le coût-servi mesuré et le test de volonté de payer.
- **Aucun arbitrage** : le suivi de règlement « payé » et l'export PDF restent à l'arbitrage expert-comptable (décision séparée) ; les contrats et SLA relèvent de la revue juridique (rang 2 du GO/NO-GO).

## 2. Volet 1 — Entretiens « règles de facturation » (S1)

Personas à interroger (2 à 3 entretiens par persona, exploitations et sous-traitants pilotes) : exploitant minier / donneur d'ordre, gérant de sous-traitance, responsable pesée, comptable de l'exploitant. Chaque cas de facturation n'est **validé** que si une **règle énoncée et signée par le client** en sort — jamais une règle proposée par l'éditeur.

| Cas | Questions d'entretien | Données à collecter | Critère de sortie |
|---|---|---|---|
| C-1 : base tonnage mesuré approuvé (RM-077, défaut) | Qui approuve la pesée ? Quel document contractuel porte la base ? Fréquence de facturation (rotation, semaine, mois) ? Écarts tonnage déclaré/mesuré : quel seuil déclenche une contestation ? | Un contrat de sous-traitance réel (anonymisé) ; un bordereau de pesée type | La chaîne pesée → approbation → base facturable est décrite par le client, étape par étape |
| C-2 : bases non-tonnage (exception contractuelle) | Quelles prestations se facturent autrement (location avec/sans conducteur, maintenance externalisée, prestation au forfait) ? À quelle condition contractuelle ? | Une clause de chaque variante rencontrée | La liste des exceptions avec leur ancrage contractuel est établie |
| C-3 : SLA et retenues | Qu'est-ce qui déclenche une retenue aujourd'hui (retard, incident HSE, panne) ? Comment est-ce mesuré (papier, tableur) ? | Les mesures actuelles et leur fiabilité perçue | Les déclencheurs de retenue sont énoncés avec leur donnée déclenchante dans l'outil |
| C-4 : multi-sites et rapprochement | Facture par site ou globale ? Comment rapprocher pesée ↔ mission ↔ sous-traitant ? | Les documents de rapprochement actuels | Le périmètre de rapprochement (site, mission, période) est défini par le client |
| C-5 : monnaie, taxes, paiement | GNF confirmé pour chaque composante ? Taxes et retenues à la source ? Paiement local et frais d'installation ? | Les mentions obligatoires d'une facture locale | Les mentions et le circuit de paiement sont décrits (relance point 16 du plan de lancement) |

**Règle transversale (RM-026)** : les conducteurs sous-traitants/intérimaires subissent les mêmes contrôles d'éligibilité — vérifier en entretien que le circuit d'approbation du donneur d'ordre le confirme avant toute modélisation des comptes externes (modèle d'accès : `MODELE_SECURITE_SOUS_TRAITANTS.md`).

## 3. Volet 2 — Coût-servi mesuré (C2)

Chaque composante du coût-servi est **mesurée sur staging réel** pendant la session d'exécution (les outils existent déjà), jamais estimée :

| Composante | Méthode de mesure | Source / outil |
|---|---|---|
| Base de données par tenant | Volumétrie et croissance par tenant après chargement pilote | staging, métriques PostgreSQL |
| Historique GPS + rétention | Volume ingéré par fenêtre et coût de rétention au seuil retenu | ingestion réelle + `GET /gps/metrics` (relève scriptée #443) |
| Sauvegarde et sortie de crise | Temps et coût du cycle complet R1 (protocole #427) | `PROTOCOLE_RESTAURATION_EXTERNE.md` |
| Support et onboarding | Temps réel passé par flotte lors de l'installation pilote (#423) | journal d'onboarding |
| SMS / notifications | Coût fournisseur réel au volume pilote | facture fournisseur (rang 7 si traceur) |
| Matériel traceur + SIM | Coût d'acquisition et d'abonnement relevé sur le devis du boîtier d'essai | banc L1–L9 (`PROTOCOLE_ESSAI_GPS_PHYSIQUE.md`) |
| Infrastructure par flotte | CPU/RAM/stockage par worker aux charges pilotes | staging équipé (`GPS_SSE_CAPACITY.md` §Mesures) |

Sortie : un **modèle de coût par flotte** (tableau par offre candidate — Starter, Business, Mining Pro, Enterprise, colonnes « Contenu à tester » et « Unité de prix à comparer » déjà définies dans le plan de lancement) qui nourrit l'arbitrage tarif, sans fixer de prix.

## 4. Volet 3 — Test de volonté de payer (barre C2 : 3+ prospects/pilotes)

Les quatre offres candidates sont présentées comme prototypes de contenu (pas de prix signé avant coût-servi). Pour chaque prospect : contenu retenu, unité de prix perçue comme juste, objections écrites, engagement de pilote. La barre est atteinte quand **3+ prospects/pilotes** ont exprimé par écrit une volonté de payer cohérente avec une même offre.

## 5. Barre de sortie et articulation

1. Sortie S1 : `REGLES_FACTURATION_S1_C2_VALIDÉES.md` — règles et cas signés (produit + clients).
2. Sortie C2 : modèle de coût par flotte + 3+ volontés de payer écrites.
3. **Alors seulement** : ouverture du chantier schéma/API de facturation sous-traitants (gate S1 levée par le produit), tarifs approuvés (arbitrage coût-servi + expert-comptable), contrats/SLA (revue juridique rang 2).
4. Les arbitrages séparés (règlement « payé », export PDF) ne sont ni bloqués ni décidés par ce protocole.

## 6. Traçabilité

- `ROADMAP_85_TO_95.md` S1 et C2 restent **« À faire »** — ce protocole les prépare, il ne les ferme pas.
- `GO_NO_GO.md` : aucun prérequis levé (les restes tarif/SLA/règlement restent non techniques) ; classement inchangé.
- `COMMERCIAL_LAUNCH_PLAN.md` §« Offres à étudier » : la structure d'entretien et la mesure coût-servi renvoient à ce protocole.
- `COMMERCIAL_READINESS_CURRENT.md` : entrée au registre §8 et bloc de révision daté (PR #444).
