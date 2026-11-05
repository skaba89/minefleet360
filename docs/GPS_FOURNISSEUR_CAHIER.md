# Intégration d’un fournisseur de traceurs GPS — éléments à obtenir

Décision déléguée D-DEL-06 (2 novembre 2026) : **aucun décodeur constructeur n’est développé sans la spécification réelle du fournisseur** (format, authentification, horodatage). Un décodeur écrit à l’aveugle produirait des positions fausses ou mal datées.

## Point d’entrée existant

Les traceurs peuvent envoyer une position à `POST /api/v1/gps/telemetry` avec le contrat `minefleet-json-v1` : JSON HTTPS, secret par traceur révocable et séquence anti-rejeu. Si le fournisseur sait pousser ce format, aucun décodeur spécifique n’est nécessaire.

## Architecture d’adaptateurs

Le module `backend/app/fleet/gps_payload_adapters.py` fournit un registre fermé et versionné :

- l’adaptateur est sélectionné par la configuration serveur, jamais par le corps du traceur ;
- chaque adaptateur déclare un identifiant canonique, un fournisseur, un protocole, une version et sa limite de taille ;
- le résultat est toujours un `GpsDeviceMessage` normalisé, sans tenant, site, véhicule ni secret ;
- l’authentification, la résolution de l’association serveur, l’anti-rejeu et l’écriture atomique restent communs ;
- un identifiant dupliqué, invalide ou inconnu est refusé avant toute écriture ;
- aucun chargement dynamique de code ou plugin fourni par un tiers n’est autorisé.

Le registre ne contient actuellement que `minefleet-json-v1`, explicitement marqué **non certifié matériellement**. Teltonika, Queclink et les autres fabricants ne sont ni enregistrés ni annoncés compatibles à ce stade.

## À obtenir du fournisseur par écrit

| Sujet | Questions |
|---|---|
| Modèle exact | Référence commerciale, variante matérielle et version de firmware testée ? |
| Mode | Poussée, TCP/UDP propriétaire, webhook ou interrogation d’API ? Fréquence et volume ? |
| Format | Spécification exacte, unités, encodage, checksum et exemples réels anonymisés ? |
| Horodatage | Heure GNSS ou réception, fuseau, résolution et comportement sans fix ? |
| Identité | IMEI ou numéro de série stable, remplacement et réaffectation d’un boîtier ? |
| Authentification | Secret, HMAC, certificat client, IP source, rotation et révocation ? |
| Fiabilité | Stockage embarqué, rejeu après coupure, ordre, doublons, accusés réseau ? |
| Qualité | Précision, satellites, vitesse, cap, contact, compteur et batterie ? |
| Événements | Choc, entrée/sortie, batterie, bouton d’urgence : format et sémantique ? |
| Contrat | Hébergement, conservation, sous-traitance, réversibilité et support ? |
| Test | Bac à sable et boîtier physique avec SIM/réseau représentatifs ? |

## Cycle obligatoire d’un nouvel adaptateur

1. Créer un identifiant distinct par protocole/version ; ne jamais remplacer silencieusement un décodeur existant.
2. Ajouter des fixtures fournisseur expurgées et autorisées, sans IMEI réel, coordonnées sensibles ni secret.
3. Tester les unités, fuseaux, timestamps invalides, absence de fix, limites, checksum et charges hostiles.
4. Vérifier authentification, révocation, réaffectation, doublons, messages hors ordre et rejeu après coupure.
5. Mesurer charge, pertes et latence sur staging.
6. Tester le couple modèle + firmware + réseau sur matériel réel.
7. Enregistrer le rapport daté et son périmètre avant de déclarer une compatibilité.

Une validation de fixtures ou de CI ne vaut pas certification matérielle. La certification ne concerne que le couple modèle/firmware/protocole réellement essayé.
