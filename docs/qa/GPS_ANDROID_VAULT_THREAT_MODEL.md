# GPS durable Android — modèle de menace et recette du coffre (D2-a)

Suite de #489 et #497. Proposition à valider par les responsables sécurité, produit et exploitation avant de créer une file persistante. Aucun code mobile natif, aucune activation du GPS différé ni modification de la PWA dans cette tranche.

## Frontières

- Android natif dédié, version minimale et matrice appareils à sélectionner après inventaire du parc guinéen. Ne pas supposer que l'émulation Playwright Android teste Android Keystore ou les services natifs.
- Coffre privé à l'application ; API HTTPS existante, session d'origine unique ; aucune clé de traceur, aucun jeton dans le coffre. Le contrôle final appartient au serveur ; les métadonnées client ne sont pas des preuves d'autorisation.
- PWA inchangée : tampon volatile. Aucun pont JavaScript donnant accès au coffre natif.
- Menaces couvertes : copie des fichiers, altération/corruption, restauration de sauvegarde, appareil partagé, perte/vol verrouillé, rejeu réseau et changement d'identité. Un appareil compromis (root, instrumentation, malware privilégié) ou déverrouillé sous contrôle de l'attaquant n'offre pas une garantie absolue ; suspendre le pilote si ce risque est inacceptable.

## Conception proposée (à vérifier sur appareils)

| Composant | Exigence |
|---|---|
| Clé | AES-256/GCM dans Android Keystore, clé distincte par partage, non exportable ; alias opaque ; vérifier niveau de sécurité et comportement selon appareils. Aucun fallback en clair. |
| Enregistrement | Nonce aléatoire généré par le fournisseur cryptographique à chaque chiffrement ; jamais réutilisé avec la même clé. Tag 128 bits. AAD non ambigu, versionné, lié au tenant, compte, session, site, véhicule, partage et UUID ; comparer au contexte actif, ne pas accepter l'identité lue du fichier seule. |
| Format | Version, identifiant opaque, nonce, ciphertext/tag ; coordonnées et horodatages dans le texte chiffré. Rejeter les versions inconnues et les champs altérés. Minimiser les index et métadonnées. |
| Persistance | Fichier/DB privée hors sauvegardes et transfert d'appareil ; transaction atomique, jamais de données en clair dans journal/WAL/fichiers temporaires. Ne pas considérer le chiffrement du disque seul comme suffisant. |
| Limites | Maximum 4320 points/partage et 12 h selon contrat candidat ; plafond octets mesuré puis fixé avant pilote, refuser les nouvelles captures dès saturation et afficher le compteur. |
| Purge | Arrêter acquisition/worker, invalider le contexte, détruire la clé puis supprimer ciphertext ; journal de purge minimal sans coordonnées. Bloquer toute reprise si une étape échoue. Au démarrage réconcilier orphelins clé/fichier avant toute ouverture ; aucune récupération de clé supprimée. |

Clé indisponible ou invalidée, erreur d'intégrité, manque d'espace ou panne de transaction : aucune écriture en clair ; suspendre, signaler une perte potentielle et ne pas confondre capture avec écriture confirmée. Ne jamais logger payloads, clés, position, précision ou trajet.

## Cycle de vie et synchronisation

| Transition | Action obligatoire |
|---|---|
| Démarrage en ligne consenti | Créer le partage serveur, vérifier permission et session, initialiser contexte et clé ; sinon aucune acquisition durable. |
| Coupure | Captures uniquement dans le partage valide, horloge monotone et échéance serveur ; aucune prolongation locale. |
| Reconnexion | Vérifier même session/partage/identité et autorisation avant déchiffrement pour envoi ; utiliser uniquement le canal différé pour les points affectés à ce canal. |
| Réponse 200 complète | Supprimer atomiquement les accepted/duplicate ; rejected/conflict comptés et purgés selon politique validée. Réponse absente ou incohérente : aucun retrait confirmé. |
| Réseau/429/5xx | Backoff borné, jamais en boucle ; respecter Retry-After dans les limites de validité du partage. |
| 401/403/404/409 ou contexte divergent | Suspendre, aucune réauthentification automatique pour transférer la file ; vérifier contexte et appliquer purge lorsqu'interdit. |
| Stop local, révocation reçue, déconnexion, compte/site/véhicule changé, expiration | Annuler acquisition et envois futurs, purger clé/file, rendre compte des abandons sans coordonnées. Une demande déjà arrivée au serveur reste soumise à ses contrôles transactionnels. |
| Processus tué/reboot | Aucune reprise autonome : vérifier serveur et même session avant replay. Si hors réseau, ne pas réactiver capture ; en cas de doute sur échéance, arrêt sûr. |

Service de localisation visible seulement après consentement ; notification système sans coordonnées. Tester restrictions OS, permission révoquée, batterie, écran verrouillé, suspension et interruption. Aucun contournement des permissions Android.

## Barrière de recette D2

| ID | Essai | Résultat attendu |
|---|---|---|
| A01 | Inspection fichiers/DB/WAL/backup/transfert | aucun point en clair ni coffre restaurable sur autre appareil |
| A02 | Altération ciphertext, tag, nonce, AAD, version | rejet fermé ; aucun envoi ni lecture partielle |
| A03 | Substitution de contexte utilisateur/session/partage | refus sans fuite ; aucun replay sous autre identité |
| A04 | Crash entre écriture et commit, plein disque | transaction entière ou absente ; pas de perte silencieuse |
| A05 | Crash pendant purge, clé absente ou invalidée | aucune réouverture ; reprise de purge au démarrage |
| A06 | Stop hors ligne, changement heure, reboot, 12 h | capture arrêtée ; aucune reprise illégitime |
| A07 | 5 min offline, perte ACK, rejeu concurrent | une position par UUID ; aucun retrait sans ACK valide |
| A08 | 64/128/256 kbps, 429/5xx, coupures 24/72 h | consommation mesurée ; arrêt à échéance ; aucun historique présenté comme live |
| A09 | Deux appareils physiques (entrée de gamme et récent), verrouillage et charge | preuves de sécurité Keystore, consommation batterie / octets, comportement OS documenté |
| A10 | Régression PWA, GPS live et traceur | API/permissions inchangées ; aucune persistance GPS PWA |

Tous les jeux sont synthétiques. Conserver les résultats par modèle d'appareil, version OS, build et commit ; expurger toute coordonnée des preuves. Les preuves terrain et la revue sécurité sont distinctes des tests unitaires.

## Décisions encore ouvertes

1. Inventaire Android (versions, mémoire, espace, niveau de sécurité Keystore), appareils pilotes et contraintes MDM ; ne pas choisir de dépendances natives avant inventaire.
2. Revue du modèle de menace, politique de rétention et purge des rejets, légalité de la surveillance et information des conducteurs par client.
3. Choix du plafond octets après mesures, budget batterie/réseau, stratégie de compatibilité et tests instrumentation.
4. Validation explicite avant D2-b : squelette Android sans permissions GPS ni collecte, tests cryptographiques instrumentés avec données fictives ; D2-c seulement après preuves : coffre et purge, puis D3 intégration synchronisation.

Feature flag serveur reste désactivé. Ce document ne démontre ni la sécurité cryptographique effective, ni la compatibilité Android, ni l'état de préparation production. Aucun score de maturité augmenté.
