# Protocole d'essai Android physique — usage terrain et réseau dégradé

- **Objet** : protocole d'exécution des essais sur **appareils Android physiques** pour produire la preuve
  « Android physique / connectivité faible » exigée par `docs/qa/GO_NO_GO.md` (condition n° 6) et le
  protocole de pilote (`docs/ops/PROTOCOLE_PILOTE.md`, prérequis 6). L'émulation Playwright (Pixel 7 émulé,
  offline HSE éprouvé en build de production) reste une preuve logicielle : elle ne vaut pas validation
  terrain.
- **Périmètre honnête** : l'application est une PWA navigateur. Aucun suivi GPS persistant en arrière-plan
  n'est promis tant que non validé (`docs/GPS_PHONE_VOLATILE_OFFLINE.md` le documente) ; le protocole
  mesure ce qui existe et consigne les limites constatées.

## 0. Matrice d'appareils (minimum requis pour lever la condition)

| # | Appareil | Android | Navigateur | Réseau de test | Rôle |
|---|---|---|---|---|---|
| A1 | appareil bas de gamme récent (≥ Android 12, RAM ≤ 4 Go) | 【…】 | Chrome stable | réseau mobile réel (opérateur du site) | profil « terrain » |
| A2 | appareil milieu de gamme | 【…】 | Chrome stable | Wi-Fi puis bascule mobile | profil « encadrement » |

Un appareil de plus (tablette, ancien Android 10) est bienvenu ; chaque ligne ajoutée doit être exécutée
pour prétendre à un résultat sur cette classe d'appareil.

## 1. Scénarios obligatoires (par appareil, données fictives, société de démonstration)

Chaque scénario est exécuté sur les parcours **offline-first livrés** (déclaration HSE, notes d'OT) et sur
les consultations classiques. Résultat consigné : réussi / partiel / échec + capture ou enregistrement.

| # | Scénario | Procédure | Critère de réussite |
|---|---|---|---|
| A1 | Réseau 4G stable | parcours nominal complet (connexion, inspection HSE, OT) | aucune erreur, saisies enregistrées |
| A2 | Réseau faible | activon throtting côté opérateur ou zone à faible couverture ; temps de chargement consignés | UI utilisable, états de chargement explicites, pas d'erreur inexpliquée |
| A3 | Coupure complète | mode avion pendant la saisie d'une inspection HSE | l'application reste utilisable, la saisie locale est conservée (IndexedDB/outbox) |
| A4 | Reprise de synchronisation | sortie du mode avion | synchronisation automatique, aucune double écriture (idempotence), états cohérents |
| A5 | Fermeture du navigateur | fermer Chrome pendant qu'une écriture est en attente dans l'outbox, rouvrir | le brouillon local est retrouvé ; aucune donnée perdue ni dupliquée |
| A6 | Batterie faible | < 15 % (ou mode économie d'énergie actif) | l'application reste fonctionnelle en usage actif ; comportement constaté consigné |
| A7 | Changement de compte | déconnexion, connexion d'un autre utilisateur (autre rôle) | aucune donnée du compte précédent accessible ; purge locale sécurisée |
| A8 | Changement de société | connexion d'un compte d'une autre société (fictive B) | aucune donnée de la société A visible (UI **et** API : 404 neutre) |
| A9 | Indicateur d'état de connexion | couper/rétablir le réseau et observer la bannière d'état | l'état affiché correspond au réel, sans blocage persistant |
| A10 | Habilitations hors ligne | parcourir uniquement des données déjà synchronisées | aucune donnée non autorisée rendue accessible hors ligne |

## 2. Points de mesure à consigner

- Temps de chargement à froid / à chaud par écran principal (mesure chronométrée, 3 essais).
- Taille des données locales (IndexedDB) après une journée de saisies — pas de croissance anormale.
- Comportement du partage GPS téléphone (« Mon suivi ») : actif **uniquement** application ouverte
  (volatilité assumée) — le constater et le documenter, ne pas promettre mieux.
- Consommation batterie approximative pour 1 h d'usage actif.
- Version d'Android, version de Chrome, espace disponible — à chaque campagne.

## 3. Résultats et limites (modèle de rapport)

| Champ | A1 | A2 |
|---|---|---|
| Appareil / Android / Chrome | … | … |
| Scénarios réussis (A1–A10) | … | … |
| Échecs / partiels et analyse | … | … |
| Données locales après campagne | … | … |
| Limites constatées (GPS arrière-plan, notifications, etc.) | … | … |
| Décision : classe d'appareil validée pour le pilote | … | … |

**Règles de restitution** : les captures contiennent des données fictives uniquement ; aucun identifiant
d'appareil réel (IMEI, GAID) n'est consigné ; le rapport est référencé dans
`docs/audit/COMMERCIAL_READINESS_CURRENT.md` (§ inconnues n° 4) lorsque complet. Un scénario échoué
bloque la levée de la condition jusqu'à correction testée (PR + re-campagne sur l'appareil concerné).
