# GPS-23 — message JSON strict vers l'ingestion transactionnelle

## Contrat livré

`accept_gps_telemetry_payload` reçoit des octets JSON, un contexte de
passerelle déjà authentifié, un secret séparé et l'heure de réception serveur.
Le corps est validé par `GpsTelemetryIn`, puis converti en
`GpsDeviceMessage` et transmis à la chaîne existante.

Le JSON n'apporte jamais l'identité de société, de site ou de véhicule.
Le contexte fiable est fourni par l'appelant et l'association persistée
résout le véhicule. L'appelant doit établir le contexte RLS de cette même
société avant l'appel et conserver la responsabilité du commit/rollback.

| Contrôle | Comportement |
| --- | --- |
| Message vide ou supérieur à 16 Kio | Refus avant accès base |
| Clé JSON répétée, JSON mal formé, profondeur excessive | Refus explicite |
| Tenant, site, véhicule ou secret dans le corps | Refus du schéma strict |
| Date sans fuseau, coordonnées impossibles, séquence non entière | Refus du schéma strict |
| Erreur de validation | Code stable, message neutre ; corps et détails de validation non exposés |
| Secret absent, incorrect ou révoqué | Refus dans la chaîne d'authentification du traceur |
| Point antérieur à l'association actuelle | Refus même si le secret actuel est valide |
| Séquence rejouée | Aucune nouvelle position |
| Timestamp déjà présent avec une séquence supérieure | Savepoint annulé ; séquence non avancée |
| Rollback de l'appelant | Position et séquence annulées ensemble |

Le seuil de 16 Kio borne le coût du décodage d'un point individuel ; il
ne décrit pas un protocole fournisseur et devra être confronté à celui
retenu. Les limites temporelles existantes du point GPS restent appliquées.

## Sémantique du résultat

`True` signifie qu'une nouvelle position a été insérée dans la transaction
courante. Sa durabilité dépend du commit de l'appelant.
`False` peut signifier un doublon ou un refus : ce résultat n'est donc
**pas** un accusé de succès fournisseur et ne doit pas être converti
automatiquement en acquittement réseau.

Les erreurs de structure lèvent `AppError("VALIDATION_ERROR")` sans
inclure le corps, le secret ou les détails Pydantic dans la réponse.

## Réaffectation d'un traceur

Exemple : un traceur est réaffecté à 12 h. Un point relevé à 11 h 55,
reçu à 12 h 05 avec le secret de l'association actuelle, ne doit pas être
attribué au nouveau camion. La prévalidation vérifie désormais que
`position.recorded_at >= binding.active_from`.

Cette protection est conservatrice : l'import d'un historique d'ancienne
association n'est pas autorisé par cette chaîne.

## Validation

Les tests unitaires couvrent les charges hostiles, la confidentialité des
erreurs et l'absence de commit implicite.
Le test PostgreSQL parcourt la chaîne complète : association réaffectée,
empreinte de secret persistée, RLS, séquence, position, savepoint, rollback
externe, révocation et lecture API des dernières positions.

## Prochaine étape fournisseur

Aucune route réseau d'ingestion n'est déclarée par cette tranche.
L'adaptateur devra définir le transport réel, authentifier la passerelle,
résoudre le tenant côté serveur, appliquer sa limite de débit et son
acquittement/idempotence fournisseur. Le secret du traceur et un tenant
librement fourni dans un en-tête ne suffisent pas à établir ce contexte.
