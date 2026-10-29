# Géolocalisation et interface MINEFLEET 360

## Interface

La référence fournie par l'utilisateur guide le cadre commun : barre latérale bleu nuit,
fond bleu très clair, cartes blanches, boutons bleus, tableaux compacts et badges de statut.
La connexion utilise deux colonnes avec un visuel minier généré pour le projet ; les champs,
liens et messages restent accessibles et fonctionnels. L'interface s'adapte au mobile avec
un menu dépliable et des tableaux défilants. Les rôles continuent à filtrer les accès.

Le tableau de bord affiche des comptages réels par statut et par site, ainsi que les signaux
GPS récents. Aucune valeur du montage de référence n'est utilisée comme donnée métier.
Les données indisponibles sont indiquées par un tiret et une erreur, jamais remplacées par zéro.
La flotte GPS propose une zone cartographique et une liste latérale avec recherche et source.
La vue relative reste interne ; l'ouverture d'OpenStreetMap exige une action explicite et
autorise les mises à jour du véhicule sélectionné jusqu'à fermeture de sa carte.

## Téléphone du compte connecté

1. Un responsable autorisé ouvre « Mon partage GPS », choisit son véhicule et confirme
   être à bord. Le navigateur demande l'autorisation de localisation au premier relevé.
2. Pour un conducteur : l'administrateur relie d'abord le compte actif au dossier conducteur
   depuis sa fiche. Ce compte doit porter le rôle DRIVER sur le site du conducteur. Il ne
   pourra choisir que le véhicule d'une affectation ACTIVE en cours. Un compte ne peut être
   relié à deux dossiers via cette API.
3. Les relevés sont demandés environ toutes les 10 secondes, sans cache de position, et
   envoyés avec leur précision, leur date et une vitesse éventuellement inconnue.
4. « Arrêter le partage » coupe immédiatement les nouvelles demandes et confirme l'arrêt
   au serveur. Quitter la page coupe aussi les relevés et tente d'arrêter le partage serveur.
   En cas d'échec réseau, l'interface signale que l'arrêt reste à confirmer.

HTTPS est nécessaire (localhost est accepté par les navigateurs en développement).
Le navigateur peut suspendre la localisation en arrière-plan ou lorsque l'écran est verrouillé.
Cette version ne promet donc pas un suivi continu en arrière-plan. Un traceur autonome
est nécessaire pour ce besoin ; le mode natif et la synchronisation hors ligne restent à faire.

Le partage est lié à l'utilisateur ET à la session authentifiée, expire après 12 heures au
maximum, et est remplacé quand ce même compte en démarre un autre. Les droits, l'affectation,
le site et l'état du véhicule sont revérifiés à chaque envoi. Aucun relevé n'est pris sans
action de démarrage et consentement explicite. La liste de choix est bornée aux 200 premiers
véhicules autorisés ; étendre la recherche paginée avant un déploiement sur un très grand parc.

## Traceur GPS

Dans la fiche véhicule, « Associer un traceur » crée une liaison véhicule/site et une clé
aléatoire de 256 bits. La clé complète n'est renvoyée qu'une fois ; seule son empreinte est
conservée. « Révoquer l'accès » invalide la liaison et son secret. Révoquer avant de déplacer
un traceur vers un autre véhicule ou de renouveler sa clé.

Le traceur ou une passerelle doit parler le contrat HTTPS JSON ci-dessous. L'association
d'un IMEI ne connecte pas automatiquement un appareil propriétaire. Les protocoles TCP,
SMS et les API des fabricants demandent un adaptateur propre au fournisseur.

```http
POST /api/v1/gps/telemetry
Authorization: Bearer <clé gps_ affichée au provisionnement>
Content-Type: application/json
```

```json
{
  "device_id": "identifiant-configure",
  "sequence": 1,
  "latitude": 9.5,
  "longitude": -13.7,
  "accuracy_m": 10.0,
  "speed_kmh": 20.0,
  "recorded_at": "2026-10-29T12:00:00Z"
}
```

Les coordonnées de cet exemple sont fictives. La séquence doit croître pour chaque message
de la liaison, y compris après redémarrage du traceur. Le tenant, le site et le véhicule sont
résolus côté serveur après vérification de la clé ; ils sont interdits dans le JSON.
Le préfixe gps_ distingue ces clés des jetons de session ou de réinitialisation.
Le tenant du jeton opaque ne sert qu'à sélectionner le contexte RLS avant vérification du
secret : aucune écriture ni donnée métier ne sont autorisées à ce stade.

Réponses : 204 si un nouveau point est stocké ; 401 si la clé, la liaison ou le périmètre
machine sont invalides ; 409 pour un point refusé, ancien ou déjà reçu ; 422 pour un JSON
invalide ; 429 si la limite est atteinte. Un doublon ne reçoit pas d'accusé 204.
Le corps est limité à 16 Kio, sa réception à 10 secondes, et les clés JSON répétées sont
refusées. Le service limite les requêtes par source réseau (1000/minute) et les requêtes
d'un équipement authentifié (60/minute), via les compteurs PostgreSQL partagés existants.
Vérifier ces valeurs et l'IP source de confiance derrière le proxy avant une grande flotte.

## Affichage et sécurité

Le rafraîchissement de supervision se fait toutes les 15 secondes. Le signal est récent si
le relevé ET la réception ont moins de 2 minutes et si la source reste active. Un partage
arrêté ou une clé révoquée ne conserve pas un statut actif. La dernière position reste
historique et datée ; la vitesse d'un signal ancien est masquée. Les positions antérieures
au changement de site ne sont pas exposées dans le nouveau périmètre.

Permissions : fleet.gps.share pour TENANT_ADMIN, OPS_MANAGER, DISPATCHER et DRIVER (ce dernier
limité à sa propre affectation) ; fleet.gps.manage pour TENANT_ADMIN et OPS_MANAGER ;
workforce.driver.link_account pour TENANT_ADMIN seulement. Toutes sont contrôlées côté serveur.
Les opérations démarrage/arrêt, liaison de compte, provisionnement et révocation sont auditées,
sans secret ni coordonnées dans le journal. Les positions restent un historique append-only.

La migration 0026 ajoute les partages téléphone et la provenance aux positions existantes
(source TRACKER par défaut), avec clés étrangères composites tenant, RLS forcée et index
d'unicité du partage actif par utilisateur. Pas de déploiement de production dans cette PR.

Le choix et la configuration du matériel GPS réel, les règles de conservation des positions
et la validation du suivi des salariés pour le pilote restent à définir avec l'exploitant.

## Visuel de connexion

Asset : frontend/public/assets/mining-login.png. Généré avec l'outil imagegen intégré.
Prompt : « Realistic editorial portrait photo of an unbranded yellow mining haul truck at
an open-pit mine in West Africa, front three-quarter view in the lower middle, cloudy
blue-gray sky and space for HTML branding above, muted navy atmosphere, no people, logos,
lettering, UI or watermark. » Les composants de l'interface ne font pas partie de l'image.
