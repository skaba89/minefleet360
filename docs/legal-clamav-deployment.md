# ClamAV privé — étape de déploiement documentaire

Le profil Docker Compose `documents` ajoute un service `clamav` non publié sur le VPS. Il **ne connecte pas encore** l'API au scanner et ne débloque pas la soumission des contrats.

## Préparation et recette

Depuis `infra/deploy`, après avoir configuré l'environnement de recette et vérifié la mémoire disponible :

```sh
docker compose -f docker-compose.prod.yml --env-file .env.prod --profile documents up -d clamav
docker compose -f docker-compose.prod.yml --env-file .env.prod --profile documents ps clamav
docker compose -f docker-compose.prod.yml --env-file .env.prod --profile documents logs --tail=100 clamav
```

Ne publiez **jamais** le port 3310 sur l'hôte ou Internet. Le protocole clamd TCP n'authentifie pas les clients ; le scanner doit rester sur un réseau privé. Le volume `clamav-signatures` conserve les signatures. Prévoir les mises à jour des signatures, l'espace disque et les ressources mémoire ; vérifier le statut du scanner avant tout upload réel.

## Critères de sortie avant mise en service

- Service sain et signatures actualisées ; contrôle d'un fichier de test inoffensif et du vecteur de test EICAR dans un environnement isolé.
- Paramètres d'hôte/port/timeout injectés côté API depuis une configuration validée, et communications privées prouvées.
- Refus en cas de timeout, signature obsolète ou scanner indisponible.
- Upload authentifié, isolation tenant/site, limite de taille, validation PDF, stockage privé et relecture SHA-256.
- Mise à jour du statut documentaire et audit réalisés de façon cohérente, avec tests de bout en bout.

Ne jamais considérer la présence du conteneur comme une preuve d'analyse antivirus opérationnelle.
