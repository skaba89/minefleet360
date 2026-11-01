# Documents des contrats — sécurité et limites

La migration 0049 ajoute uniquement un registre de **métadonnées en attente**.
Elle ne transfère aucun fichier et ne certifie aucune empreinte SHA-256.

## Chemin de mise en œuvre prévu

1. API d'upload avec permission dédiée, isolation tenant/site et limitation de taille.
2. Stockage objet privé, nom de clé opaque non choisi par le navigateur, chiffrement et contrôle d'accès.
3. Lecture du fichier stocké par le serveur, calcul SHA-256 côté serveur et contrôle de concordance.
4. Analyse antivirus et validation du type réel (PDF), puis statut de document vérifié dans une migration dédiée.
5. Association explicite du document vérifié au contrat avant autorisation de soumission.
6. Audit des dépôts, téléchargements et vérifications ; politique de rétention et nettoyage des orphelins.

**Limite actuelle :** la route de soumission des contrats vérifie seulement que `document_sha256` est renseigné. Elle ne prouve pas l'existence du contenu stocké. Ne pas présenter les approbations comme des signatures ou des vérifications de documents.

Le champ `object_key` du registre doit être produit par un service de stockage sécurisé et ne doit jamais contenir de lien public, de token ou de donnée sensible. Les insertions directes par un client ne doivent pas être exposées.
