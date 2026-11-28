# Qualification des tolérances de relevé minier

> Lot dispatch readiness — migration `0091`, service `mining_tolerance_service.py`.
> Statut : CI_VALIDÉE (tests intégration PostgreSQL locaux + CI). Il n'y a toujours
> **aucune** approbation positive de réseau ni autorisation de circulation dans ce lot.

## Objet

Une tolérance de comparaison longue déclarée / mesurée n'est pas un réglage universel :
c'est une **valeur de site, mesurée, justifiée et approuvée indépendamment**. Ce lot
comble la piece attendue par `mining_approval_policy.review_blockers` (« qualify the
survey tolerance ») et rend la tolérance d'un rapport traçable jusqu'à sa qualification.

## Modèle (0091, additif)

`mining_tolerance_qualification` — périmètre tenant/site, RLS SELECT/INSERT/UPDATE :

| Champ | Contenu |
| --- | --- |
| `tolerance_m` | valeur proposée, `>= 0` et finie |
| `survey_source` | source du relevé (texte borné 1..100) |
| `measurement_method` | méthode de mesure (texte borné 1..100) |
| `instrument_precision_m` | précision de l'instrument, `>= 0` et finie |
| `surveyed_on` | date du relevé, jamais dans le futur (CHECK) |
| `responsible_user_id` | responsable du relevé, utilisateur du tenant (trigger) |
| `referential_version` | version du référentiel topographique (1..100) |
| `justification` | justification technique (1..500) |
| `status` | `PROPOSED` → `APPROVED` → `RETIRED` |
| `proposed_by` / `approved_by` / `approved_at` / `retired_at` | cycle de vie audité |

Garanties en base (triggers) :

- les champs de relevé sont **immuables** après création (l'historique est la table + audit) ;
- l'approbation exige un `approved_by` **indépendant** (≠ proposant, ≠ responsable du relevé) et son horodatage ;
- le retrait (`RETIRED`) exige un horodatage ;
- `mining_readiness_report.tolerance_qualification_id` (colonne nouvelle, nullable pour l'historique) : le trigger d'insertion refuse un rapport lié à une qualification d'un autre site, non `APPROVED`, ou dont la valeur diffère de la `tolerance_m` du rapport.

## Règles de service

- `propose_tolerance_qualification` : permission provisoire `dispatch.location.manage` sur le site + MFA (même politique provisoire que l'enregistrement de rapport, en attente des permissions dédiées de la phase suivante) ; responsable du relevé doit appartenir au tenant.
- `approve_tolerance_qualification` : `UPDATE ... WHERE status='PROPOSED' AND proposed_by <> :actor AND responsible_user_id <> :actor RETURNING` — la transition conditionnelle est le verrou de concurrence ; refus `SELF_APPROVAL_FORBIDDEN`, `CONFLICT` (décision concurrente déjà prise), `NOT_FOUND`.
- `retire_tolerance_qualification` : `PROPOSED`/`APPROVED` → `RETIRED` ; ne réécrit pas l'historique des rapports existants.
- `load_qualified_tolerance` : ne renvoie qu'une qualification `APPROVED` du site ; identifiant étranger ≡ `NOT_FOUND` (portée tenant/site).
- `record_draft_readiness` exige désormais `tolerance_qualification_id` : la valeur du rapport doit être **exactement** celle de la qualification approuvée (`VALIDATION_ERROR` sinon). Un rapport ne peut plus être écrit avec une tolérance non qualifiée.

## Ce qui reste explicitement hors lot

- Pièces justificatives (stockage objet) : non incluses, à arbitrer avec la gouvernance documentaire.
- Routes REST et contrats OpenAPI/TypeScript : phase suivante (les services restent internes).
- Permissions RBAC dédiées (`dispatch.readiness.*`) : phase suivante ; la politique provisoire est documentée dans chaque docstring.
- Approbation positive et activation : volontairement indisponibles ; la cohérence transactionnelle et le contrôle de fraîchette des preuves restent à outiller avant.
