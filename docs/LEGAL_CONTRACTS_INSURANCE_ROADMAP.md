# MineFleet360 — Contrats, signature électronique et assurances

## Statut
Fondation de données uniquement (migration 0046). Aucune route API, interface utilisateur, signature électronique, police activée ni alerte automatique n'est encore disponible.

## Modules visés
1. **Contrats** — contrats fournisseurs, transporteurs, sous-traitants, salariés et locations ; modèle, versions de pièces jointes, contreparties, circuit de validation, échéances et avenants.
2. **Signature électronique** — intégration d'un prestataire de confiance à sélectionner ; identité du signataire, consentement explicite, horodatage, preuve vérifiable, empreinte SHA-256 du PDF, journal d'audit append-only ; aucun certificat ni signature juridiquement qualifiée simulés en interne.
3. **Assurances** — registre des assureurs, polices, garanties, primes, échéances, renouvellements et sinistres ; liens tenant/site puis véhicules/engins/conducteurs et documents véhicules existants.
4. **Alertes** — rappels configurables avant expiration, contrôle de cohérence des dates, tableau de bord couverture/risques.
5. **Sécurité** — RBAC par rôle et site, RLS PostgreSQL, documents privés, chiffrement et suivi des accès, aucun secret dans les journaux.

## Ordre d'implémentation
- Lot A (cette PR) : schéma initial des contrats et polices, uniquement brouillons/enregistrements ; isolation RLS et contraintes SQL.
- Lot B : API de création/lecture et permissions dédiées, tests multi-tenant et multi-site, gestion du cycle de vie.
- Lot C : rattachement des polices aux véhicules/engins et fichiers, renouvellement et alertes ; vérification de l'assureur agréé.
- Lot D : workflow de versionnage et signature externe (prestataire vérifié), preuve, audit et contrôle de l'intégrité du PDF.
- Lot E : interface web et scénarios E2E, tests de sécurité, recette juridique puis activation en production.

## Garde-fous réglementaires
Vérifier avec un conseil juridique en Guinée les conditions de preuve et de certification prévues par la loi L/2016/035/AN et le décret du 19 août 2026 avant de présenter une signature comme opposable. Le Code guinéen des assurances L/2016/034/AN régit les opérations locales, notamment la souscription auprès d'assureurs agréés et la règle de devise GNF sous réserve des exceptions autorisées. La migration impose GNF pour le périmètre initial ; une exception légale devra faire l'objet d'une évolution validée.

## Hors périmètre de la migration 0046
- Pas de fausse signature, de PDF « signé » ni de webhook de prestataire.
- Pas de mouvement financier ni de paiement de prime.
- Pas de lien véhicule ou personnel, de sinistre, d'avenant ni de renouvellement automatisé.
- Les nouveaux objets ne remplacent pas encore `vehicle_document`.
- Les migrations et contrôles CI/recette doivent passer avant toute fusion.
