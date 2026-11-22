# GPS téléphone durable — contrat P0 de sécurité et de recette (proposé)

Base : main@e5ee515b, suite de #488. Ce contrat est soumis à validation humaine avant toute persistance de coordonnées. Il ne crée aucune capacité opérationnelle et ne change ni permissions, ni schéma, ni API existante.

## État constaté

- `frontend/src/pages/PhoneTrackingPage.tsx` : acquisition explicite après consentement et création d'un partage en ligne ; cadence ~10 s, arrêt lors de sortie, expiration ou interdiction ; mémoire effacée.
- `frontend/src/lib/phoneGpsMemoryBuffer.ts` : 12 points, 100 s ; expiration/saturation impliquent des pertes ; fermeture et suspension navigateur aussi.
- `backend/app/fleet/gps_live_router.py` et `gps_live_service.py` : API position unitaire 204, permission fleet.gps.share, verrou utilisateur/partage, tenant + compte, vérification session exacte, véhicule/site/autorisations, partage maximum 12 h, horodatage entre max(début, maintenant - 2 min) et maintenant + 5 s, ordre strict, intervalle serveur 5 s.
- `FleetGpsPhoneShare` garde session, compte, site, véhicule et timestamps ; nouvelles sessions ne peuvent pas envoyer sur l'ancien partage. Démarrer un nouveau partage arrête l'ancien.
- `offline-outbox.ts` n'est pas un coffre GPS : liste blanche d'opérations métier, séparation logique par identité ; le filtre de secrets ne démontre pas un chiffrement de coordonnées. Ne pas étendre cette liste blanche au GPS.
- API traceurs et GPS téléphone ont des frontières d'identité différentes ; aucune réutilisation de credentials traceur sur téléphone.

## Décisions proposées et limites

1. Conserver intégralement l'API temps réel et ses limites. Créer une voie de rattrapage séparée, désactivée par défaut, qui ne change pas la signification de la position récente.
2. Priorité à Android natif à stockage privé, chiffrement authentifié et clé protégée par Android Keystore. Pour PWA, ne pas présenter IndexedDB ou une clé WebCrypto persistée dans la même origine comme équivalent au coffre natif : une XSS active peut accéder aux données via l'application. Maintenir le tampon volatile tant qu'un modèle de menace PWA spécifique n'est pas accepté.
3. Candidat pilote conservateur : collecte uniquement sur un partage démarré en ligne et explicitement consenti, limité à sa durée (12 h actuellement). Cible initiale 10 s/point, maximum 4 320 points/partage et 12 h d'âge au rejeu, à valider avec le métier et la sécurité. Pas de prolongation locale automatique, ni de démarrage sans serveur. Taille maximale de la file et octets réellement mesurés sur appareil.
4. Pour la première livraison, identité et session d'origine strictement identiques. Redémarrage de l'application peut reprendre seulement après vérification serveur du même partage et même session. Si réauthentification crée une autre session : ne pas transférer les points ; arrêter, purger selon la politique approuvée, afficher le nombre de points abandonnés. Un futur transfert inter-session nécessitera un contrat distinct et ne doit pas être activé implicitement.
5. Hors ligne, la révocation distante ne peut pas être connue immédiatement. Stop local immédiat, absence de nouvelle acquisition au plus tard à expiration locale (horloge monotone utilisée pour la durée) ; à reconnexion le serveur réévalue tous les droits et l'appartenance. Aucun rejeu après arrêt, révocation, changement de compte/site/véhicule ou expiration du partage dans cette première tranche.
6. Coupures de 24/72 h : tests de dégradation et arrêt honnête ; pas une promesse de couverture 72 h. La continuité prolongée exige une évolution du partage, validée séparément, ou un traceur autonome.

## Architecture cible du premier incrément

Flux : acquisition consentie → validation et écriture locale atomique → file chiffrée par partage → lot borné HTTP authentifié → validation et transaction serveur → acquittement par point → retrait local après acquittement. Aucun envoi en arrière-plan PWA ; Android service de localisation visible et soumis aux restrictions OS.

Identité locale : tenant, compte, session, site, véhicule et partage d'origine en métadonnées minimisées (ou données chiffrées) ; ce ne sont jamais des preuves d'autorisation. Les clés d'authentification, jetons, cookies et secrets GPS ne sont jamais dans la file et les coordonnées jamais dans les logs, audit, analytics, notifications, crash reports ou sauvegardes cloud mobiles. Exclure fichiers/DB de la sauvegarde Android. Stocker uniquement les mesures nécessaires. Clé de chiffrement indépendante par partage, nonce unique par enregistrement, contexte authentifié lié au partage et identifiant de point ; effacement logique de la file et destruction de la clé sur purge. Pas de promesse d'effacement physique flash. En cas de stockage saturé, refuser nouvelle acquisition conformément au plafond, afficher un compteur explicite ; aucune éviction invisible.

## Contrat API candidat (non implémenté)

Route proposée POST /me/gps/shares/{share_id}/deferred-positions ; modèle strict, lot borné à 100 points et 64 KiB avant parsing, limites ajustables après mesure. Enveloppe sans tenant/site/vehicle/user ni jeton, points : client_point_id UUID stable, recorded_at UTC avec fuseau, latitude/longitude, accuracy_m, speed_kmh, heading_deg (mêmes validations strictes que PhonePointIn). L'identifiant est généré une seule fois à l'acquisition.

Serveur : même Require(fleet.gps.share), _lock_user et _share, même session, partage actif et non expiré, _vehicle et site égaux, vérifications d'affectation et de droits courants. Valider chaque capture dans [started_at, min(expires_at, received_at + 5 s)], âge maximum candidat 12 h ; limiter la cadence de capture (validation de cohérence et quotas, pas une preuve anti-spoofing). Tout lot sous identité interdite est rejeté globalement avant inspection du contenu opérationnel.

Contrainte unique par tenant + partage + client_point_id ; hash canonique des champs, même ID/corps renvoie duplicate, même ID/corps différent renvoie conflict, jamais de second effet. Pour éviter le double enregistrement par voie unitaire, un même point appartient exclusivement à l'un des deux canaux (choisi lors de l'acquisition) ; ne jamais tenter la voie différée après un envoi live ambigu. Idempotence et position dans une seule transaction, pas de résultat accepté avant commit. Les points historiques n'écrasent pas la position courante : conserver recorded_at et received_at, classifier retards, exclure les effets alertes live ; recalcul géofences historique explicitement hors périmètre. Évaluer le stockage nécessaire et la rétention des clés d'idempotence au moins égale à la fenêtre de rejeu, sans prolonger celle des positions.

Réponse 200 par lot validé avec liste par client_point_id : accepted, duplicate, rejected (code stable et générique) ou conflict ; erreurs globales 401/403/404 arrêt sans fuite, 429 Retry-After / 5xx réseau backoff exponentiel plafonné. Rejeu identique après réponse perdue ne crée ni position ni alerte supplémentaire. Réponse absente ou malformée ne vaut pas succès. Les rejets définitifs sont comptés et visibles, points purgés selon sensibilité ; jamais automatiquement modifiés ni transférés à un nouveau partage.

## Matrice d'autorisation

| Acteur | Lire sa file | Écrire/rejouer | Lire un autre partage |
|---|---|---|---|
| Conducteur / compte autorisé, affectation active | Oui, uniquement statut et compteur de son partage | Oui si toutes les vérifications ci-dessus passent | Non |
| Même compte, nouvelle session ou site | Non | Non | Non |
| Administrateur/direction | Jamais via stockage local d'autrui | Non pour le compte d'autrui | Seulement lecture serveur existante sous RBAC/RLS |
| Traceur machine | Non | Non, route télématique dédiée | Non |

## Menaces et tests de recette obligatoires

| ID | Scénario | Critère |
|---|---|---|
| GPS-D01 | 5 min hors réseau, même partage/session | chaque point éligible acquitté une seule fois ; horodatage d'origine intact |
| GPS-D02 | Réponse perdue, double envoi concurrent | un enregistrement ; même ID/contenu différent rejeté ; rollback sans acquittement |
| GPS-D03 | Tardif, désordonné, nouveau point live | historique distinct ; dernier état jamais rétrogradé ; aucune alerte live historique |
| GPS-D04 | IDOR partage/tenant/site, session différente | rejet sans fuite ni effet, y compris sous RLS et deux workers |
| GPS-D05 | Retrait droit, affectation finie, changement véhicule/site, révocation | refus avant insertion, purge locale visible |
| GPS-D06 | Stop hors réseau, redémarrage, expiration 12 h, horloge modifiée | arrêt capture, aucune reprise interdite ; compteur abandonné sans coordonnées |
| GPS-D07 | Stockage inspecté, extraction de sauvegarde, XSS et clé inaccessible | pas de coordonnées en clair dans DB/logs/backup ; modèle de menace et limites documentés |
| GPS-D08 | Saturation, lot trop gros, valeurs NaN ou coordonnées hors limites, date future | erreur explicite, mémoire et DB bornées |
| GPS-D09 | 64/128/256 kbps, pertes, 429/5xx, reconnexions oscillantes | consommation et durée de rattrapage mesurées ; pas de boucle infinie |
| GPS-D10 | Écran verrouillé, OS suspend, batterie faible, fermeture/reboot | vérifier deux Android physiques ; afficher comportement réel, pas de garantie artificielle |
| GPS-D11 | Coupure 24/72 h | arrêt à expiration, aucun point ancien présenté comme actuel |
| GPS-D12 | Ancien endpoint unitaire et traceurs | non-régression auth, 2 min/5 s, alertes, SSE et isolation |

## Lots et approbations

- D0 : ce contrat, revue humaine sécurité/produit et arbitrage rétention, usage légal et plafonds ; aucune persistance activée.
- D1 : API différée et migration additive, tests intégrés PostGIS, RLS, concurrence et OpenAPI/RBAC ; feature flag désactivé.
- D2 : stockage Android isolé, purge, tests cryptographiques et lifecycle ; ne pas modifier la PWA volatile.
- D3 : synchronisation, indicateurs origine/fraîcheur et acquittements, mesures réseau ; tests E2E et Android physique.
- D4 : pilote terrain avec politique de confidentialité validée, équipements, preuve RPO/RTO et supervision ; validation client.

Ne pas déployer en production, modifier le partage actuel, affaiblir une permission, ou augmenter le score de maturité à partir du seul document. Les validations techniques, terrain et commerciales restent distinctes.
