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
| Corriger / annuler une pesée | DISPATCHER, OPS_MANAGER | `/pesees` | `POST /weighing-tickets/{id}/correct\|/void` | ticket corrigé/annulé, motif | ⏳ non couvert E2E |
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
| Réapprovisionnement (soumission + décision) | STOREKEEPER, OPS_MANAGER | `/pieces` | `POST /part-replenishments[/submit\|/decision]` | cycle complet, jamais auto-décidé | ⏳ non couvert E2E |
| Cycle pneu (montage, usure, démontage, rebut, export) | WORKSHOP_CHIEF, MECHANIC | `/pneus` | `POST /tyres[/{id}/mount\|…]`, `/tyres/stock` | km consommés, alertes, CSV | ✔ `e2e/pneus.spec.ts` |
| Commandes de pièces (`/parts-purchase-orders`) | STOREKEEPER, OPS_MANAGER | — (aucune page) | `GET\|POST /parts-purchase-orders` | ⏳ **aucune UI** — écart ouvert | ❌ |

### HSE (scénario 8)
| Action | Rôle(s) | Route UI | API | Résultat attendu | Preuve |
|---|---|---|---|---|---|
| Déclarer un incident (+ hors-ligne) | DRIVER, DISPATCHER, HSE | `/hse` | `POST /hse/incidents` | idempotent, preuves uploadées | ✔ `e2e-field/hse-offline.spec.ts` |
| Inspection avec NC → OT depuis non-conformité | HSE, WORKSHOP_CHIEF | `/hse/inspections` | `POST /hse/inspections`, `POST /work-orders` | NC tracée, OT créé | ✔ `e2e/hse-inspections.spec.ts` |
| Décision d'action corrective + complétion | HSE, OPS_MANAGER | `/hse`, `/hse/{id}` | `POST /hse/corrective-actions/{id}/decision\|/complete` | workflow strict | ⏳ non couvert E2E |
| Modèles de checklist | HSE | `/hse/checklists` | `POST\|POST /hse/checklist-templates[/deactivate]` | modèles gérés | ✔ API ; E2E ⏳ |

### GPS (scénario 9)
| Action | Rôle(s) | Route UI | API | Résultat attendu | Preuve |
|---|---|---|---|---|---|
| Carte live (SSE) et historique de trajet | OPS_MANAGER, DISPATCHER | `/flotte-gps` | `GET /vehicles/gps/latest\|/stream`, `/vehicles/{id}/gps/track` | données mesurées, jamais un tonnage | ✔ `e2e-demo/parcours-demo.spec.ts` |
| Zones (géofences) | OPS_MANAGER, HSE | `/flotte-gps/zones` | `POST /geofences`, `POST /geofences/{id}/deactivate` | création puis désactivation | ✔ `e2e-demo/parcours-demo.spec.ts` (lecture) ; E2E ⏳ |
| Alertes GPS : acquittement | OPS_MANAGER, DISPATCHER, HSE | `/flotte-gps/alertes` | `POST /gps/alerts/{id}/acknowledge` | re-prise en compte refusée (409) | ⏳ non couvert E2E |
| Politique site + notifications | OPS_MANAGER, TENANT_ADMIN | `/flotte-gps/alertes` | `PUT /sites/{id}/gps-policy`, `/me/alert-notifications` | seuils bornés (422 sinon) | ✔ recette backend R7 ; E2E ⏳ |
| Partage téléphone | DRIVER, OPS_MANAGER | `/mon-suivi` | `POST /me/gps/shares[/positions\|/stop]` | consentement explicite, arrêt | ✔ recette backend R7 ; E2E ⏳ |

### Juridique (scénario R9) et coûts (scénario R10)
| Action | Rôle(s) | Route UI | API | Résultat attendu | Preuve |
|---|---|---|---|---|---|
| Contrat brouillon → décision (quatre-yeux) | TENANT_ADMIN (créer), DIRECTION (décider) | `/juridique` | `POST /legal-contracts`, `/{id}/decision` | incomplet non soumis, décision tracée | ⏳ UI créée ; E2E ⏳ |
| Police d'assurance | FINANCE | `/juridique` | `POST /insurance-policies` | GNF, dates cohérentes | ⏳ non couvert E2E |
| Échéances d'assurance (nouvel endpoint) | FINANCE, DIRECTION, OPS_MANAGER, HSE, AUDITOR | `/juridique` | `GET /insurance-policies/expiring` | polices EXPIRING/EXPIRED | ⏳ **aucune UI** — écart ouvert |
| Réconciliation du stockage légal | DIRECTION, TENANT_ADMIN | `/juridique` | `GET /legal-contracts/storage-reconciliation` | cohérent / orphelin détecté | ⏳ non couvert E2E |
| Coût complet par engin + taux horaires | FINANCE, OPS_MANAGER, DIRECTION, AUDITOR | `/couts` | `GET /costs/vehicles[/{id}/history]`, `POST /costs/labour-rates` | GNF, totaux = somme des lignes | ✔ `e2e-demo/parcours-demo.spec.ts` (lecture) ; actions ⏳ |

### Administration et plateforme (scénario 10)
| Action | Rôle(s) | Route UI | API | Résultat attendu | Preuve |
|---|---|---|---|---|---|
| Créer / suspendre / réactiver une société | PLATFORM_ADMIN | `/plateforme/*` | `POST /platform/tenants[...]` | parcours complet | ⏳ UI existante ; E2E ⏳ |
| Créer site, inviter utilisateur, rôles, audit | TENANT_ADMIN | `/administration/*` | `POST /sites`, `/users`, `/role-assignments` ; `GET /audit-events` | parcours complet, 403 pour les autres | ✔ `e2e/administration.spec.ts` |
| Santé plateforme | PLATFORM_ADMIN | `/plateforme/etat` | `GET /health`, `/ready` | statuts visibles | ⏳ non couvert E2E |

## 4. Écarts ouverts (prochaines PR)

1. **UI manquante pour deux capacités backend** : `GET /insurance-policies/expiring` (échéances d'assurance) et
   `GET|POST /parts-purchase-orders` (commandes de pièces) — à ajouter respectivement à `/juridique` et `/pieces`.
2. **Specs E2E d'actions à écrire** : correction/annulation de pesée, décision/complétion d'action corrective HSE,
   décision de réapprovisionnement pièces, acquittement d'alerte GPS, cycle juridique complet, parcours plateforme.
3. **Pages à deux formes de refus** : harmoniser l'accès direct non autorisé (texte dédié vs 403 générique) —
   acceptable aujourd'hui (aucun crash, jamais de donnée), à uniformiser pour l'UX.

## 5. Exécution

```bash
# Backend + données (comme .github/workflows/e2e-isolation.yml)
alembic upgrade head
minefleet create-platform-admin --email platform-admin@example.com --name "Administrateur fictif"
minefleet seed-fictif > /tmp/e2e-accounts.txt
minefleet demo seed --profile qa --seed 42 --credentials-out /tmp/demo-accounts.tsv
uvicorn app.main:app --host 127.0.0.1 --port 8000

# Navigateur
cd frontend && npm ci && npx playwright install --with-deps chromium
MF_API_URL=http://127.0.0.1:8000 MF_DEMO_ACCOUNTS=/tmp/demo-accounts.tsv \
  npx playwright test --config=playwright.demo.config.ts
```
