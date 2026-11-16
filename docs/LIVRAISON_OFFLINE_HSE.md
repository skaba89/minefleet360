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

## Extension aux inspections HSE — tranche 1 : contrat serveur idempotent (16 novembre 2026)

Prérequis de la file hors ligne des inspections (phase 3 de la mission « validation terrain ») :
`POST /hse/inspections` accepte désormais `Idempotency-Key` avec **exactement** le contrat des incidents —
clé liée au tenant **et** au compte, corps empreinté (SHA-256), clé finalisée dans la transaction de
l'inspection, rejeu → inspection d'origine + `Idempotency-Replayed: true`, corps différent →
`IDEMPOTENCY_KEY_REUSED`. Sans clé, le comportement est inchangé. Pas de migration (table `idempotency_record`).

Garanties testées (`backend/tests/test_hse_inspections.py`) : création unique au rejeu, **aucun numéro
consommé** ni second événement d'audit `hse.inspection.create` ; clé d'un autre compte sans effet ; échec métier
(engin hors site) sans clé bloquée ; **modèle de checklist désactivé pendant l'attente du réseau** → refus
définitif `REFERENCE_NOT_FOUND`, rien n'est créé ; rôle retiré avant synchronisation → 401/403, rien n'est créé ;
clé malformée → 422.

Reste (tranches suivantes) : mise en cache des modèles actifs et des engins du site dans le profil terrain,
file IndexedDB + écran hors ligne des inspections (réutilisation du moteur `hseOfflineSync`), E2E Chromium +
émulation Android, puis essai sur appareil réel (`docs/qa/PROTOCOLE_ESSAI_ANDROID_REEL.md`). Les photos de
preuve restent en ligne uniquement.

## Extension aux inspections HSE — tranche 2 : file hors ligne côté application (16 novembre 2026)

- `/hse/inspections` rejoint la liste blanche de la file IndexedDB (`offline-outbox.ts`), avec `/hse/incidents`.
- Le moteur (`hseOfflineSync.ts`) envoie chaque opération vers sa route et n'accepte comme accusé de réception
  que l'identifiant et la référence serveur de cette route (`hse_inspection_id` + `INS-000123`). Inspections et
  déclarations partagent la file, l'ordre de saisie, le verrou Web Locks par compte et la politique de rejeu.
- Formulaire d'inspection : clé d'idempotence générée **avant** l'envoi ; hors ligne → file (« Enregistrer sur
  l'appareil ») ; réponse perdue (`status 0`) → file avec **la même clé** ; refus serveur → jamais mis en file.
- Libellé local `summary` (nom et version de la checklist) pour l'affichage de la file : **jamais envoyé** (schéma
  strict côté API).
- La page Inspections affiche et synchronise la file (lien « Ouvrir » vers `/hse/inspections/<id>`).

Vérifications : Vitest 275/275 (10 nouveaux, dont 6 qui échouent sans l'implémentation), `tsc` OK ; E2E
`e2e-field/hse-inspection-offline.spec.ts` (Chromium + émulation Android) : saisie hors ligne puis
synchronisation unique, réponse perdue sans doublon — exécutés en CI uniquement.

Limites de cette tranche : la checklist et les engins doivent avoir été chargés **avant** la coupure (coupure en
cours de session). L'ouverture de l'application sans réseau pour une inspection (modèles et engins mis en cache
dans le profil terrain) est la tranche 3. Photos : en ligne uniquement. Appareil Android réel : non essayé.

## Extension aux inspections HSE — tranche 3 : ouverture de l'application sans réseau (16 novembre 2026)

- **Kit d'inspection hors ligne** (`lib/offlineInspectionKit.ts`, `localStorage`, clé
  `minefleet-field-inspection-kit-v1`) préparé à l'ouverture de la page Inspections **en ligne** : sites où le
  compte a `hse.inspection.perform` (10 au plus), checklists **actives** (définitions seulement), engins de ces
  sites (identifiant + numéro de parc, seulement si `fleet.vehicle.read`). Mêmes requêtes et même cache que le
  formulaire en ligne.
- **Données locales — changement assumé** : le profil terrain restait sans donnée métier ; le kit ajoute des
  définitions de checklists et des numéros de parc. **Aucune donnée personnelle, aucun jeton.** Garde-fous : champs
  copiés un à un (rien d'inattendu ne transite), bornes (50 sites, 50 checklists, 100 points, 1 000 engins),
  validation stricte à la relecture, **lié au compte et à l'espace**, ignoré au-delà de **7 jours** ou s'il est daté
  dans le futur, **supprimé à la déconnexion volontaire** (conservé à l'expiration de session, comme le profil
  terrain).
- **Mode hors ligne restreint** : si un kit valide existe pour le compte, « Réaliser une inspection » s'ajoute à la
  déclaration d'incident ; même libellés et mêmes règles que le formulaire en ligne ; engins filtrés par site ;
  l'inspection part dans la file commune et se synchronise après reconnexion.
- Le serveur revérifie tout à la synchronisation : permission, site, **modèle toujours actif** (un modèle désactivé
  entre-temps → refus définitif affiché), engin du site.

Vérifications : Vitest 287/287 (12 nouveaux ; les 3 tests de capacité échouent sans l'implémentation), `tsc` OK ;
E2E (Chromium + émulation Android) : préparation en ligne, rechargement sans réseau, inspection en mode restreint,
reconnexion, synchronisation unique — exécuté en CI uniquement.

Limites : le mode hors ligne restreint ne s'ouvre que pour un compte qui a aussi un profil terrain (droit de
déclarer un incident sur au moins un site) ; un compte qui ne peut qu'inspecter n'en bénéficie pas encore.
Photos en ligne uniquement. Appareil Android réel non essayé (`docs/qa/PROTOCOLE_ESSAI_ANDROID_REEL.md`).
