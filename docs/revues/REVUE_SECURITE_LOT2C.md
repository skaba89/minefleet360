# Revue sécurité — lot 2c : compteurs et documents des véhicules (PR #16)

> Date : 2026-10-28. Objet : `backend/app/fleet/records.py`, `contracts.py`, `router.py`, `schemas.py`, `models.py`, `backend/app/assignment/eligibility.py`, `backend/app/core/validity.py`, migration `0015`, `authz_matrix.yaml` (`fleet.meter.*`, `fleet.document.*`, `fleet.vehicle_category.manage`), pages web de la fiche véhicule, des échéances et de l'administration.

## 1. Revue indépendante (agent security-engineer distinct, lecture du code)
Aucun constat critique ni élevé. Vérifiés sans problème : isolation tenant et portée site (404 uniformes, verrou après contrôle de portée), immuabilité des relevés, contrôles de relevé, retrait irréversible et versionné, chaîne d'éligibilité (affectation, conformité, départ à l'heure serveur), validation d'entrée, interface sans injection HTML.

Les constats moyens portaient sur le **contournement du blocage par document**. Ils sont traités par un changement de modèle, décidé en même temps en tant qu'expert flotte (D-42) : l'exigence est désormais portée par la **catégorie du véhicule**, et non plus par chaque document.

| ID | Gravité | Constat | Traitement |
|---|---|---|---|
| L2C-R-01 | Moyenne | Retirer un document échu pour « erreur de saisie » effaçait le blocage | **Corrigé** : l'exigence vient de la catégorie (un retrait ne la supprime pas) ; « erreur de saisie » n'est possible que dans les 24 h suivant la saisie ; test `test_blocking_cannot_be_bypassed` |
| L2C-R-02 | Moyenne | Modification libre d'un document (désactiver le blocage, repousser une échéance passée) | **Corrigé** : route de modification supprimée ; document **immuable** en base (trigger), hormis le retrait motivé ; un renouvellement est un nouvel exemplaire ; la liste des documents exigés n'est modifiable que par `TENANT_ADMIN`, avec audit avant/après |
| L2C-R-03 | Moyenne | Un exemplaire non bloquant et sans échéance satisfaisait un type bloquant | **Corrigé** : échéance obligatoire pour tout document sauf la carte grise (contrôle en base et applicatif) ; plus de notion de document « non bloquant » d'un type exigé ; test |
| L2C-R-04 | Moyenne | `reset_reason` désactivait la règle de baisse et de plausibilité (saut de compteur arbitraire) ; tout saisisseur pouvait remettre à zéro | **Corrigé** : remise à zéro = route distincte `fleet.meter.reset` (OPS_MANAGER, WORKSHOP_CHIEF), vers une valeur **inférieure** seulement ; le relevé courant ne l'accepte plus ; test |
| L2C-R-05 | Faible | Relevé futur toléré bloquant les suivants ; premier relevé sans borne | **Corrigé** pour le relevé futur (ramené à l'heure serveur). **Accepté** pour le premier relevé : il fait office de valeur initiale, saisi par un rôle autorisé, tracé ; une erreur se corrige par remise à zéro |
| L2C-R-06 | Faible | Retrait de document sans verrou du véhicule (course avec une création d'affectation) | **Corrigé** : véhicule puis document, comme les affectations |
| L2C-R-07 | Faible | Audit incomplet (`issuer`, identifiant du relevé, compteur concerné) | **Corrigé** |
| L2C-R-08 | Faible | Auteur des relevés visible de tous ; émetteur en texte libre | **Corrigé** pour l'auteur (masqué hors `TENANT_ADMIN` et `AUDITOR`, politique de champ de la matrice) ; **accepté** pour l'émetteur (nom d'organisme, consigne affichée à la saisie) |
| L2C-R-09 | Faible | Intégrité du document assurée par l'application seulement | **Corrigé** : trigger `tg_vehicle_document_guard` (seule transition VALID → WITHDRAWN, champs figés) ; test en base |
| L2C-R-10 | Faible | Alertes d'échéance : borne avant filtrage, requête par ligne, renouvellement futur | **Corrigé** : renouvellement testé en SQL (`NOT EXISTS`, exemplaire en vigueur couvrant l'horizon), limite appliquée ensuite |
| L2C-R-11 | Info | Absence de document non bloquante ; « pas encore valide » libellé « échu » | **Corrigé** : documents exigés par catégorie (D-42) avec politique `warn` puis `block` ; code distinct `VEHICLE_DOCUMENT_NOT_YET_VALID` ; manquants affichés sur la fiche |

## 2. Risque résiduel accepté
- **Politique `warn` par défaut** pour les documents exigés **jamais saisis** : le temps de saisir le parc existant, un véhicule sans aucun document reste affectable (avec avertissement). À passer à `block` (`MF_REQUIRED_DOCUMENTS_POLICY=block`) une fois le parc saisi. Un document **échu ou retiré** bloque toujours.

## 3. Vérifications exécutées (2026-10-28)
- Serveur : ruff, format, mypy OK ; `tests/test_vehicle_records.py` (10 scénarios) ; suite complète **2095 tests**, couverture 93,34 %.
- Migration `0016` (correctifs, la PR #16 ayant été fusionnée avant) : passage depuis 0015 vérifié avec un document existant ; copie des documents exigés vérifiée (44 par tenant) ; aller-retour OK.
- Interface : `tsc`, Vitest 19, Playwright 16, build, permissions à jour.

## 4. Non vérifié
- Concurrence réelle entre retrait de document et création d'affectation : raisonnement sur l'ordre des verrous, pas de test parallèle.
- Liste légale guinéenne des documents obligatoires : avis juridique local requis.
