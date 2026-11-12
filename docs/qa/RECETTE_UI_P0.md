# Recette UI P0 — comptes, menus, pages et actions métier (matrice de recette)

- **Objet** : recette exhaustive des comptes, menus et pages par rôle, avec les **actions métier** (créer,
  modifier, clôturer) et non la seule navigation. Complète `docs/qa/ROLE_PAGE_ACTION_MATRIX.md`
  (généré, menus × permissions) en décrivant **ce qui est prouvé par un test Playwright** et les écarts restants.
- **Sources de vérité** : `backend/app/authz/authz_matrix.yaml` (RBAC machine), `frontend/src/App.tsx` (routes),
  `frontend/src/components/Layout.tsx` (menus), les specs Playwright cités en dernière colonne.
- **Anti-dérive** : `python scripts/generate_role_route_matrix.py --check` et `gen_permissions.py --check`
  exécutés en CI frontend (job `frontend`) ; toute évolution de menu ou de matrice doit régénérer le document généré.

## 1. Comptes et périmètres de recette

| Périmètre | Jeu de données | Comptes | Specs |
|---|---|---|---|
| Tenant fictif éphémère (actions métier) | `minefleet seed-fictif` | OPS_MANAGER, DISPATCHER, HR, WORKSHOP_CHIEF, HSE, DIRECTION, FINANCE, AUDITOR + TENANT_ADMIN | `e2e/*.spec.ts` (données créées par API) |
| Trois sociétés DEMO (lecture + parcours) | `minefleet demo seed --profile qa --seed 42` | les 12 rôles tenant/site × 3 sociétés (47 comptes) | `e2e-demo/*.spec.ts` |
| Plateforme | `minefleet create-platform-admin` | PLATFORM_ADMIN (via `MF_PLATFORM_ACCOUNT`, éphémère) | `e2e-demo/direct-url-access.spec.ts` |

Les 14 rôles de la matrice RBAC sont couverts : `PLATFORM_ADMIN`, `TENANT_ADMIN`, `DIRECTION`,
`OPS_MANAGER` (TENANT et SITE), `DISPATCHER`, `HR`, `DRIVER`, `WORKSHOP_CHIEF`, `MECHANIC`,
`STOREKEEPER`, `FUEL_MANAGER`, `HSE`, `FINANCE`, `AUDITOR`.

## 2. Garde-fous transverses (tous rôles)

| Contrôle | Attendu | Preuve |
|---|---|---|
| Connexion / déconnexion | formulaire `/connexion`, déconnexion réelle refusée si non confirmée | `e2e-demo/demo.ts` (login), `AuthContext.tsx` |
| MFA TOTP bout en bout | enrôlement, confirmation, codes de récupération | `e2e/mfa.spec.ts` |
| Accès direct par URL (34 routes protégées × 13 rôles tenant/site) | jamais « Page introuvable. » ni « Erreur inattendue. » ; refus 403 en français ou état explicite | `e2e-demo/direct-url-access.spec.ts` |
| PLATFORM_ADMIN sans droit métier privé | pages plateforme chargent ; aucun menu métier ; `/vehicules` en accès direct → refus propre | `e2e-demo/direct-url-access.spec.ts` |
| Menus filtrés par grants | chaque lien de menu correspond à une permission du rôle ; menus non autorisés absents | `e2e-demo/navigation-roles.spec.ts` + `ROLE_PAGE_ACTION_MATRIX.md` (généré) |
| Responsive 360/768 px | navigation et formulaires utilisables | `e2e/responsive.spec.ts` |
| Hors-ligne terrain (Android + desktop) | déclaration HSE outbox + synchronisation | `e2e-field/hse-offline.spec.ts` |
| Fumée publique sans authentification | `/connexion` rend, aucun appel API authentifié | `e2e-smoke/login.spec.ts` (CI `browser-smoke`) |
| Isolation inter-sociétés | aucune donnée d'une autre société dans les parcours démo | `e2e-demo/parcours-demo.spec.ts` (§ isolation) |

## 3. Matrice des actions métier par domaine

Légende : ✔ = couvert par un spec Playwright cité ; ⏳ = écart ouvert (voir §4).

### Flotte et documents (scénario 1)
| Action (bouton) | Rôle(s) | Route UI | API | Résultat attendu | Preuve |
|---|---|---|---|---|---|
| Créer un véhicule | TENANT_ADMIN | `/vehicules` | `POST /vehicles` | 201, ligne visible | ✔ `e2e/saisie.spec.ts` |
| Immobiliser (statut + If-Match) | OPS_MANAGER | `/vehicules/{id}` | `POST /vehicles/{id}/status` | statut affiché, journal | ✔ `e2e/saisie.spec.ts` |
| Réformer | OPS_MANAGER | `/vehicules/{id}` | `POST /vehicles/{id}/retire` | disparait des listes actives | ✔ `e2e/saisie.spec.ts` |
| Relevé compteur / reset | OPS_MANAGER | `/vehicules/{id}` | `POST /vehicles/{id}/meter-readings\|-resets` | monotone, refus recul | ✔ `e2e/vehicule-documents.spec.ts` |
| Déposer / retirer un document | TENANT_ADMIN | `/vehicules/{id}` | `POST /vehicles/{id}/documents`, `POST /vehicle-documents/{id}/withdraw` | échéances recalculées | ✔ `e2e/vehicule-documents.spec.ts` |
| Voir les échéances documents | FINANCE, DIRECTION, OPS_MANAGER, AUDITOR | `/vehicules/echeances` | `GET /vehicle-documents?within_days` | liste EXPIRING/EXPIRED | ⏳ page rendue (accès direct ✔), cas métier dédié à écrire |

### Conducteurs et affectations (scénario 2)
| Action | Rôle(s) | Route UI | API | Résultat attendu | Preuve |
|---|---|---|---|---|---|
| Créer conducteur, permis, habilitation | HR | `/conducteurs`, `/conducteurs/{id}` | `POST /drivers`, `POST /drivers/{id}/licenses`, `/qualifications` | 201 + listes | ✔ `e2e/fixtures.ts` (API) ; UI : `e2e/saisie.spec.ts` (partiel) |
| Affecter / clôturer une affectation | OPS_MANAGER | `/affectations` | `POST /vehicle-assignments` (+ fin) | éligibilité contrôlée, refus inéligible | ✔ `e2e/affectations.spec.ts` |

### Exploitation et pesées (scénario 3)
| Action | Rôle(s) | Route UI | API | Résultat attendu | Preuve |
|---|---|---|---|---|---|
| Créer lieux / matériau | TENANT_ADMIN | `/administration/lieux-matieres` | `POST /site-locations`, `/materials` | référentiels visibles | ✔ `e2e/missions.spec.ts` |
| Lancer une mission (cycle 5 événements, If-Match) | DISPATCHER, OPS_MANAGER | `/missions`, `/missions/{id}` | `POST /missions[/events]` | rotations suivies, clôture | ✔ `e2e/missions.spec.ts` |
| Saisir une pesée pont / dégradée | DISPATCHER, OPS_MANAGER | `/missions/{id}`, `/pesees` | `POST /weighing-tickets` | net_kg, statut VALID / PENDING_APPROVAL | ✔ `e2e/pesees.spec.ts` |
| Approuver une pesée dégradée (pas par le saisissant) | OPS_MANAGER (2ᵉ) | `/pesees` | `POST /weighing-tickets/{id}/approve` | VALID, décision tracée | ✔ `e2e/pesees.spec.ts` |
| Corriger / annuler une pesée | DISPATCHER, OPS_MANAGER | `/pesees` | `POST /weighing-tickets/{id}/correct\|/void` | ticket corrigé/annulé, motif | ✔ `e2e/pesees-actions.spec.ts` |
| Indicateurs de dispatch | OPS_MANAGER, FINANCE, DIRECTION | `/indicateurs` | `GET /dispatch-indicators` | totaux cohérents avec les pesées | ✔ `e2e/pesees.spec.ts` (fin) |

### Atelier et préventif (scénarios 4-5)
| Action | Rôle(s) | Route UI | API | Résultat attendu | Preuve |
|---|---|---|---|---|---|
| Signaler une panne (immobilisante) | DISPATCHER | `/atelier` | `POST /work-orders` | OT REQUESTED, véhicule IMMOBILIZED | ✔ `e2e/atelier.spec.ts` |
| Approuver / affecter / exécuter / contrôler | WORKSHOP_CHIEF, MECHANIC | `/atelier/{id}` | `POST /work-orders/{id}/decision\|/progress\|/labour` | QC jamais par l'exécutant, remise en service | ✔ `e2e/atelier.spec.ts` |
| Évaluer / planifier le préventif | OPS_MANAGER, WORKSHOP_CHIEF | `/maintenance` | `POST /preventive-dues/evaluate`, `/{id}/schedule` | échéances calculées au compteur | ✔ recette backend R5 ; E2E ⏳ |
| Fiabilité par période | FINANCE, OPS_MANAGER, HSE, AUDITOR | `/atelier/fiabilite` | `GET /maintenance/reliability` | downtime/MTBF cohérents | ✔ recette backend R4/R10 ; E2E ⏳ |

### Carburant (scénario 6)
| Action | Rôle(s) | Route UI | API | Résultat attendu | Preuve |
|---|---|---|---|---|---|
| Fournisseur, commande, réception, cuve, seuil | FUEL_MANAGER, OPS_MANAGER | `/carburant` | `POST /fuel/suppliers\|/purchases\|/tanks[...]` | 201 et soldes cohérents | ✔ `e2e/carburant.spec.ts` |
| Double validation (commande / sortie) | 2ᵉ décisionnaire ≠ saisissant | `/carburant` | `POST /fuel/purchases/{id}/decision`, `/fuel/issues/{id}/decision` | 403/409 si même personne | ✔ `e2e/carburant.spec.ts` |
| Pompe, relevés, anomalies (workflow complet) | FUEL_MANAGER, HSE | `/carburant` | `POST /fuel/pumps[...]`, `/fuel/anomaly-cases[...]` | écart qualifié, acquitté, clôturé | ✔ `e2e/fuel-anomalies.spec.ts` |
| Dashboard carburant | rôles fuel | `/carburant` | `GET /fuel/dashboard` | mesuré/estimé/en attente | ✔ `e2e/carburant.spec.ts` |

### Pièces, pneus (scénario 7)
| Action | Rôle(s) | Route UI | API | Résultat attendu | Preuve |
|---|---|---|---|---|---|
| Réception valorisée, réservation, consommation | STOREKEEPER, WORKSHOP_CHIEF | `/pieces` | `POST /part-movements/valued-receipts`, `/part-reservations[/consume]` | CMP et soldes exacts | ✔ API (R4/R10 backend) ; E2E ⏳ |
| Réapprovisionnement (soumission + décision) | STOREKEEPER, OPS_MANAGER | `/pieces` | `POST /part-replenishments[/submit\|/decision]` | cycle complet, jamais auto-décidé | ✔ `e2e/parts-replenishment.spec.ts` (bug GRANT 500 corrigé par 0064) |
| Cycle pneu (montage, usure, démontage, rebut, export) | WORKSHOP_CHIEF, MECHANIC | `/pneus` | `POST /tyres[/{id}/mount\|…]`, `/tyres/stock` | km consommés, alertes, CSV | ✔ `e2e/pneus.spec.ts` |
| Commandes de pièces (`/parts-purchase-orders`) | STOREKEEPER, OPS_MANAGER | `/pieces` (onglet « Commandes d'achat ») | `GET\|POST /parts-purchase-orders` | brouillon créé depuis une demande APPROVED, quantité reprise de la demande | ✔ `src/pages/PartsPage.test.tsx` (vitest) ; E2E ⏳ |

### HSE (scénario 8)
| Action | Rôle(s) | Route UI | API | Résultat attendu | Preuve |
|---|---|---|---|---|---|
| Déclarer un incident (+ hors-ligne) | DRIVER, DISPATCHER, HSE | `/hse` | `POST /hse/incidents` | idempotent, preuves uploadées | ✔ `e2e-field/hse-offline.spec.ts` |
| Inspection avec NC → OT depuis non-conformité | HSE, WORKSHOP_CHIEF | `/hse/inspections` | `POST /hse/inspections`, `POST /work-orders` | NC tracée, OT créé | ✔ `e2e/hse-inspections.spec.ts` |
| Décision d'action corrective + complétion | HSE, OPS_MANAGER | `/hse`, `/hse/{id}` | `POST /hse/corrective-actions/{id}/decision\|/complete` | workflow strict | ✔ `e2e/hse-corrective-actions.spec.ts` |
| Modèles de checklist | HSE | `/hse/checklists` | `POST\|POST /hse/checklist-templates[/deactivate]` | modèles gérés | ✔ API ; E2E ⏳ |

### GPS (scénario 9)
| Action | Rôle(s) | Route UI | API | Résultat attendu | Preuve |
|---|---|---|---|---|---|
| Carte live (SSE) et historique de trajet | OPS_MANAGER, DISPATCHER | `/flotte-gps` | `GET /vehicles/gps/latest\|/stream`, `/vehicles/{id}/gps/track` | données mesurées, jamais un tonnage | ✔ `e2e-demo/parcours-demo.spec.ts` |
| Zones (géofences) | OPS_MANAGER, HSE | `/flotte-gps/zones` | `POST /geofences`, `POST /geofences/{id}/deactivate` | création puis désactivation | ✔ `e2e/gps-zones-policy.spec.ts` (création OPS_MANAGER, lecture DISPATCHER sans bouton, refus API 403, désactivation conservée via `include_inactive`) |
| Alertes GPS : acquittement | OPS_MANAGER, DISPATCHER, HSE | `/flotte-gps/alertes` | `POST /gps/alerts/{id}/acknowledge` | re-prise en compte refusée (409) | ✔ `e2e/gps-alerts.spec.ts` |
| Politique site + notifications | OPS_MANAGER, TENANT_ADMIN | `/flotte-gps/alertes` | `PUT /sites/{id}/gps-policy`, `/me/alert-notifications` | seuils bornés (422 sinon) | ✔ `e2e/gps-zones-policy.spec.ts` (réglages OPS_MANAGER persistés, contrôle croisé API, politique visible mais non modifiable pour DISPATCHER, préférences e-mail) |
| Partage téléphone | DRIVER, OPS_MANAGER | `/mon-suivi` | `POST /me/gps/shares[/positions\|/stop]` | consentement explicite, arrêt | ✔ recette backend R7 ; E2E ⏳ |

### Juridique (scénario R9) et coûts (scénario R10)
| Action | Rôle(s) | Route UI | API | Résultat attendu | Preuve |
|---|---|---|---|---|---|
| Contrat brouillon → décision (quatre-yeux) | TENANT_ADMIN (créer), DIRECTION (décider) | `/juridique` | `POST /legal-contracts`, `/{id}/decision` | incomplet non soumis, décision tracée | ✔ `e2e/legal-contracts.spec.ts` (brouillon + refus de soumission sans preuve) ; cycle documentaire complet ✔ `e2e/legal-document-cycle.spec.ts` (harnais S3/ClamAV : dépôt, scan EICAR refusé, vérification DIRECTION, soumission, décision UI, réconciliation nominale UI) |
| Police d'assurance | FINANCE | `/juridique` | `POST /insurance-policies` | GNF, dates cohérentes | ✔ `e2e/insurance-policies.spec.ts` |
| Échéances d'assurance (nouvel endpoint) | FINANCE, DIRECTION, OPS_MANAGER, HSE, AUDITOR | `/juridique` (onglet assurances) | `GET /insurance-policies/expiring` | polices EXPIRING/EXPIRED avec état traduit | ✔ `src/pages/LegalRegistriesPage.test.tsx` (vitest) ; ✔ `e2e/insurance-policies.spec.ts` |
| Réconciliation du stockage légal | DIRECTION, TENANT_ADMIN | `/juridique` | `GET /legal-contracts/storage-reconciliation` | cohérent / orphelin détecté | ✔ chemin dégradé : `e2e/costs-reconciliation.spec.ts` (503 SERVICE_BUSY annoncé sans stockage privé, panneau réservé à la revue tenant, 403 pour l'AUDITOR) ; ✔ chemin nominal : `e2e/legal-document-cycle.spec.ts` (harnais S3/ClamAV, cohérence annoncée depuis l'UI) |
| Coût complet par engin + taux horaires | FINANCE, OPS_MANAGER, DIRECTION, AUDITOR | `/couts` | `GET /costs/vehicles[/{id}/history]`, `POST /costs/labour-rates` | GNF, totaux = somme des lignes | ✔ `e2e-demo/parcours-demo.spec.ts` (lecture) ; taux horaires ✔ `e2e/costs-reconciliation.spec.ts` (création FINANCE, AUDITOR sans section, DISPATCHER refusé) |

### Administration et plateforme (scénario 10)
| Action | Rôle(s) | Route UI | API | Résultat attendu | Preuve |
|---|---|---|---|---|---|
| Créer / suspendre / réactiver une société | PLATFORM_ADMIN | `/plateforme/*` | `POST /platform/tenants[...]` | parcours complet | ✔ `e2e/platform-tenants.spec.ts` |
| Créer site, inviter utilisateur, rôles, audit | TENANT_ADMIN | `/administration/*` | `POST /sites`, `/users`, `/role-assignments` ; `GET /audit-events` | parcours complet, 403 pour les autres | ✔ `e2e/administration.spec.ts` |
| Santé plateforme | PLATFORM_ADMIN | `/plateforme/etat` | `GET /health`, `/ready` | statuts visibles | ⏳ non couvert E2E |

## 4. Écarts ouverts (prochaines PR)

*Aucun écart ouvert.* L'écart n°1 (UI du cycle documentaire juridique) est **résolu** : le dépôt de
justificatif (empreinte SHA-256 calculée au client, contrôle de concordance avec l'empreinte attendue,
envoi des octets bruts avec `X-Filename`), les états PENDING/VERIFIED traduits (nouvelle route
`GET /legal-contracts/{contract_id}/documents`, matrice `legal.contract.read`), la vérification
quatre-yeux (`legal.contract.review`) et la soumission (`legal.contract.submit`, exige un justificatif
vérifié) sont exposés dans `/juridique` — panneau « Documents » par contrat
(`ContractDocumentsPanel.tsx`, tests Vitest inclus). Le parcours complet est prouvé depuis le navigateur
par `e2e/legal-document-cycle.spec.ts` (test « cycle documentaire depuis l'UI ») sur le harnais
S3/ClamAV : empreinte à la création, dépôt, vérification DIRECTION, soumission.

*Résolu : l'écart d'UI pour `GET /insurance-policies/expiring` et `GET|POST /parts-purchase-orders` est couvert
(onglet assurances de `/juridique` et onglet « Commandes d'achat » de `/pieces`, tests vitest inclus).
Les 6 specs E2E d'actions (`pesees-actions`, `parts-replenishment`, `gps-alerts`, `hse-corrective-actions`,
`legal-contracts`, `platform-tenants`) sont exécutées par le job CI `e2e-isolation` ; elles ont révélé et
fait corriger l'absence de GRANT UPDATE sur `spare_part_replenishment` (migration 0064, régression testée).
La police d'assurance est couverte par `e2e/insurance-policies.spec.ts` : création FINANCE depuis
`/juridique`, états EXPIRING/EXPIRED traduits, borne d'horizon 45 jours, auditeur en lecture seule.
Les zones de site (géofences), la politique d'alerte du site et les préférences de notification sont
couvertes par `e2e/gps-zones-policy.spec.ts` : création puis désactivation d'une zone par l'OPS_MANAGER,
lecture DISPATCHER sans bouton de gestion (refus 403 en API), politique du site persistée et relu par
l'API, préférences personnelles de notification enregistrées. Les actions de coûts (taux horaires) et la
réconciliation du stockage documentaire sont couvertes par `e2e/costs-reconciliation.spec.ts` : création
d'un taux par la FINANCE avec contrôle croisé API, AUDITOR sans section de gestion, DISPATCHER refusé
(403 serveur) ; réconciliation prouvée sur son chemin dégradé (503 SERVICE_BUSY annoncé en français
sans stockage privé, panneau limité à la revue tenant). Le chemin nominal est couvert par
`e2e/legal-document-cycle.spec.ts` avec le harnais S3/ClamAV (voir §5) : cohérence annoncée depuis l'UI
après un cycle complet (dépôt, scan, vérification, soumission, décision).

**Écart n°2 (formes de refus) — résolu** : les refus d'accès direct par pré-contrôle utilisent désormais
une forme canonique unique (`<AccessDenied />` de `components/common.tsx` — « Vous n'avez pas accès à cette
page. », `div.error` + `role="alert"`), appliquée aux 17 points de refus de 10 fichiers de pages qui
pré-contrôlaient avec des variantes hétérogènes (administration ×4, plateforme ×4, juridique ×2,
référentiels, pièces, préventif, fiabilité, alertes GPS, flotte GPS, carburant). Convention documentée :
une page que le rôle ne couvre pas → « …cette page » (`AccessDenied`) ; une donnée d'une page par ailleurs
autorisée → « …cette information » (`ErrorMessage` sur 403 serveur, défense en profondeur). Le socle E2E
d'accès direct continue de garantir qu'aucun accès direct ne montre « Page introuvable. » ni « Erreur inattendue. ».*

## 5. Exécution

```bash
# Backend + données (comme .github/workflows/e2e-isolation.yml)
alembic upgrade head
minefleet create-platform-admin --email platform-admin@example.com --name "Administrateur fictif"
minefleet seed-fictif > /tmp/e2e-accounts.txt
minefleet demo seed --profile qa --seed 42 --credentials-out /tmp/demo-accounts.tsv
uvicorn app.main:app --host 127.0.0.1 --port 8000

# Cycle documentaire juridique : harnais S3/ClamAV + API dédiée :8001 (étape
# « Start legal documentary harness » du workflow e2e-isolation ; l'API :8000 reste sans
# stockage privé pour préserver le chemin dégradé 503 testé par costs-reconciliation).
openssl req -x509 -newkey rsa:2048 -nodes -days 2 -keyout /tmp/legal-harness/s3.key \
  -out /tmp/legal-harness/s3.crt -subj "/CN=127.0.0.1" \
  -addext "subjectAltName=IP:127.0.0.1,DNS:localhost"
FAKE_S3_DATA_DIR=/tmp/legal-harness/objects python scripts/dev/fake_s3.py \
  --port 9443 --bucket legal-private --cert /tmp/legal-harness/s3.crt --key /tmp/legal-harness/s3.key &
python scripts/dev/fake_clamd.py --port 3310 &
MF_LEGAL_OBJECT_STORAGE_ENABLED=true MF_LEGAL_OBJECT_STORAGE_ENDPOINT=https://127.0.0.1:9443 \
MF_LEGAL_OBJECT_STORAGE_BUCKET=legal-private MF_LEGAL_OBJECT_STORAGE_ACCESS_KEY=<ephemere> \
MF_LEGAL_OBJECT_STORAGE_SECRET_KEY=<ephemere> MF_LEGAL_MALWARE_SCAN_ENABLED=true \
MF_LEGAL_MALWARE_SCAN_HOST=127.0.0.1 MF_LEGAL_MALWARE_SCAN_PORT=3310 \
MF_ALLOWED_ORIGINS=http://localhost:5173 MF_COOKIE_SECURE=false MF_MFA_ENFORCEMENT=off \
AWS_CA_BUNDLE=/tmp/legal-harness/s3.crt uvicorn app.main:app --host 127.0.0.1 --port 8001 &
# puis : MF_API_URL=http://localhost:8001 npx playwright test e2e/legal-document-cycle.spec.ts

# Navigateur
cd frontend && npm ci && npx playwright install --with-deps chromium
MF_API_URL=http://127.0.0.1:8000 MF_DEMO_ACCOUNTS=/tmp/demo-accounts.tsv \
  npx playwright test --config=playwright.demo.config.ts
```
