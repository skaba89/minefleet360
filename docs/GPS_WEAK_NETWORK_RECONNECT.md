# Carte GPS — reprise après coupure réseau (lot frontend)

Cette PR améliore **la consultation** du suivi GPS SSE sur réseau faible :

- lorsque le navigateur annonce `offline`, la connexion SSE est annulée et les tentatives de reconnexion s'arrêtent ;
- à l'événement `online`, une nouvelle session SSE est tentée avec les droits courants ;
- les erreurs transitoires respectent un délai exponentiel borné de 1, 2, 4, 8, 16 puis 30 secondes ;
- un snapshot SSE valide remet le compteur d'échecs à zéro ;
- en absence de SSE et avec réseau détecté, le polling REST de secours à 15 secondes reste disponible ;
- l'interface distingue l'état **hors connexion** de la diffusion connectée et rappelle que les positions ne sont pas actualisées.

Les données GPS ne sont pas enregistrées sur un stockage local, notamment pas dans `localStorage`, pour éviter des fuites de positions entre utilisateurs ou sociétés. Le cache React Query peut conserver des positions durant la session courante, identifiées par leur horodatage original ; il ne constitue pas une preuve d'emplacement actuel.

Les tests Vitest vérifient la progression et le plafonnement des délais. Les tests serveur de révocation et d'isolation restent inchangés.

## Limites et suite

L'événement `online` indique seulement que le navigateur voit un réseau : il ne prouve pas que l'API est joignable. L'état réel du serveur reste déterminé par les réponses HTTP/SSE.

Cette PR ne met **pas** en file d'attente des positions GPS à envoyer depuis le téléphone. L'ingestion GPS hors ligne demandera une conception distincte : permissions, consentement, quotas de stockage, chiffrement local, ordre des points, timestamps, rejets des doublons et effacement après déconnexion, avec essais sur mobiles réels.
