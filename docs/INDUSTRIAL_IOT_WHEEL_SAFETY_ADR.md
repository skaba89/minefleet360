# ADR proposée — Industrial IoT et Smart Wheel Safety
Date : 2026-11-26. Référence de départ : 8bb23b284033b2f17ffc67d29383890026b374ce.
Statut : proposée, aucun matériel certifié, aucun changement runtime.

## Inventaire ciblé (lecture statique, non exhaustif)
| Source | Constat | Décision |
|---|---|---|
| backend/app/maintenance/tyre_models.py et tyre_service.py | tyre, tyre_event, position_code, pression nominale et relevée en kPa, événements de montage et inspection, PRESSURE_DEVIATION | Réutiliser les pneus; distinguer télémétrie et inspection humaine |
| backend/app/maintenance/tyre_router.py | routes /tyres, permissions read/manage/fit, ETag | Conserver contrats et contrôles |
| frontend/src/pages/TyresPages.tsx | parc, stock, usure, alertes, coûts, export | Enrichir sans duplication |
| backend/app/fleet/gps_live_router.py | provisionnement/révocation GPS, authentification machine, ingestion HTTPS, lot différé téléphone | Réutiliser principes de sécurité, pas les credentials GPS |
| backend/app/fleet/gps_alert_router.py et gps_alert_models.py | alertes GPS et acquittement, outbox liée à gps_alert_id | Domaine mécanique séparé, généralisation outbox à évaluer |
| backend/app/hse/router.py | incidents, actions correctives, idempotence utilisateur | Lien explicite aux incidents après validation métier |
| backend/app/billing/router.py | plans, abonnements, facturation interne | Évaluer droits de module et quotas existants |
| backend/app/main.py et frontend/src/App.tsx | monolithe modulaire, routes et menus métier | Ajouter une tranche verticale, pas de microservice |
| docs/LIVE_LOCATION_AND_INTERFACE.md | contrat GPS, protection machine, limites réseau | Ne pas modifier le contrat GPS |

Recherche de code non concluante : aucun résultat exploitable sur tpms, wheel, iot, tire, telematics. Cela ne prouve pas l'absence de code. Avant migration, inventorier arborescence complète, migrations, tests, permissions, flags, jobs, PR en cours et contrats OpenAPI au SHA retenu. Aucun test exécuté dans cet audit documentaire.

## Décision
Monolithe modulaire FastAPI/PostgreSQL existant. Adaptateurs OEM isolés derrière un contrat interne. Aucun broker ni stockage supplémentaire sans mesure de besoin. Unités canoniques kPa et Celsius; préserver unité originale et provenance. Ne jamais déduire desserrage d'une température. Ne jamais interpréter silence comme absence de danger. Alertes embarquées autonomes; aucun freinage ni immobilisation automatique. Seuils validés fabricant/exploitant HSE, pas de valeur universelle.

## Modèle proposé (noms provisoires)
iot_gateway, iot_sensor, sensor_binding, wheel_position (uniquement si référentiel existant insuffisant), iot_measurement, wheel_safety_alert. Clés composites tenant/site selon conventions; association temporelle véhicule/position et, pour TPMS, pneu. Capteur moyeu distinct du pneu; permutation et démontage ne doivent pas réattribuer rétroactivement les mesures. Interdire affectations simultanées incompatibles. Réutiliser véhicule, tyre et historique existants. Données append-only avec politique de rétention et index dimensionnés après mesure. Séparer explicitement simulation et matériel réel.

## Contrat interne candidat (non OEM)
POST /api/v1/iot/telemetry, credential machine dédié, révocable et limité à la passerelle. Corps exemple fictif :
```json
{"event_id":"demo-001","sensor_external_id":"demo-sensor","observed_at":"2026-11-26T12:00:00Z","metric":"HUB_TEMPERATURE","value":65,"unit":"CELSIUS"}
```
Types candidats : TYRE_PRESSURE, TYRE_TEMPERATURE, HUB_TEMPERATURE, WHEEL_LOOSENING (événement booléen/état distinct du numérique), BATTERY_LEVEL, SENSOR_STATUS. Tenant/site/véhicule résolus côté serveur; refuser champs de périmètre non autorisés. Valider capacité du capteur, unité, valeur finie, taille, âge, décalage horloge et identifiant. Déduplication durable par équipement et événement; collision de contenu rejetée; replay identique sans double effet. Horodatages observation/réception séparés. Événements tardifs ne régressent pas l'état courant; traiter incidents critiques tardifs selon politique HSE. Quarantaine si affectation ambiguë. Limites et timeouts avant transaction; pas de secret dans logs. Contrat versionné et OpenAPI régénéré.

## Alertes et interface
États distincts normal, warning, critical, unknown, stale, offline; résolution et acquittement séparés. Règles configurables et auditées, hystérésis et déduplication. Corrélation GPS uniquement si position suffisamment récente, avec âge affiché. Dashboard véhicule/roues, historique, sources et fraîcheur, état batterie si fourni, permissions par site. Créer un incident HSE ou ordre de travail via parcours autorisé et idempotent, sans usurper un compte humain. Outbox notifications à adapter sans casser GPS. Ne pas masquer une alerte active à cause d'une suspension commerciale; définir politique de désactivation et conservation avec HSE.

## Sécurité et commercialisation
Permissions candidates iot.device.read/manage, iot.telemetry.read, iot.alert.read/manage; matrice rôle/site avant implémentation. RLS forcée et tests inter-tenant, révocation, rotation, protection rejeu. Feature flag désactivé par défaut, contrôle serveur des droits commerciaux, audit des changements. Aucun changement des plans existants sans validation. Pas de revendication partenariat/certification non prouvée.

## Lots et gates
1. Inventaire exhaustif, SHA et CI de référence, ADR revue.
2. Référentiel et affectations, migration additive, contraintes et tests RLS.
3. Contrat d'ingestion et simulateur isolé, tests replay, révocation, données tardives.
4. Lecture par roue et tableau de bord; E2E avec données fictives.
5. Alertes et liens HSE/atelier, notifications, test déduplication.
6. Buffer gateway et reprise réseau; tester perte et reconnexion, fraîcheur.
7. Adaptateur ATLAS puis Wheely-Safe uniquement sur documentation officielle, échantillons et accès autorisés. Pas de payload OEM inventé.
8. Recette : migrations, couverture >=85% sans régression de référence, Ruff/mypy/pytest, typecheck/Vitest/build, Playwright, charge, restauration/rollback, vérification CI.
9. Pilote terrain avec installateur et HSE : compatibilité montage, alarmes locales sans réseau, températures et pression de référence, latence et pertes, transfert capteur, faux positifs/négatifs. Aucun test dangereux sur véhicule en mouvement. Validation production explicite.

## Dépendances externes
Documentation OEM, droits API, fréquence et protocole, gateway compatible, données échantillons, installation et garantie, validation environnement minier, conditions de distribution. Statut initial : EN ATTENTE FOURNISSEUR. Aucun accès ni compatibilité réelle établi.
