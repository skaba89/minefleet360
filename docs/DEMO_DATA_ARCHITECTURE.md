# Architecture des données de démonstration (DEMO)

État au 2 novembre 2026 — premier lot : profil `small`. Les profils `standard` et `large` sont déclarés mais
leur volume et leurs performances n'ont pas encore été mesurés (lot suivant).

## 1. Objectif et principes

Permettre d'ouvrir MineFleet 360 sur une base peuplée de données **réellement insérées** et servies par les API
et les écrans existants, sans aucun chiffre codé en dur dans l'interface.

| Exigence | Mise en œuvre |
|---|---|
| Passer par les règles métier | Chaque objet est créé par le **service applicatif** (`app.*.service`), sous l'identité du compte DEMO qui porte la permission dans `authz_matrix.yaml`. Aucun `INSERT` direct, RLS jamais désactivée, rôle `mf_app`. |
| Historique crédible | Horloge simulée (`FrozenClock`) avancée événement par événement : les bornes d'antidatage (RM-083), l'éligibilité des affectations, les échéances et les quatre yeux s'appliquent comme en exploitation. |
| Déterminisme | `--seed` + `--anchor` ⇒ mêmes engins, conducteurs, missions, pesées, carburant, chronologie. Une graine dérivée par société : ajouter une société ne change pas les autres. Les identifiants techniques (UUID) et les **mots de passe** ne sont pas déterministes (aléa cryptographique). |
| Idempotence | À la maille de la société : une société DEMO déjà présente est ignorée, aucune écriture. |
| Données fictives reconnaissables | Raisons sociales « DEMO — … », sites « (DEMO) », e-mails `@demo-*.example.com`, téléphones `+224000…`, numéros de parc et permis `DEMO-…`, noms `Démo-…`. Aucune coordonnée GPS générée dans ce lot. |

## 2. Commandes

```
minefleet demo seed --profile small --seed 42 [--anchor 2026-10-01] --credentials-out /chemin/comptes-demo.tsv
minefleet demo verify [--anchor 2026-10-01]
minefleet demo reset-credentials --tenant demo-bauxite --credentials-out /chemin/nouveaux-comptes.tsv
```

- `seed` : charge les sociétés absentes ; écrit les identifiants dans un **nouveau** fichier créé en mode 600
  (refus si le fichier existe) ; n'affiche jamais un mot de passe dans le terminal.
- `verify` : contrôles recalculés depuis les données sources (§5). Code de sortie 1 au premier écart.
- `reset-credentials` : régénère les mots de passe d'une société DEMO (sessions fermées, action auditée
  `user.password_reset`). Utile quand le fichier d'identifiants a été supprimé après transmission.

En conteneur : `docker compose … run --rm api minefleet demo seed …` avec un volume monté pour le fichier.

## 3. Garde-fous (impossibilité technique hors base DEMO)

`app/demo/guards.py`, appelé par `seed` et `reset-credentials` :

1. refus si `MF_ENV=production` ;
2. refus si la base contient **un seul** tenant client non marqué `is_demo` (vrai client, recette partagée) —
   indépendamment de la configuration.

`reset-credentials` n'accepte en outre qu'un code du catalogue DEMO et vérifie `is_demo` en base.

### Réinitialisation complète des données

Le rôle applicatif `mf_app` n'a **pas** le droit `DELETE` sur les tables métier (choix de sécurité du socle) ;
aucune commande ne contourne cette règle. La remise à zéro d'une démo se fait donc en **recréant la base de
l'instance de démonstration** (migrations puis `demo seed`), jamais par suppression ligne à ligne. Une commande
`demo reset --tenant … --confirm` exécutée avec le propriétaire du schéma reste possible mais n'est pas livrée :
elle demande une décision explicite (droit destructif, journalisation, double confirmation).

## 4. Contenu du profil `small` (graine 42)

| Élément | Volume | Détail |
|---|---:|---|
| Sociétés | 3 | DEMO — Bauxite Guinée Operations (Boké, Boffa) ; DEMO — Mines Aurifères de Haute-Guinée (Siguiri) ; DEMO — Transport & Logistique Minière (Kamsar, Conakry) |
| Sites | 5 | mine, terminal portuaire, dépôt, atelier |
| Comptes | 47 | les 13 rôles client de la matrice ; rôles de site (DISPATCHER, DRIVER, MECHANIC, FUEL_MANAGER) un par site |
| Engins | 28 | tombereaux, articulés, porteurs routiers, chargeuses, pelles, niveleuse, bouteur, citerne, arroseuse, bus, VL |
| Conducteurs | 21 | permis et autorisations de conduite ; 2 cas négatifs par société (permis expiré, permis proche échéance) |
| Affectations | 15 | une par engin de transport, poste `JOUR` |
| Missions / rotations / pesées | ≈205 / ≈560 / ≈560 | 14 jours, 2 à 4 rotations par mission, pesées pont-bascule |
| Activité du jour J | 6 en cours, 3 planifiées | missions en chargement, route chargée, déchargement, démarrées 2 h 30 avant l'exécution (ou 08:00 pour un ancrage passé) — seule partie qui dépend de l'heure d'exécution |
| Carburant | 5 cuves, ≈100 distributions | réceptions bornées par la capacité ; demande par le responsable carburant, approbation par le responsable des opérations (quatre yeux) |
| Atelier | 6 OT | une panne clôturée (approbation, assignation, temps passé, contrôle qualité) et une panne ouverte par société |
| HSE | 6 incidents | un presque-accident enquêté, action corrective réalisée puis vérifiée, incident clos ; un incident critique ouvert |

Volumes indicatifs : ils dépendent de la graine et de la date d'ancrage ; la sortie de `seed` donne les valeurs exactes.
Contrôle de déterminisme effectué : deux bases vierges chargées avec la graine 42 et le même ancrage donnent les mêmes
volumes historiques (558 rotations, 555 pesées, 97 distributions de carburant).

## 5. Contrôles de `demo verify`

Pour chaque société, sous le contexte RLS de la société :

- société présente et marquée `is_demo` ;
- isolation : aucun engin ni pesée d'une autre société visible ;
- chaque rotation terminée porte une pesée non annulée ;
- tonnage mesuré des 7 derniers jours : somme directe des pesées = indicateur servi par `dispatch.weighing.indicators` ;
- solde de chaque cuve = réceptions − distributions approuvées, compris entre 0 et la capacité ;
- OT bloquant ouvert ⇔ engin immobilisé ; OT clôturé ⇒ engin remis en service.

## 6. Instance de démonstration

Une instance dédiée (base, secrets, stockage, URL séparés de la production) est **requise** : les garde-fous
refusent une base qui contient de vrais clients. Elle n'est **pas** provisionnée par ce lot (décision humaine :
coût, domaine, sauvegardes). Points à arbitrer :

- `MF_ENV=staging` ; base et secrets propres ; URL distincte ;
- double authentification : DIRECTION, OPS_MANAGER, TENANT_ADMIN, HR, FINANCE doivent l'enrôler à la première
  connexion (`MF_MFA_ENFORCEMENT=enroll`). Pour une démonstration commerciale, `off` sur l'instance DEMO
  uniquement est envisageable — à décider, jamais en production ;
- le fichier d'identifiants est à transmettre par canal sûr puis supprimer.

## 7. Hors périmètre de ce lot (prochains lots)

Positions GPS et franchissements de zones, pièces et sorties de magasin, pneumatiques, inspections HSE et
checklists, achats de carburant, contrats et documents, parcours hors ligne, profils `standard`/`large` mesurés,
mode « démonstration commerciale » guidé, E2E Playwright sur les données DEMO.
