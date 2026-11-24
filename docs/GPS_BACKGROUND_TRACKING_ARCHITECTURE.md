# MineFleet360 — GPS en direct et suivi indépendant de la page

## Périmètre livré dans ce lot

La carte du superviseur suit automatiquement **le véhicule sélectionné** lorsque de
nouvelles positions mesurées sont disponibles via le flux GPS existant ou le polling
de secours (15 s). Le superviseur peut suspendre puis reprendre le recentrage.
Aucune estimation de position, aucune altération de l'ingestion GPS et aucun
mouvement fictif ne sont ajoutés.

**Important : le partage GPS web `/mon-suivi` ne fonctionne pas de manière
garantie après fermeture de page ou verrouillage du téléphone.** Ce lot ne
prétend pas résoudre cette restriction du navigateur. Les tests de suivi de
carte n'impliquent aucune acquisition de position en arrière-plan.

## Les deux modes de collecte conservés

1. **Web actuel (à maintenir)** : conducteur consentant, page HTTPS ouverte,
   échantillonnage toutes les ~10 s, tampon mémoire limité hors ligne, arrêt
   à la fermeture/démontage du composant. Le superviseur visualise les
   mesures en direct et peut suivre le véhicule choisi.
2. **Mobile natif (à réaliser)** : application compagnon Android/iOS, collecte
   en arrière-plan seulement avec permissions système et consentement
   explicite, indicateur visible de suivi, arrêt immédiat et suppression
   des positions en file d'attente après révocation.
3. **Traceur embarqué (existant côté API)** : ingestion via identité machine,
   permettant une transmission indépendante du téléphone et du navigateur.

## Contrat cible de l'application compagnon (non implémenté ici)

- Authentifier le conducteur via les mécanismes approuvés, jamais embarquer
  un secret de traceur statique dans l'application.
- Réutiliser la notion existante de partage associé à un véhicule, sa durée
  de validité, les permissions par utilisateur/site, le consentement et le
  mécanisme d'arrêt.
- Demander les permissions au moment de démarrer le partage. Android :
  service de localisation en premier plan avec notification persistante
  et autorisation d'arrière-plan lorsque nécessaire. iOS : permissions et
  mode background location explicites et justifiés ; les arrêts forcés et
  les restrictions du système ne peuvent pas être contournés.
- Stocker de façon chiffrée uniquement des mesures nécessaires à l'envoi
  différé, avec limites de volume, de durée et de précision. Éviter les
  journaux contenant coordonnées, tokens ou identifiants personnels.
- Réconcilier après une coupure réseau via le protocole différé existant
  **seulement lorsqu'il est activé et vérifié côté serveur** ; gérer
  idempotence, points horodatés, ordre chronologique et horloges erronées.
- Distinguer position mesurée, heure de réception, précision et état
  de fraîcheur. Aucune extrapolation de parcours sans données.
- Arrêt utilisateur : révoquer la session et purger la file locale.
  Expiration, retrait d'accès, déconnexion ou changement de véhicule :
  aucune acquisition ultérieure autorisée.
- Déployer d'abord en recette avec essais appareil réel : Android
  et iPhone, écran verrouillé, passage en arrière-plan, perte/reprise
  réseau, batterie, droits retirés, expiration et changement de tenant.

## Conditions avant commercialisation

Audit des permissions et de l'isolement multi-tenant, politique de confidentialité,
rétention, information des salariés/conducteurs, revue de sécurité mobile,
validation des stores, tests de charge et observations terrain. La collecte
en arrière-plan ne peut pas être garantie lorsque l'appareil est éteint,
les permissions retirées ou le système suspend l'application.

**Aucun SDK natif n'est livré dans ce lot, et aucun déploiement VPS n'est réalisé.**
