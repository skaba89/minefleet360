# Livraison HSE-2 — inspections, checklists, non-conformités et preuves photo

Branche `feature/hse-inspections` (empilée sur `feature/tyre-management` pour la chaîne Alembic), migration `0054`.
Complète HSE-1 (`docs/LIVRAISON_HSE1.md`).

## Périmètre

| Élément | Détail |
|---|---|
| Modèles de checklists | code, nom, type (prise de poste, engin, zone de travail), points de contrôle (libellé, critique) ; **versionnés** : réutiliser un code crée la version suivante et archive la précédente ; éléments **immuables** en base (trigger) |
| Inspections | réalisées en une fois, **en ajout seul** ; chaque point reçoit exactement une réponse (conforme, non conforme, sans objet) ; constat obligatoire si non conforme ; libellés figés ; résultat calculé : **non conforme dès qu'un point critique l'est** ; engin du même site pour les inspections d'engin, zone obligatoire pour une zone de travail ; tolérance de 10 min de dérive d'horloge |
| Non-conformités | actions correctives réutilisant la table et le cycle HSE-1 (responsable éligible, échéance, réalisation par le responsable, vérification par un tiers) ; une action a exactement un parent : incident **ou** inspection (`ck_hseca_parent`) |
| Preuves photo | JPEG/PNG reconnus **par signature**, 2 Mo maximum (limite du proxy), 10 par inspection, **antivirus ClamAV obligatoire** (infecté → 422, erreur → 503), stockage privé S3 chiffré, intégrité SHA-256 vérifiée à l'écriture et à la lecture ; sans stockage ou antivirus configuré : **refus explicite 503** (fail-closed) ; lecture uniquement par l'API (`no-store`, `nosniff`) avec droits revérifiés |
| Indicateurs | `GET /hse/summary` ajoute le nombre d'inspections et d'inspections non conformes sur la période |
| Interface | « Inspections et checklists » depuis l'écran HSE : registre, saisie guidée (photo depuis l'appareil photo du téléphone), fiche avec réponses, photos et actions ; page « Modèles de checklists » pour le responsable HSE |

Réutilisation : adaptateurs ClamAV et S3 du module juridique (ajout d'un `content_type` facultatif au port de stockage,
défaut inchangé `application/pdf`), compteur HSE (`INS-000001`), actions et autorisations HSE-1.

## Autorisations

| Permission | Rôles | Routes |
|---|---|---|
| `hse.inspection.read` | DIRECTION (T), OPS_MANAGER, DISPATCHER (S), WORKSHOP_CHIEF, HSE, AUDITOR (T) | registre, fiche, lecture des photos |
| `hse.inspection.perform` | OPS_MANAGER, DISPATCHER (S), WORKSHOP_CHIEF, MECHANIC, FUEL_MANAGER, HSE | modèles en vigueur, réalisation, ajout de photos |
| `hse.checklist.manage` | HSE (T) | création de version, archivage |
| `hse.incident.manage` (existante) | HSE | actions sur non-conformités, responsables éligibles |

Un mécanicien réalise une inspection et y ajoute des photos mais ne relit ni le registre ni les photos.

## Vérifications

- `tests/test_hse_inspections.py` : versions et immuabilité (trigger), inspection conforme / non conforme, actions
  sur non-conformité avec le cycle HSE-1, validations (réponses incomplètes ou inconnues, constat manquant, engin
  d'un autre site, date future, zone), photos (stockage, signature, type, taille, antivirus infecté / en erreur,
  isolation, refus de lecture du mécanicien), fail-closed sans services configurés, isolation inter-tenant, ajout seul.
- Tests d'autorisation générés étendus (objets inspection et preuve, stockage simulé).
- Vitest `HseInspectionsPages.test.tsx` ; Playwright `e2e/hse-inspections.spec.ts` ajouté au workflow `e2e-isolation`.
- Descente de migration rendue exécutable même avec des actions d'inspection (garde destructive conservée).

## Limites et suites

- **Saisie hors ligne des inspections** non incluse (prévue après validation terrain du parcours hors ligne #303).
- Photos d'incident : le modèle les prévoit (`hse_evidence.hse_incident_id`), aucune route n'est encore exposée.
- Pas d'immobilisation automatique d'un engin après une inspection d'engin non conforme (décision métier à prendre).
- Rapports exportables (PDF/CSV) des inspections non livrés.
- Le déploiement des photos exige la configuration du stockage privé et de ClamAV (`docs/legal-clamav-deployment.md`).
