# État vérifié de MineFleet 360 — 5 novembre 2026

> Référence actualisée : `main@fd1820bb2b74c889bec126c51c6f41dda5bb08fa`, PR #361 fusionnée.
> Trois workflows GitHub Actions associés au HEAD (`ci`, `e2e-isolation`, `security-static`) sont terminés avec succès.
> Cette preuve porte sur les workflows du dépôt. Elle ne prouve pas un déploiement ou une recette terrain.

## État synthétique

- Le socle métier couvre organisations/sites, comptes et rôles, flotte/conducteurs, affectations, dispatch, maintenance, pièces, pneus, carburant, HSE, coûts et registre de contrats, à des niveaux de complétude variables.
- Le GPS inclut maintenant ingestion authentifiée, carte multi-engins, trajet/replay, cap, géofences et alertes, notification, SSE événementiel PostgreSQL, repli/reconnexion. PR #340–#359.
- Le GPS téléphone hors réseau conserve un petit tampon **en RAM**, pas d'historique durable. Le système d'exploitation peut suspendre le navigateur.
- Le workflow HSE offline est présent dans le code et les tests; une validation Android physique et en réseau terrain reste à réaliser.
- Les compatibilités de traceurs physiques Teltonika/Queclink ne sont **pas certifiées** tant qu'un modèle et firmware n'ont pas passé un test matériel.
- Le script de restauration passe maintenant un round-trip CI sur un dump PostgreSQL synthétique isolé; une sauvegarde distante/staging et l'infrastructure client/VPS n'ont pas été vérifiées.
- Abonnements, facturation, onboarding autonome, support sous SLA et contrats de vente ne sont pas prouvés complets.

## Maturité et décision

Score factuel du dépôt : **70/100**, selon la grille et les limites de `docs/audit/INDUSTRIAL_READINESS_2026.md`. L'ancienne estimation 81/100 n'est pas certifiée. La mesure précédente 62/100 précédait plusieurs PR GPS et ne reflétait plus le HEAD.

**NO-GO pour annoncer une industrialisation commerciale ou un déploiement national.** Préparer seulement un pilote fermé après restauration isolée, staging, validation confidentialité, tests matériel/réseau, performance et sécurité. Le détail GO/NO-GO figure dans `docs/qa/GO_NO_GO.md`.

## Sources de vérité

- [Audit de préparation](audit/INDUSTRIAL_READINESS_2026.md)
- [Matrice des écarts](audit/FEATURE_GAP_MATRIX.md)
- [Sécurité et fiabilité](audit/SECURITY_AND_RELIABILITY.md)
- [Feuille de route 85→95](roadmap/ROADMAP_85_TO_95.md)
- [Plan commercial](roadmap/COMMERCIAL_LAUNCH_PLAN.md)
- [Tests d'acceptation industrielle](qa/INDUSTRIAL_ACCEPTANCE_TESTS.md)
- [GO/NO-GO](qa/GO_NO_GO.md)
- [Positionnement concurrentiel](product/COMPETITIVE_POSITIONING.md)
