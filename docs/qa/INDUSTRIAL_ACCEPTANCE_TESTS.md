# Tests d'acceptation industrielle — plan de preuve

Ce document décrit des essais à exécuter sur environnement isolé ou staging autorisé. Les scénarios qui suivent ne sont pas déclarés réussis. Aucun essai matériel réel ou charge sur infrastructure de production ne doit être simulé à partir de ce texte.

## Environnements et données

- Staging isolé de production, migration depuis snapshot fictif, rôles distincts, secrets temporaires.
- Deux tenants A et B, deux sites au minimum, utilisateurs par rôle.
- Véhicules, conducteurs, missions et événements synthétiques; aucune coordonnée d'employé réelle.
- Pour tester GPS offline durable, attendre l'architecture de chiffrement et le plan de suppression, puis obtenir validation sécurité.
- Pour essais de matériel, consigner modèle, numéro d'essai pseudonymisé, firmware, SIM/opérateur, configuration et horloge; ne jamais publier secrets ni positions.
- Charger les seuils p95/p99 et volumes convenus avant benchmark. Sans seuil signé, le test rapporte des mesures sans verdict de conformité.

## Scénarios d'acceptation

| ID | Niveau | Scénario / preuve attendue | Sécurité | Résultat attendu |
|---|---|---|---|---|
| AUTH-01 | API/E2E | anonyme, session expirée, utilisateur désactivé et rôle insuffisant | endpoints retournent des erreurs sans données sensibles | 401/403 cohérent; aucun accès par URL devinée |
| TEN-01 | API/DB | tenant A lit/modifie l'identifiant appartenant à B; même test pour site non attribué | RLS et contrôle applicatif sous rôle normal | objet B invisible/non modifiable et aucune fuite par compte, audit ou message |
| TEN-02 | DB | transaction avec erreur/rollback puis nouvelle requête sur connexion poolée | contexte tenant doit être réinitialisé | requête suivante sans contexte échoue fermée ou utilise le tenant autorisé |
| GPS-01 | API synthétique | vitesse, cap, horodatage invalide, doublon, message tardif et hors ordre | appareil autorisé, credential révoqué, mauvais tenant | événement conforme idempotent; refus explicite des valeurs invalides; ordre établi par temps de mesure |
| GPS-02 | matériel | modèle/firmware choisi envoie message, perte réseau, tampon appareil, rejeu | authentification, rotation/révocation, secrets masqués | paquet décodé sans perte silencieuse; aucune compatibilité déclarée avant compte-rendu |
| GPS-03 | UI | dernière position, signal ancien, aucun signal, mouvement/arrêt, historique et replay | filtrage par société/site et permission | carte/table cohérentes; dernière mesure et heure clairement affichées; donnée simulée étiquetée |
| GPS-04 | alertes | entrée/sortie geofence, survitesse, perte signal, retour en ligne, paquet vieux | pas d'alerte pour donnée d'un autre tenant | ouverture/fermeture et notification dédupliquées; acteur et mesure traçables |
| GPS-05 | SSE | abonnement valide, refusé, reconnecté, saturation, perte DB et repli REST | fermeture immédiate quand session/permission révoquée | flux borné; UI non figée; rattrapage; données tenant correctes; événements non durables explicitement tolérés |
| GPS-06 | charge | volumes synthétiques multiples et concurrence utilisateur (valeurs à convenir) | jetons lecture minimaux et environnement autorisé | bruts p50/p95/p99, CPU/RAM, pool DB, perte/doublons et latence ingestion→UI exportés |
| OFF-01 | Android physique | permissions GPS, arrière-plan, écran verrouillé, manque réseau, reconnexion, logout | révocation et changement compte/tenant | comportement réel documenté par OS/version; aucune promesse universelle |
| OFF-02 | métier | incident HSE hors ligne, double clic, conflit, retry, expiry, révocation | outbox scoppée au tenant/utilisateur | une seule création idempotente, ordre préservé ou conflit explicite, suppression au logout |
| OPS-01 | sauvegarde | créer sauvegarde fictive, chiffrer/transférer dans cible isolée, restaurer en réseau désactivé | ne jamais utiliser prod; stockage temporaire protégé | tables/migrations contrôlées, durée de restauration, résultat purge/alerting documentés |
| OPS-02 | déploiement | déployer staging depuis version/tag, health/readiness, migration, rollback | secrets hors logs et sans permission owner en API | version visible, aucune migration destructive non réversible non revue, rollback démontré |
| OBS-01 | incident | provoquer indisponibilité DB/worker et échec job planifié | données et secrets non exposés dans log | alerte reçue et acquittée, délai mesuré, procédure exécutée |
| MINE-01 | atelier | panne→diagnostic→OT→réservation pièce→travail→validation→remise en service | séparation des tâches si configurée | coûts et temps recalculables depuis événements, historique conservé |
| MINE-02 | opérations | mission, rotations, pesée, changement véhicule et conflit dispatcher | source de pesée tracée | tonnage issu d'une mesure/entrée identifiée; GPS ne devient jamais une pesée |
| MINE-03 | carburant/stock | approvisionnement→distribution→rapprochement→écart et cycle pneu | autorisations de site et audit | unités, corrections, valorisation et écarts reproductibles |
| PRIV-01 | confidentialité | export, correction, rétention, suppression ou gel légal | test à deux comptes/deux tenants | réponse conforme à la politique validée et preuve d'audit minimale |

## Rapport de résultat obligatoire

Pour chaque exécution, archiver : commit, date/heure, environnement, configuration anonymisée, version navigateur/OS, commandes et scripts, noms des tests, résultat, traces expurgées, latence/ressources et écarts. Ajouter la limite connue (simulateur, mock, matériel réel, réseau simulé ou terrain). Un résultat de CI ne vaut pas recette client.
