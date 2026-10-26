# Roadmap du MVP démontrable

Base auditée : `2e3b803`, 26 octobre 2026. Réutiliser le monolithe et les référentiels existants. Pas d'estimation calendrier fiable avant correction/vérification des prérequis et arbitrages métier.

| Ordre | Tranche | Contenu et démonstration | Critère de sortie |
|---|---|---|---|
| 0 | R1–R4 remédiations | Migrations peuplées, sites cohérents, authentification et exploitation | Risques hauts traités et contrôles vérifiés |
| 1 | Socle UI et affectations (suite 1c) | Connexion, administration utilisateurs/rôles/sites, consultation audit, contexte site, listes/détails/création véhicules et conducteurs, permis/habilitations, affectation datée puis clôture | API/UI françaises, contraintes anti-chevauchement DB, audit, E2E |
| 2 | Missions et rotations | Créer une mission, sélectionner affectation admissible, démarrer, saisir rotations, clôturer | Transitions et idempotence, unités/temps explicites, droits tenant/site |
| 3 | Atelier et mécaniciens | Déclarer panne, immobiliser, créer OT, affecter mécanicien, diagnostic/intervention, contrôle et remise en service | Aucun retour disponible avant validation autorisée; historique complet |
| 4 | Tableau de bord exploitation | Engins disponibles/immobilisés, affectations, missions, rotations, OT et échéances | Calculs traçables, filtres site/période, états vides et fraîcheur visibles |
| 5 | Démonstration consolidée | Jeu synthétique reproductible, scénario de bout en bout, panne et reprise | Tests E2E, inter-tenant, sécurité/QA et guide de démonstration |

## Parcours de référence

Administrateur plateforme crée un tenant fictif → administrateur tenant active ses accès et crée deux sites → responsable des opérations crée un engin → RH crée un conducteur fictif avec permis/habilitation valides → dispatcher planifie/active une affectation → crée et démarre une mission → saisit une rotation → signale une panne → chef d'atelier ouvre un OT → mécanicien diagnostique et termine → chef valide la remise en service → mission reprend/se clôture → dashboard reflète l'activité et l'immobilisation. Réexécuter avec un second tenant et vérifier l'absence totale d'accès croisé.

## Règles à conserver

- Affectation : conducteur/engin/site du même tenant, dates cohérentes, permis/habilitations valables sur la période requise, non-chevauchement garanti par PostgreSQL et tests concurrents.
- Missions : distinguer capacité nominale et charge réellement mesurée. Aucun tonnage mesuré déduit du GPS; saisie/source de pesée explicitement identifiée et validée.
- Atelier : rôles mécanicien/chef déjà déclarés à raccorder à des objets métier; décision explicite sur la levée d'une interdiction SAFETY_BAN avant pilote.
- Interface : français, heures affichées avec fuseau explicite, UTC en stockage, responsive, formulaires accessibles, états de chargement/erreur/vide; permissions appliquées côté serveur.
- Tout lot : migration justifiée ou non applicable explicite, schémas/API, UI, tests unitaires et PostgreSQL, cas A→B et sites, audit non personnel, documentation, revue sécurité/QA et rapport exact des vérifications.

## Après MVP

GPS fournisseur et offline, carburant, stocks/pièces, maintenance préventive, HSE avancé et rentabilité restent dans la vision initiale. Un adaptateur GPS simulé peut être ajouté après le parcours manuel fiable; le distinguer d'une intégration réelle. Ne pas introduire de microservices ou dépendances spéculatives. Aucun déploiement production sans validation.

## Définition de démontrable

Scénario complet accessible dans le navigateur, données fictives uniquement, environnement isolé, restauration démontrée, erreurs et conflits compréhensibles, CI verte sur le SHA livré, preuves de calcul des indicateurs. Les référentiels backend actuels ne suffisent pas à cette définition.
