# GPS Android — dossier de qualification physique D2/D3

Statut : préparation, non exécuté. Complément à [GPS_ANDROID_VAULT_THREAT_MODEL.md](GPS_ANDROID_VAULT_THREAT_MODEL.md).
Les références TypeScript #497, #501 à #505 et les vecteurs #499–#500 sont des preuves de logique ou d'interopérabilité, pas de fonctionnement sur Android. #506 (reprise) reste à vérifier sur main.

## 1. Inventaire préalable (à renseigner par le responsable du parc)

| Donnée | Appareil P1 (entrée de gamme) | Appareil P2 (récent) |
|---|---|---|
| Modèle / version Android / patch sécurité | À renseigner | À renseigner |
| RAM / espace libre | À renseigner | À renseigner |
| Niveau de sécurité Keystore observé / état verrouillage | À mesurer | À mesurer |
| Restrictions batterie / MDM | À renseigner | À renseigner |
| Réseau disponible / opérateur de test | À renseigner | À renseigner |

Pas d'IMEI, de numéro personnel, de compte réel, d'adresse ou de trajet réel dans les preuves. L'inventaire ne vaut pas autorisation de collecte. Choix SDK, dépendances et versions minimales après validation de cet inventaire.

## 2. Barrières indépendantes

- D2-b : validation écrite du modèle de menace, inventaire et choix techniques ; squelette sans permission de localisation ni service de collecte, essais cryptographiques synthétiques.
- D2-c : coffre, transactions, exclusion de sauvegarde, purge et récupération ; preuve instrumentée sur P1/P2, sans données réelles.
- D3 : intégration conditionnelle après validation D2 ; API de recette isolée, comptes/sites/véhicules fictifs, aucune activation en production.
- Pilote terrain : décision distincte après revue sécurité, légalité, consentement/information, budget mesuré et validation exploitation. Aucun GO implicite.

## 3. Scénarios de qualification

| ID | Préparation et injection | Critère de réussite | Preuve attendue |
|---|---|---|---|
| Q01 / A01-A02 | Vecteurs publics, inspection fichiers/DB/WAL, altérer nonce/AAD/tag/version ; tester sauvegarde/transfert | Aucun clair, refus fermé, aucune restauration utilisable | Rapport expurgé et résultat instrumentation |
| Q02 / A03 | Changer tenant, compte, session, site, véhicule ou partage, un champ à la fois | Aucun déchiffrement ni envoi sous contexte divergent | Compteurs, statuts, tests |
| Q03 / A04 | Injecter arrêt processus avant/pendant/après commit et saturation espace | Commit entier ou absent, pas de capture annoncée à tort | Comptage avant/après |
| Q04 / A05 | Couper à chaque frontière de purge ; simuler clé inconnue ou invalidée | Aucun retour à l'état ouvert ; clé détruite avant ciphertext ; absence vérifiée | Séquence d'états sans alias ni payload |
| Q05 / A06 | Stop hors ligne, heure modifiée, reboot, expiration 12 h | Pas de capture autonome ; aucun rejeu sans preuve fraîche | Décisions horodatées sans positions |
| Q06 / A07 | Perdre ACK après commit serveur, rejouer même UUID, ACK partielle/tardive, deux tentatives concurrentes | Aucun doublon ; aucun retrait sans ACK complète et tentative valide | Comptages serveur/client synthétiques |
| Q07 / A08 | Réseau plafonné à 64/128/256 kbps, coupures 5 min et 24/72 h, 429/5xx | Reprise bornée ; échéance respectée ; pas d'historique présenté comme live | Octets, délais, nombre de tentatives |
| Q08 / A09 | P1/P2, écran verrouillé, charge, économie batterie, permission révoquée | Arrêt sûr, restrictions respectées, mesures reproductibles | Énergie, durée, version OS, état final |
| Q09 / A10 | Parcours PWA existants, GPS live et traceurs en recette | Aucun changement de droits, stockage ou comportement | Résultats CI + recette séparée |
| Q10 / A04-A08 | 4319/4320 points, budget octets mesuré, espace insuffisant | Refus au-delà des limites ; aucune éviction silencieuse | Compteurs et occupation réelle |

## 4. Fiche de preuve par essai

- ID, résultat PASS / FAIL / BLOCKED / NOT RUN, date UTC, commit, build, environnement isolé, appareil P1/P2, OS.
- Préconditions, injection, résultat attendu/observé, compteurs, durée, octets et anomalie éventuelle.
- Responsable exécutant et responsable de validation ; référence interne vers preuve expurgée.
- Toute preuve absente = NOT RUN ; jamais PASS par extrapolation d'un test JVM ou Playwright.

## 5. Critères de sortie

Tous les essais applicables à la phase doivent être PASS sur les deux appareils, sans régression ni anomalie bloquante. Les budgets octets, batterie et réseau sont à fixer à partir des mesures et à approuver avant pilote. Les rejets/conflits nécessitent une politique de disposition approuvée. Aucun score de maturité supplémentaire sans preuve ni mise à jour du GO/NO-GO.

En cas de FAIL ou BLOCKED : conserver le flag serveur désactivé, suspendre le passage de phase et documenter le correctif ou la décision humaine. Aucun déploiement production.
