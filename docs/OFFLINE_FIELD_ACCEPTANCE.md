# Contrat de recette — opérations terrain en réseau faible

> Statut : spécification de tests et de livraison. Ce document ne signifie **pas** que les écritures offline sont déjà opérationnelles.

## État de référence

- Le shell PWA est disponible hors ligne et ne doit pas cacher les réponses `/api/`, les tokens ou les secrets.
- La synchronisation d'écritures métier n'est pas encore livrée. Une opération hors ligne doit donc être signalée comme indisponible tant que l'outbox n'est pas activée pour le parcours choisi.
- Le premier parcours doit être append-only (constat terrain non financier), sans modification concurrente d'un objet existant.

## Lots et critères d'acceptation

### A. Idempotence côté serveur (pré-requis)

1. Recevoir une clé d'idempotence opaque, générée par opération, associée au tenant, à l'utilisateur, à la méthode, à la route et au hash canonique du corps.
2. Première requête : exécuter l'effet métier et enregistrer atomiquement le résultat et son état.
3. Même clé, même portée et même corps : renvoyer le résultat convenu sans créer de deuxième écriture.
4. Même clé avec un corps différent : répondre 409 sans exécuter d'effet.
5. Même clé utilisée dans un autre tenant/utilisateur : ne jamais exposer l'opération originale. L'autorisation reste vérifiée à chaque requête.
6. Deux requêtes concurrentes avec même clé : au plus un effet métier, y compris sous deux workers.
7. Définir et tester la durée de rétention et le nettoyage des clés ; aucune clé ou donnée personnelle dans les logs.
8. Tester le rollback (erreur DB/crash) : pas de résultat idempotent marqué réussi si l'effet métier est annulé.

### B. Cache de lecture

- IndexedDB pour les seules données explicitement autorisées, avec cloisonnement tenant + compte + site et version de schéma.
- Purge à la déconnexion, révocation de session et changement de compte ; ne pas conserver access token, refresh token ni secrets GPS.
- Interdire le cache HTTP des réponses API privées ; documenter une politique de rétention et de capacité locale.
- Les contenus historiques affichés hors ligne montrent clairement leur date de dernière synchronisation.

### C. Première outbox terrain

- Créer une entrée stable `operation_id` et une clé d'idempotence par action explicite.
- États distincts : `en_attente`, `en_cours`, `synchronisee`, `rejetee`, avec cause lisible en français.
- Rejouer les opérations FIFO pour un même périmètre, avec verrouillage pour éviter deux synchroniseurs simultanés.
- Réseau indisponible/5xx/429 : nouvelle tentative avec backoff borné, sans duplication.
- 401 : suspendre et exiger une réauthentification ; 403 : rejeter, sans changer le périmètre ; 409/422 : bloquer l'opération et proposer une correction humaine, pas de réécriture silencieuse.
- Afficher nombre d'actions en attente et statut par action ; ne jamais afficher « synchronisée » avant acquittement serveur.
- Déconnexion/changement de compte : ne jamais rejouer les opérations sous une autre identité ; conserver ou purger la file selon une politique explicite et sécurisée.
- GPS et opérations sensibles : aucun envoi en arrière-plan sans autorisation et consentement adaptés.

## Tests exigés avant activation

| ID | Scénario | Attendu |
| --- | --- | --- |
| OFF-01 | Création hors ligne, reconnexion | exactement une opération serveur, état synchronisé |
| OFF-02 | Réponse serveur perdue puis rejeu | aucun doublon |
| OFF-03 | Deux onglets synchronisent simultanément | un seul effet et statut cohérent |
| OFF-04 | Même clé, corps différent | 409, aucune nouvelle écriture |
| OFF-05 | Changement de compte/tenant avant reconnexion | aucune fuite ni écriture inter-tenant |
| OFF-06 | Expiration de session au rejeu | suspension 401, réauthentification |
| OFF-07 | Permissions retirées avant rejeu | refus 403, aucune écriture |
| OFF-08 | Payload invalide ou conflit métier | 422/409 visible, sans boucle infinie |
| OFF-09 | Fermeture/rechargement du navigateur | reprise sans perte ni duplication |
| OFF-10 | Réseau oscillant/latence forte | backoff, état honnête, aucune opération fantôme |
| OFF-11 | Déconnexion + purge cache | absence de secrets et de données d'un autre compte |
| OFF-12 | Test RLS multi-site sous charge | aucune fuite inter-site |
| OFF-13 | Échec après début transaction | rollback et rejeu sûr |
| OFF-14 | PWA offline et contrôle réseau | aucune réponse `/api/` mise en cache par service worker |

## Conditions de fusion des PR d'implémentation

- PRs ciblées : serveur idempotent → tests concurrence/tenant → cache lecture → outbox premier parcours → UI états → E2E réseau réel.
- Tests backend Ruff, mypy, pytest avec seuil de couverture, migrations PostgreSQL/PostGIS et tests RLS.
- Typecheck, Vitest, build React et Playwright sur parcours connecté/déconnecté.
- Essai sur téléphone Android d'entrée de gamme avec réseau intermittent, sans promesse de synchronisation tant que le parcours n'est pas validé.
- Validation humaine requise avant fusion ; ne jamais fusionner sur la seule présence de tests verts.

## Hors périmètre

La synchronisation GPS en arrière-plan, les mutations financières, la modification hors ligne de stocks quantifiés et les résolutions automatiques de conflits ne font pas partie de ce premier lot.
