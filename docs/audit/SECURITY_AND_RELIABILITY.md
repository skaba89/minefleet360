# Sécurité et fiabilité — revue basée sur le dépôt

**Référence :** `main@ee0579f544de84b98cd92f74e499467603dae8ee`, observée le 5 novembre 2026.  
**Nature de la revue :** lecture des fichiers et docs versionnés + résultats des workflows GitHub sur ce commit. Pas de pentest, de DAST, d'accès au VPS, ni d'exercice de restauration exécuté pendant cet audit.

## Contrôles observés

| Sujet | Contrôle dans le dépôt | Preuve de validation disponible | Ce qui reste à vérifier |
|---|---|---|---|
| Isolation tenant/site | RBAC applicatif et RLS PostgreSQL visibles dans migrations et tests | workflow `e2e-isolation` du HEAD réussi | revue indépendante, tous chemins/support jobs et staging configuré pareil |
| Authentification / sessions | Identité, MFA et services de session versionnés | tests CI backend; scan SAST réussi | MFA auprès de vrais utilisateurs, récupération, révocation globale, contrôles externes |
| Seuils d'authentification | Limiteur de défaillances basé PostgreSQL observé dans `core/ratelimit.py` | tests backend CI | saturation/latence DB, comportement dégradé pendant panne, quotas par route |
| Secrets et configuration | Variables `MF_*`, Pydantic Settings; rôles DB applicatif et propriétaire séparés | CI construit ses secrets éphémères; aucune valeur réelle n'est intégrée à cette revue | rotation sur hôte, CI secrets et historique de dépôt; déploiement depuis coffre |
| E-mail d'activation/reset | `build_email_sender` refuse la capture en `production`, et exige HTTPS pour SMTP de staging/production | tests et CI dans dépôt, code lu au HEAD | vérifier qu'OVH déploie les variables attendues; tester délivrabilité et purge en recette |
| Fichiers contractuels | modules d'ingestion/antivirus et stockage documents privés présents | tests CI selon workflows | scanner réel, privilèges objet, restauration et autorisations sur environnement cible |
| GPS/confidentialité | sessions de partage consenties, rétention configurée, arrêt à révocation/expiration; messages SSE ne portent pas de coordonnées | PR #357–#359 et tests associés; CI du HEAD | politique de conservation validée par pays, journaux/proxy et captures Android |
| GPS temps réel | SSE authentifié avec relecture RLS et repli; LISTEN/NOTIFY, reconnexion | intégration PostgreSQL testée dans la PR #359; CI du HEAD | panne de base/worker physique, publication multi-machine, perte d'événements et SLO |
| Dépendances / SAST / secrets | audit dépendances + Bandit + Gitleaks dans workflows | `ci` et `security-static` verts au HEAD | DAST, images et supply chain, pinning action SHA, SBOM et politique de remédiation |
| Sauvegardes | archive PostgreSQL, chiffrement/distant optionnels via configuration, script de restauration isolée | une étape CI sauvegarde la base fictive et exécute la restauration isolée; la preuve de workflow reste à consulter à chaque HEAD | configuration distante réelle, clés, transfert, restauration hors CI, RPO/RTO |
| Observabilité | sondes santé/readiness et jobs planifiés documentés | fichiers présents | alertes injectées et acquittées, métriques API/DB/SSE, astreinte et rétention |
| CI/CD | quatre workflows répertoriés; migrations peuplées testées en CI | toutes les exécutions associées au HEAD sont vertes | CD non démontré, rollback/release et protection main à relire dans les settings |

## Risques ouverts et barrières de mise en service

| ID | Gravité opérationnelle | Risque | Action de réduction | Critère de fermeture |
|---|---|---|---|---|
| REL-01 | Bloquant avant pilote réel | Aucune preuve disponible ici de restauration complète d'une sauvegarde chiffrée distante | restaurer un artefact de test sur base isolée, documenter durées et contrôle intégrité | rapport de restauration daté, environnement distinct et aucun accès à la base de production |
| GPS-01 | Bloquant avant pilote télématique | Aucun modèle de traceur/firmware réel certifié | choisir un échantillon matériel avec le partenaire client; essais replay, ordre, auth, panne | procès-verbal par modèle/firmware; aucun label « certifié » avant cette preuve |
| GPS-02 | Bloquant pour SLA GPS | p95/p99 d'ingestion→affichage et taux d'événements perdus inconnus | benchmark autorisé en staging avec véhicules synthétiques | objectifs convenus avec métiers, mesures brutes conservées, seuils atteints |
| OFF-01 | Bloquant avant GPS persistant sur téléphone | Aucun stockage local durable GPS approuvé; le tampon actuel est seulement RAM | concevoir chiffrement, clés, séparation compte/tenant, effacement et expiration; revue sécurité avant code | tests appareil réel: perte, verrouillage, logout, révocation, changement de tenant et restauration |
| OPS-01 | Bloquant avant vente à engagements | RPO/RTO, destination externe et supervision des restaurations non mesurés | documenter SLO provisoires, tester alerte et restore | preuves de tests, responsables et procédures d'escalade |
| SEC-01 | Bloquant avant traitement de données salariés à grande échelle | Avis juridique et notice spécifique GPS/emploi/conservation non confirmés | cartographier finalité, base, minimisation, accès, export et effacement; faire valider par conseil compétent | documents validés dans le pays d'exploitation |
| SEC-02 | Important | Audit statique n'est pas un audit d'intrusion; DAST/pentest absent | audit indépendant sur staging et parcours authz/API | rapport fermé et aucun finding critique/élevé ouvert ou accepté formellement |
| OPS-02 | Important | Outils CLI Docker et restauration dépendent d'images taguées et d'un hôte adéquat | construire/pinner les images et tester cycle déploiement/rollback | signature d'une répétition staging |

## SLI/SLO à décider avant un contrat

Aucun objectif p95/p99 ne peut être fixé unilatéralement à partir de la CI. Le client pilote doit préciser la fréquence d'émission, le nombre d'engins, les sites, l'usage du flux, l'impact métier des retards et la couverture réseau. Mesurer ensuite :

- disponibilité API et erreurs par route;
- temps de réponse p50/p95/p99 par groupe de requêtes;
- temps de la réception d'un paquet GPS à son affichage (horloges synchronisées, identifiant synthétique);
- pourcentage de messages reçus/acceptés/dupliqués/rejetés/hors ordre;
- fraîcheur de la position par véhicule;
- reconnexion SSE et délai de rattrapage REST;
- CPU/RAM, pool SQL, connexions PostgreSQL, WAL et taille/rétention GPS;
- fréquence de succès backup, dernier restore testé, RPO et RTO réellement observés;
- succès et délai de synchronisation offline.

Les seuils restent **TBD avec les utilisateurs métiers**. Ne transformer aucun test de CI en disponibilité contractuelle ou en capacité d'objets suivis.
