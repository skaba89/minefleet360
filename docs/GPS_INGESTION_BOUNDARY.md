# GPS-23 — adaptateur strict vers l’ingestion transactionnelle

## Contrat livré

`POST /api/v1/gps/telemetry` reçoit actuellement le contrat serveur `minefleet-json-v1`. La route authentifie une clé machine opaque, borne la lecture du corps et ne permet jamais au traceur de fournir le tenant, le site, le véhicule, le secret ou l’identifiant d’adaptateur dans le JSON.

`accept_gps_telemetry_payload` reçoit séparément :

- les octets non fiables ;
- un contexte tenant déjà établi ;
- le secret machine ;
- l’heure de réception serveur ;
- un identifiant d’adaptateur choisi côté serveur.

Le registre transforme le format externe en `GpsDeviceMessage`. La chaîne commune résout ensuite l’association persistée, applique RLS, authentification, fenêtre temporelle, séquence anti-rejeu et écriture atomique.

## Contrôles communs

| Contrôle | Comportement |
|---|---|
| Adaptateur absent, inconnu ou identifiant invalide | Refus avant authentification ou accès base |
| Message vide ou au-delà de la limite déclarée | Refus avant décodage |
| Clé JSON répétée, JSON mal formé, profondeur excessive | Refus explicite pour `minefleet-json-v1` |
| Tenant, site, véhicule, secret ou choix d’adaptateur dans le corps | Refus du schéma strict |
| Date sans fuseau, coordonnées impossibles, séquence non entière | Refus du schéma normalisé |
| Erreur de validation | Code stable et message neutre ; corps et détails non exposés |
| Secret absent, incorrect ou révoqué | Refus dans la chaîne d’authentification |
| Point antérieur à l’association actuelle | Refus même avec le secret actuel |
| Séquence rejouée | Aucune nouvelle position |
| Timestamp déjà présent avec une séquence supérieure | Savepoint annulé ; séquence non avancée |
| Rollback de l’appelant | Position et séquence annulées ensemble |

La limite de 16 Kio appartient au contrat `minefleet-json-v1`. Chaque futur adaptateur doit déclarer sa propre borne, au maximum 1 Mio dans le registre, puis être confronté au protocole réellement retenu.

## Sélection de l’adaptateur

Le client HTTP ne transmet pas d’en-tête ou de champ permettant de sélectionner un décodeur. La route publique actuelle utilise seulement `minefleet-json-v1`. Une intégration fournisseur devra associer l’adaptateur à une configuration serveur authentifiée, avec une route ou passerelle dédiée si le transport diffère.

Ce choix empêche un appareil de demander un parseur plus permissif et évite qu’un nom de fournisseur soit traité comme une preuve de compatibilité.

## Sémantique du résultat

`True` signifie qu’une nouvelle position est insérée dans la transaction courante ; sa durabilité dépend du commit de l’appelant. `False` peut signifier doublon ou refus et ne constitue pas un accusé fournisseur universel.

Les erreurs de structure lèvent `AppError("VALIDATION_ERROR")` sans inclure le corps, le secret, les coordonnées ou les détails Pydantic dans la réponse.

## Réaffectation d’un traceur

Un point relevé avant la nouvelle association mais reçu après la réaffectation ne doit pas être attribué au nouveau camion. La prévalidation exige `position.recorded_at >= binding.active_from`. L’import d’un historique d’ancienne association n’est pas autorisé par cette chaîne.

## Validation

Les tests unitaires couvrent charges hostiles, confidentialité, registre dupliqué/inconnu, limite par adaptateur, sélection serveur et absence de commit implicite. Le test PostgreSQL couvre association réaffectée, empreinte du secret, RLS, séquence, position, savepoint, rollback, révocation et lecture API.

## Limites restantes

Le registre est une architecture d’extension, pas une certification. Aucun décodeur Teltonika ou Queclink n’est livré. Chaque constructeur/modèle/firmware exige spécification, fixtures autorisées, transport sécurisé, tests de laboratoire, charge staging et essai physique documenté selon `docs/GPS_FOURNISSEUR_CAHIER.md`.
