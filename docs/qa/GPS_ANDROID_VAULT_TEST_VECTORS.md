# Vecteurs de recette du coffre GPS Android (D2-a complément)

Suite du modèle de menace #498, sans dépendance Android ou permission. Les vecteurs sont publics, synthétiques et non secrets. Ils ne constituent ni un coffre ni une preuve de sécurité Keystore. Aucun changement de production.

## Encodage AAD proposé V1

Préfixe ASCII `MF-GPS-V1` suivi d'un octet nul, puis sept UUID de 16 octets en ordre réseau (big-endian), sans séparateur :
tenant, compte, session, site, véhicule, partage, point. Longueur totale 122 octets.
Les identités attendues proviennent du contexte actif vérifié, jamais seulement du fichier chiffré. Vérifier les types d'identifiants et l'ordre avec le backend avant intégration ; si le contrat change, versionner l'encodage au lieu de réinterpréter les anciens enregistrements.

Le test de référence `backend/tests_unit/test_android_vault_vectors.py` définit un vecteur AES-256-GCM, nonce de 12 octets, tag de 16 octets, résultat ciphertext suivi du tag. Le futur test natif doit reproduire les octets de ce vecteur dans un harnais de test isolé. **Ne jamais importer la clé de test, réutiliser son nonce ni imposer un nonce à la clé de production.** Le test Keystore doit générer ses propres clés et nonces et vérifier séparément les propriétés du fournisseur et du matériel.

## Vérifications de référence

- Résultat connu indépendant du futur environnement natif.
- Altération de chacune des sept identités et des 21 permutations de deux champs.
- Altération de chaque octet du ciphertext/tag, du nonce et du préfixe de version.
- Mauvaise clé et nombre de champs incorrect.

Exécution locale du vecteur : cinq tests unittest réussis. CI complète et tests instrumentés Android restent distincts. Aucun stockage réel, aucun fichier de coordonnées, aucune collecte, aucun changement de flag GPS.

## Étape suivante

Valider explicitement le passage en D2-b et inventorier le parc Android (versions, niveaux de sécurité Keystore, matériel pilote). Répliquer les vecteurs sur le socle natif sans collecte ; ensuite, mesurer les capacités Keystore sur appareils physiques. Ne pas considérer cette recette JVM/Python comme preuve de sécurité du stockage Android.
