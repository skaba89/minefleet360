# Livraison — déclaration d'incident HSE hors ligne (premier parcours offline de bout en bout)

Branche `feature/offline-hse-sync`. Lot 4 du plan « réseau faible » (`docs/ROADMAP.md`) : première écriture métier
synchronisable. Pas de migration : la table `idempotency_record` (0039) est réutilisée.

## Parcours

1. Le dispatcher, l'atelier, le carburant ou le HSE ouvre l'application. Avec réseau : écran HSE habituel.
   Sans réseau au démarrage : si un **profil terrain** a été mémorisé lors d'une session précédente, l'application
   ouvre le **mode hors ligne restreint** (déclaration d'incident et file d'attente seulement).
2. La déclaration est enregistrée dans l'outbox IndexedDB (`/hse/incidents` est la seule route activée).
3. L'écran affiche « En attente de synchronisation ».
4. Au retour du réseau (événement `online`), toutes les 30 s tant qu'il reste des opérations, ou sur
   « Synchroniser maintenant », la file est envoyée **dans l'ordre de saisie**, sous verrou Web Locks exclusif
   par compte (un seul onglet envoie).
5. Chaque envoi est une requête authentifiée normale (`Authorization` en mémoire, cookie de rafraîchissement) :
   le serveur revérifie la permission `hse.incident.report`, le site actif dans la portée et l'engin.
6. `Idempotency-Key = operationId` : la clé est liée au tenant **et** au compte, le corps est empreinté (SHA-256)
   et la clé est finalisée dans la même transaction que l'incident. Un rejeu renvoie l'incident d'origine
   (`Idempotency-Replayed: true`) ; un corps différent sous la même clé est refusé (`IDEMPOTENCY_KEY_REUSED`).
7. L'écran affiche « Synchronisé — HSE-000123 » seulement après une réponse 2xx portant la référence serveur.

Envoi direct en ligne : la clé est générée avant l'envoi. Si la réponse se perd, la déclaration part dans la file
avec la **même** clé : le rejeu renvoie l'incident déjà créé (testé par E2E en coupant la réponse).

## Traitement des réponses

| Réponse | Effet |
|---|---|
| 2xx | « Synchronisé » + référence serveur |
| coupure, 429, 5xx | reste en attente, nouvel essai différé (backoff plafonné à 60 s) ; la passe s'arrête pour préserver l'ordre |
| 401 (après échec du rafraîchissement) | reste en attente, « reconnectez-vous » ; la passe s'arrête |
| 403, 404, 409, 422 | refus définitif affiché avec motif ; l'opération n'est jamais renvoyée ; la file continue |

## Sécurité et données locales

- Aucun jeton dans IndexedDB ni dans le profil terrain ; la charge passe le garde-fou des champs sensibles.
- Opérations filtrées par (espace, compte) à la lecture **et** à l'envoi ; aucune reprise sous un autre compte.
- **Changement assumé vs PR #296** : à l'**expiration** de session, les déclarations *en attente* du compte qui
  expire sont conservées (une purge totale détruirait des déclarations de sécurité) ; tout le reste est purgé, et
  tout ce qui dépasse 7 jours. La **déconnexion volontaire** purge toujours tout, après un avertissement listant les
  déclarations non envoyées.
- Profil terrain (`localStorage`) : espace, identifiant de compte, nom affiché, fuseau, sites où le compte peut
  déclarer. Pas d'e-mail ni de jeton. Supprimé à la déconnexion volontaire. Il ne donne aucun accès serveur.

## Vérifications exécutées

- Backend `tests/test_hse.py` : rejeu unique sans nouvel événement, clé liée au compte, clé réutilisée avec un autre
  corps, rôle retiré avant synchronisation (refus, rien créé), rollback d'un échec métier sans clé bloquée, clé
  malformée.
- Vitest : moteur de synchronisation (`hseOfflineSync.test.ts`, 16 cas : 2xx, coupure, 429/5xx, 403/409/422, 401,
  délai, reprise d'un envoi interrompu, autre compte, accusé incomplet, deux onglets, absence de Web Locks), écran
  (`HseOffline.test.tsx`), expiration de session (`AuthContext.test.tsx`).
- Playwright `e2e-field/hse-offline.spec.ts` sur build de production + service worker, **Chromium et émulation
  Android Pixel 7** : déclaration sans réseau puis synchronisation unique, réponse perdue sans doublon, deux onglets,
  ouverture de l'application sans réseau puis reconnexion, avertissement à la déconnexion. Ajouté au workflow
  `e2e-isolation`.

Défaut corrigé au passage : sur téléphone, le bandeau fixe « Mode hors ligne » masquait le bouton d'envoi des
formulaires en bas de page.

## Limites

- Essai sur **appareil Android réel** et réseau mobile instable non réalisé (émulation uniquement).
- Pas de synchronisation en arrière-plan quand l'application est fermée (Background Sync non utilisé) : la file part
  à la prochaine ouverture avec réseau.
- Sélection d'engin indisponible hors ligne (liste non mise en cache) ; photos non prises en charge.
- Si le rôle d'un utilisateur change pendant qu'il est hors ligne, le profil terrain reste celui de la dernière
  session jusqu'au retour du réseau ; le serveur refuse alors les déclarations non autorisées.
