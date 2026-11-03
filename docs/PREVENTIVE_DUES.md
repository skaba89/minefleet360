# Échéances préventives : point de départ et compteurs

État au 3 novembre 2026. Décisions du client (3 novembre 2026) :

1. **Point de départ d'un plan** : l'atelier déclare le **dernier entretien connu** (date et cumuls km / heures
   relevés ce jour-là). Une **autre personne** l'approuve ou le rejette. Si le dernier entretien est inconnu, cette
   déclaration, une fois approuvée, rend un **entretien initial** dû tout de suite.
2. **Compteurs** : valeur actuelle = cumul au dernier jalon validé + hausses des relevés bruts depuis ce jalon. Une
   baisse (remise à zéro, compteur remplacé, erreur de saisie) rend le compteur **non fiable** jusqu'à un nouveau
   jalon validé.
3. **Déclenchement** : d'abord un bouton « Évaluer les échéances » pour le responsable atelier, ensuite une tâche
   quotidienne qui réutilisera le même service (lots suivants).
4. **Ordre de travail** : l'échéance apparaît « due » ; le responsable atelier crée l'OT préventif (action
   existante). Rien n'est immobilisé automatiquement.

## Constat de départ

- Tous les plans de démonstration (120 sur le jeu `large`) restaient en « information insuffisante ». Le calcul
  partait uniquement du dernier OT préventif clôturé, qui n'existe jamais pour un plan neuf.
- Le compteur « actuel » ne comptait que s'il avait été **approuvé**, et tout relevé postérieur l'invalidait. Comme
  aucune route ne permettait d'approuver un compteur, les seuils km et heures ne pouvaient jamais se déclencher.

## Livré dans cette tranche (A)

| Élément | Détail |
|---|---|
| Table `maintenance_service_declaration` (migration 0058) | engin, site, code de plan, `KNOWN` (date ≤ déclaration, km / heures facultatifs) ou `UNKNOWN` (ni date ni compteur), statut `PENDING` → `APPROVED` / `REJECTED`. Contraintes en base : décideur ≠ déclarant (`ck_msd_four_eyes`), motif obligatoire au rejet, **une seule déclaration en attente** par engin et code de plan. RLS forcée. |
| `maintenance_due.trigger_kind = INITIAL` | échéance datée (date d'approbation), sans compteur ; clé `INITIAL:<déclaration>` (unique par plan) |
| Jalon d'un plan | le plus récent de : clôture du dernier OT préventif du même code de plan, ou dernière déclaration approuvée (datée par l'entretien déclaré, ou par l'approbation pour « inconnu ») |
| Compteurs | `preventive_meters_since` : hausses mesurées entre relevés bruts (le dernier relevé au plus tard au jalon sert de référence d'échelle ; sans lui, le premier relevé suivant est comparé au cumul déclaré). Toute baisse → non fiable, aucune échéance déduite de ce compteur |
| API | `POST /preventive-declarations`, `POST /preventive-declarations/{id}/decide` (permission `maintenance.preventive.manage`, portée site) ; `GET /vehicles/{id}/preventive-declarations` et `GET /vehicles/{id}/preventive-status` (permission `maintenance.preventive.read`). L'état est **calculé à la lecture**, sans rien enregistrer |
| Écran | fiche engin et page Préventif : état de chaque plan (point de départ, km / heures restants, compteur non fiable, date d'échéance), déclaration du dernier entretien, approbation ou rejet motivé. Le déclarant voit « À valider par une autre personne » |
| Audit | `maintenance.service_declaration.create` et `.decide` (avec le motif) |

**Vérifié sur une copie du jeu `large`** (demo-bauxite, 48 plans) : avant, 48 plans en « information
insuffisante ». Après 36 déclarations « connu » et 12 « inconnu », toutes approuvées par une autre personne : les 36
plans connus sont dus par les heures moteur (exemple : 381 h depuis le jalon pour un intervalle de 250 h), et les
12 inconnus demandent un entretien initial. L'auto-approbation a été refusée à chaque fois.

## Reste à faire

- **B** : clôturer une échéance sans approbation de compteur (le cumul à la clôture est calculé selon la même
  règle, puis figé), et ajouter le bouton « Évaluer les échéances », qui enregistre les échéances dues (idempotent,
  audité, limité au site) et les liste sur la page Préventif.
- **C** : tâche quotidienne (compte technique à droits minimaux, supervision des échecs, reprise sans doublon).
- Le calendrier utilise la date UTC du jalon ; le fuseau du site pour les échéances calendaires reste à arbitrer
  (`PLAN_LOT3B_PREVENTIF.md`).
- La vraisemblance des hausses entre deux relevés est déjà contrôlée à la saisie (D-43) ; aucune autre détection
  d'anomalie n'est ajoutée ici.
