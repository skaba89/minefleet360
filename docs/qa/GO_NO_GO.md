# GO / NO-GO — situation au 6 novembre 2026 (base main 089d801)

## Verdict

**NO-GO commercialisation industrialisée et déploiement large.**  
**GO conditionnel pour préparer un pilote fermé**, sous réserve de respecter les blocages P0 ci-dessous. Aucun pilote terrain, déploiement production, modèle de traceur certifié, avis juridique, restauration d'une sauvegarde opérationnelle/externe ou SLO de charge n'est attesté. La CI prouve uniquement une chaîne synthétique sur infrastructure jetable.

## Preuves positives disponibles

- La base auditée est `main@089d8019dc67524ceb7420d42426e2c4921cc566`, après fusion de la PR #372.
- PR #359 est fusionnée et son code apporte un backoff de reconnexion LISTEN borné; la PR décrit ses tests unitaires et PostgreSQL.
- Sur la base #372 et la PR #373, `ci`, `e2e-isolation` et `security-static` sont terminés en succès. #373 étend `ci` au chiffrement, transport rclone local, checksum, déchiffrement et restore du dump synthétique avant le démarrage sous `mf_app`.
- Les migrations, modules métiers, code GPS, tests, scripts de sauvegarde/restauration, sondes et documentation sont présents dans l'arbre.
- Les fonctionnalités GPS cartographiques/alertes/SSE des PR #340–#359 ne doivent plus être décrites comme absentes.

## Conditions BLOQUANTES avant pilote avec données opérationnelles

| Condition | État prouvé | Preuve à fournir avant décision GO |
|---|---|---|
| Environnement staging isolé et déploiement reproductible | Non validé dans cet audit | capture de version, checklist readiness, test migration/rollback daté |
| Sauvegarde et restore isolé | Round-trip synthétique automatisé avec chiffrement et remote rclone local; fournisseur externe et exercice staging absents | restaurer une sauvegarde staging chiffrée depuis le coffre retenu, vérifier l'API, la récupération de clé et mesurer RPO/RTO |
| Isolation tenant/site dans la configuration de recette | tests CI verts, staging non vérifié | suite croisée A/B avec rôles et tenant DB applicatif |
| Confidentialité GPS/salariés et consentement | contrôles de code documentés, revue juridique absente | notice, finalités, accès, rétention, suppression et validation professionnelle |
| Traceur physique ciblé | non certifié | essai daté du modèle/firmware/protocole exact |
| Android physique / connectivité faible | essai réel non démontré | matrice appareil/OS, arrière-plan, réseau simulé puis terrain |
| SLO GPS et capacité | aucun p95/p99 validé | benchmark staging et seuil métier signé |
| Supervision et réponse d'incident | scripts présents, alertes non éprouvées | injection d'incident, alerte reçue/acquittée, exercice documenté |

## Conditions bloquantes avant vente et promesse de service

- Tarification, quota GPS, rétention, support, contrat, SLA et coût de support établis.
- Onboarding client, import et sortie/export testés.
- Politique de confidentialité et conditions validées pour la juridiction ciblée.
- Aucun constat critique/élevé d'un audit de sécurité indépendant restant sans mesure ou acceptation formelle.
- Parcours commerciaux testés avec clients pilotes, sans données simulées confondues avec données terrain.

## Décision à réévaluer

Le statut pourra évoluer vers **GO pilote** à l'issue des preuves ci-dessus, en consignant qui a approuvé, client/site concernés, durée, limites, données collectées, responsables d'incident, critères d'arrêt et plan de suppression. La vente avec engagement de disponibilité nécessite ensuite des mesures réelles et des termes contractuels validés.

Score dépôt actuel : **70/100**; cette note mesure seulement les capacités et éléments de preuve consultables. Elle n'infléchit pas le verdict NO-GO.
