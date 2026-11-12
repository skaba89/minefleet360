# Protocole d'essai d'un traceur GPS physique — qualification par modèle

- **Objet** : protocole d'exécution de l'essai d'UN traceur physique réel, pour produire la preuve
  « traceur physique ciblé » exigée par `docs/qa/GO_NO_GO.md` (condition n° 5) et le protocole de pilote
  (`docs/ops/PROTOCOLE_PILOTE.md`, prérequis 5). Il applique le cahier des exigences fournisseur
  (`docs/GPS_FOURNISSEUR_CAHIER.md`) : aucun décodeur développé sans spécification réelle, adaptateur
  enregistré dans `backend/app/fleet/gps_payload_adapters.py` seul admis, **aucune compatibilité annoncée
  avant rapport daté**.
- **Périmètre de validité** : la qualification porte sur le couple **modèle + firmware + protocole +
  réseau (SIM/opérateur)** réellement essayés. Un changement de firmware ou de protocole annule le
  résultat. Une validation CI ou par fixtures ne vaut jamais certification matérielle.

## 0. Conditions préalables

| # | Prérequis | Preuve |
|---|---|---|
| P1 | Spécification écrite du fournisseur reçue (format, authentification, horodatage, rejeu) | dossier fournisseur horodaté |
| P2 | Adaptateur implémenté si le fournisseur ne pousse pas `minefleet-json-v1` nativement, avec fixtures expurgées et tests verts en CI | PR fusionnée, CI verte |
| P3 | Boîtier physique en main, avec SIM active d'un opérateur représentatif du site cible (Guinée) | photo + ICCID masqué dans le rapport |
| P4 | Environnement d'essai dédié (staging ou local), jamais production ; véhicule de test déclaré dans la société de démonstration | URL d'essai + compte de test |
| P5 | Secret par traceur provisionné via l'UI (`fiche véhicule → Géolocalisation → Associer un traceur`) et remis au fournisseur/intégrateur | capture horodatée (clé non affichée) |

**Interdits** : IMEI réels ou coordonnées sensibles dans les commits/fixtures ; données de clients réels ;
annonce de compatibilité avant la fin du §4.

## 1. Phase laboratoire (banc, antenne extérieure ou fenêtre)

Objectif : valider le contrat d'ingestion **sans variable terrain**. Chaque mesure est horodatée et
conservée brute (sortie API, journal serveur, fichier fourni par le traceur).

| # | Test | Procédure | Critère de réussite |
|---|---|---|---|
| L1 | Ingestion nominale | le traceur pousse vers `POST /api/v1/gps/telemetry` (contrat `minefleet-json-v1` ou adaptateur qualifié) | 202/200 par position ; position visible dans l'historique |
| L2 | Authentification | position avec secret inconnu, secret révoqué, en-tête absent | refus 401/403, **aucune écriture**, événement consigné |
| L3 | Anti-rejeu | rejouer une position déjà acceptée (même séquence/horodatage) | refus de doublon, une seule position en base |
| L4 | Messages hors ordre | pousser t₂ puis t₁<t₂ | traitement sans corruption de l'historique (ordre de réception conservé, horodatages respectés) |
| L5 | Sans fix | forcer absence GNSS (boîtier en boîte métallique) | position refusée ou marquée sans fix, pas de coordonnée fantôme |
| L6 | Horodatages invalides | futur lointain, epoch 0, fuseau incohérent | refus ou normalisation documentée — jamais de position mal datée acceptée |
| L7 | Coupure réseau | débrancher le lien 15 min puis rétablir | rejeu du stockage embarqué : les positions manquantes arrivent, ordre et unicité respectés |
| L8 | Limite de taille / charge hostile | payloads surdimensionnés, JSON malformé, champs inconnus | refus propre (4xx), aucun crash worker, journal sans fuite de contenu |
| L9 | Révocation / réaffectation | révoquer le secret puis réassocier le boîtier à un autre véhicule | l'ancien secret ne pousse plus ; la nouvelle association fonctionne |

## 2. Phase terrain (site réel, réseau mobile guinéen)

Objectif : mesurer le comportement en conditions représentatives. Durée minimale : **1 journée
d'exploitation complète** + 1 trajet routier. Les mesures ci-dessous sont relevées automatiquement quand
une commande existe, sinon manuellement (méthode consignée).

| # | Mesure | Définition | Cible indicative (à figer au rapport) |
|---|---|---|---|
| T1 | Latence de réception | horodatage GNSS → écriture en base | p95 < 30 s en 4G |
| T2 | Latence d'affichage | écriture → visible sur la carte `/flotte-gps` (SSE) | p95 < 5 s après écriture |
| T3 | Fraîcheur | âge de la dernière position pendant roulage | < 2 min en continu |
| T4 | Précision disponible | écart estimé vs point de référence connu (site) | consigné (hors tunnel/entrepôt) |
| T5 | Doublons | positions identiques (même horodatage/séquence) en base | 0 |
| T6 | Hors ordre | messages t₁ arrivés après t₂ | comptés ; traitement conforme L4 |
| T7 | Perte de paquets | positions attendues (cadence × durée) vs reçues hors coupures déclarées | < 5 % en 4G |
| T8 | Reconnexion | reprise du flux après tunnel/zone blanche | < 2 min, rejeu conforme L7 |
| T9 | Charge et coût | messages/heure, data consommée (compteur SIM), autonomie | consignés (coût mensuel estimé par traceur) |
| T10 | Zones et alertes | entrée/sortie de zone créée sur le site, alerte acquittée depuis l'UI | déclenchement correct, latence T1+T2 |

## 3. Matrice de qualification (à remplir par modèle essayé)

| Fabricant | Modèle | Firmware | Protocole | SIM / opérateur | Test laboratoire | Test terrain | Certification |
|---|---|---|---|---|---|---|---|
| 【…】 | 【…】 | 【…】 | 【…】 | 【…】 | 【date + rapport】 | 【date + rapport】 | 【OUI/NON — périmètre exact】 |

**Règle d'affichage** : la certification ne porte que sur la ligne remplie. Toute autre combinaison
modèle/firmware/protocole reste « non essayé » — aucune compatibilité ne peut être annoncée
(`docs/GPS_FOURNISSEUR_CAHIER.md`, registre fermé).

## 4. Rapport de qualification (modèle)

| Champ | Contenu |
|---|---|
| Modèle / firmware / protocole / IMEI masqué | … |
| Dates d'essai (laboratoire, terrain) et opérateur | … |
| Spécification fournisseur reçue (référence, version) | … |
| Adaptateur utilisé (identifiant, commit, PR) | … |
| Résultats L1–L9 (tableau, écarts) | … |
| Mesures T1–T10 (tableau, p50/p95, méthode) | … |
| Incidents et limites constatées | … |
| Coûts (boîtier, SIM, data mensuelle, installation) | … |
| Décision : adaptateur certifié / à corriger / rejeté — périmètre exact | … |
| Preuves (chemins + SHA256, hors dépôt si sensibles) | … |

La décision est consignée dans `docs/audit/COMMERCIAL_READINESS_CURRENT.md` (§ inconnues n° 3) uniquement
lorsque le rapport est complet ; le registre d'adaptateurs du code n'est modifié que par PR testée.
