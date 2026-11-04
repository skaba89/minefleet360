# Dette technique — inventaire priorisé

État au 4 novembre 2026, `main@000ee08`.

| Priorité | Élément | Constat | Remède |
|---|---|---|---|
| P1 | Approbations de compteur (`MeterReconciliationApproval`) | toute une chaîne existe (`preventive_reconciliation_*`, `preventive_meter_approval_read`, `preventive_approval_persist`) sans route ni écran de création ; depuis #336/#337, le calcul passe par le jalon validé et les relevés | décider : supprimer la chaîne ou l'exposer comme correction exceptionnelle ; en attendant, ne plus l'étendre |
| P1 | Fragmentation du module préventif | 30 fichiers `preventive_*`, souvent de 40 à 120 lignes, nés de tranches successives | regrouper par responsabilité (plans, jalons, échéances, finalisation) une fois les tranches B2 et C livrées |
| P1 | Rafraîchissement GPS par interrogation | 15 s de latence, coût proportionnel au nombre d'écrans ouverts | push (SSE) avec la carte temps réel |
| P2 | Échéances calendaires en date UTC | sans effet en Guinée (UTC+0), faux pour un site à un autre fuseau | utiliser le fuseau du site |
| P2 | Harnais de test | la fixture de session descend toutes les migrations : lente (~19 min pour la suite complète) | base modèle réutilisée par session, en gardant un job de vérification des migrations |
| P2 | Coût des pneus | tout le prix d'achat est imputé au pneu neuf (décision produit ouverte) | arbitrage produit, puis amortissement au km |
| P2 | Page coût complet | ~65 ms de SQL réparties sur 6 requêtes ; historique des pneus rechargé à chaque appel | valeur à date par pneu si les flottes grossissent |
| P3 | `docs/MATURITY_SCORECARD.md` périmé | grille et notes du 30 octobre | remplacé pour le pilotage par `PRODUCT_READINESS_SCORE.md` |
| P3 | Conteneurs de développement sur le VPS | ~1 Go de mémoire (`minefleet-ci-db`, `mf-audit-*`, `minefleet-api-check-*`) | à arrêter avec l'accord du client |
