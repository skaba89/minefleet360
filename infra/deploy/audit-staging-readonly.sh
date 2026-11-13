#!/usr/bin/env bash
# Audit staging en lecture seule — rejoue la phase A (A1–A8) de
# docs/ops/RECETTE_STAGING_VALIDATION.md et produit un fragment de rapport daté (§R).
#
# Aucune mutation : pas de staging-release.sh apply|rollback, pas de compose up/down/pull,
# pas de backup.sh, pas de DDL/DML — seules des lectures (labels, catalogues PostgreSQL,
# sondes, GET API) sont exécutées. La phase B (dry-run de release) reste décrite dans le
# runbook ; les phases C/D exigent une approbation explicite et sont hors périmètre ici.
#
# Usage : bash audit-staging-readonly.sh [--plan] [--live] [--out <fichier>]
#   --plan   affiche les commandes sans rien exécuter (vérification de portée)
#   --live   exécute aussi les sondes HTTP (--live de check-preproduction.sh, A5/A7/A8)
#   --out    chemin du rapport (défaut : audit-staging-readonly-<horodatage>.txt)
# Codes de sortie : 0 aucun échec · 2 au moins un échec · 3 configuration.
set -uo pipefail
umask 077

PLAN=0
LIVE=0
OUT=""
while [ $# -gt 0 ]; do
  case "$1" in
    --plan) PLAN=1 ;;
    --live) LIVE=1 ;;
    --out) OUT="${2:?--out exige un chemin}"; shift ;;
    *) echo "option inconnue : $1" >&2; exit 3 ;;
  esac
  shift
done

DEPLOY_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DEPLOY_DIR"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
OUT="${OUT:-audit-staging-readonly-${STAMP}.txt}"
FAILURES=0
SKIPS=0

# --- Garde de configuration (mire du contrôle MF_ENV de staging-release.sh) --------------------------
if [ ! -f .env.prod ]; then
  echo "CONFIG : .env.prod absent dans $DEPLOY_DIR — audit annulé (la phase A exige le .env.prod en place)" >&2
  exit 3
fi
if [ "$(sed -n 's/^MF_ENV=//p' .env.prod)" != "staging" ]; then
  echo "CONFIG : .env.prod ne déclare pas exactement MF_ENV=staging — audit annulé (jamais ailleurs que sur staging)" >&2
  exit 3
fi
STAGING_URL="${MINEFLEET_STAGING_URL:-}"

section() { printf '\n=== %s ===\n' "$1" | tee -a "$OUT"; }
stamp()   { printf '[%s] ' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" | tee -a "$OUT"; }
runsh() { # runsh <étiquette> <script-shell> — exécute avec bash -c (ou affiche en --plan) et consigne
  local label="$1" script="$2" code
  stamp; printf 'A-%s\n' "$label" | tee -a "$OUT"
  if [ "$PLAN" -eq 1 ]; then
    printf '  [plan] %s\n' "$script" | tee -a "$OUT"
    return 0
  fi
  if bash -c "$script" >>"$OUT" 2>&1; then
    printf '  statut : OK\n' | tee -a "$OUT"
  else
    code=$?
    printf '  statut : ÉCHEC (exit %s)\n' "$code" | tee -a "$OUT"
    FAILURES=$((FAILURES + 1))
  fi
}
skip() { # skip <étiquette> <raison>
  stamp; printf 'A-%s — SKIP : %s\n' "$1" "$2" | tee -a "$OUT"
  SKIPS=$((SKIPS + 1))
}

if [ "$PLAN" -eq 0 ]; then
  {
    printf 'Rapport audit staging lecture seule — phase A (A1–A8) de docs/ops/RECETTE_STAGING_VALIDATION.md\n'
    printf 'Début : %s · hôte : %s · répertoire : %s\n' "$STAMP" "$(hostname)" "$DEPLOY_DIR"
    printf 'Portée : lectures uniquement ; aucune donnée secrète n’est collectée (le .env.prod n’est jamais affiché)\n'
  } >"$OUT"
fi

section "A1 — Versions déployées (API / frontend / commit)"
runsh "1-compose-ps" "docker compose -f docker-compose.prod.yml --env-file .env.prod ps"
runsh "1-labels-revision" 'docker inspect --format "{{.Name}} {{index .Config.Labels \"org.opencontainers.image.revision\"}}" "$(docker compose -f docker-compose.prod.yml --env-file .env.prod ps -q api)" "$(docker compose -f docker-compose.prod.yml --env-file .env.prod ps -q web)"'
runsh "1-release-state" "cat release-state/current.json"

section "A2 — Schéma Alembic"
runsh "2-label-alembic" 'docker inspect --format "{{index .Config.Labels \"com.minefleet.alembic-head\"}}" "$(docker compose -f docker-compose.prod.yml --env-file .env.prod ps -q api)"'
runsh "2-schema-revision" "docker compose -f docker-compose.prod.yml --env-file .env.prod --profile ops run --rm --no-deps migrate python -m app.core.check_schema_revision"

section "A3 — Images et signatures"
runsh "3-images-epinglees" "docker compose -f docker-compose.prod.yml --env-file .env.prod ps --format '{{.Image}}'"
if command -v cosign >/dev/null 2>&1; then
  runsh "3-cosign-verify" 'IMG="$(docker compose -f docker-compose.prod.yml --env-file .env.prod ps --format "{{.Image}}" | grep "/api@sha256:" | head -1)"; [ -n "$IMG" ] && cosign verify --certificate-oidc-issuer https://token.actions.githubusercontent.com --certificate-identity-regexp "^https://github.com/skaba89/minefleet360/" "$IMG"'
  runsh "3-cosign-attestation" 'IMG="$(docker compose -f docker-compose.prod.yml --env-file .env.prod ps --format "{{.Image}}" | grep "/api@sha256:" | head -1)"; [ -n "$IMG" ] && cosign verify-attestation --type https://slsa.dev/provenance/v1 --certificate-oidc-issuer https://token.actions.githubusercontent.com --certificate-identity-regexp "^https://github.com/skaba89/minefleet360/" "$IMG"'
else
  skip "3-cosign" "cosign absent de l’hôte — vérification de signature manuelle requise (runbook §A3)"
fi

section "A4 — Permissions et isolation PostgreSQL (lectures de catalogue uniquement)"
runsh "4-catalogue" "docker compose -f docker-compose.prod.yml --env-file .env.prod exec -T db psql -U postgres -d minefleet -tAc \"
SELECT rolname, rolsuper, rolbypassrls FROM pg_roles WHERE rolname IN ('mf_owner','mf_app');
SELECT has_table_privilege('mf_app','app.insurance_policy','INSERT,UPDATE,DELETE');
SELECT has_table_privilege('mf_app','app.legal_contract','INSERT');
SELECT count(*) FROM pg_tables WHERE schemaname='app' AND rowsecurity;\""

section "A5 — HTTPS et configuration Compose"
runsh "5-compose-parse" "bash check-preproduction.sh docker-compose.prod.yml"
if [ -n "$STAGING_URL" ] && [ "$LIVE" -eq 1 ]; then
  runsh "5-sondes-live" "MINEFLEET_STAGING_URL=\"$STAGING_URL\" bash check-preproduction.sh docker-compose.prod.yml --live"
  HOST_CERT="${STAGING_URL#https://}"; HOST_CERT="${HOST_CERT%%/*}"
  runsh "5-certificat" "echo | openssl s_client -connect \"$HOST_CERT\":443 -servername \"$HOST_CERT\" 2>/dev/null | openssl x509 -noout -dates"
else
  skip "5-live" "MINEFLEET_STAGING_URL absent ou --live non demandé (sondes HTTP non exécutées)"
fi

section "A6 — Comptes et permissions (API)"
skip "6-comptes" "manuelle par conception (MFA + comptes fictifs du coffre) — suivre le §A6 du runbook"

section "A7 — Routes et surface exposée"
if [ -n "$STAGING_URL" ] && [ "$LIVE" -eq 1 ]; then
  for r in / /api/v1/health /api/v1/ready /connexion /docs /openapi.json; do
    runsh "7-route${r}" "curl -s -o /dev/null -w \"%{http_code} ${r}\n\" --proto '=https' \"${STAGING_URL}${r}\""
  done
else
  skip "7-routes" "MINEFLEET_STAGING_URL absent ou --live non demandé"
fi

section "A8 — Logs et santé continue"
runsh "8-erreurs-24h" "docker compose -f docker-compose.prod.yml --env-file .env.prod logs --since 24h api web 2>&1 | grep -Eci 'traceback|error' || echo 0"
if [ -n "$STAGING_URL" ]; then
  runsh "8-sonde-globale" "MINEFLEET_BASE_URL=\"$STAGING_URL\" bash probe-all.sh"
else
  skip "8-sonde-globale" "MINEFLEET_STAGING_URL absent"
fi
runsh "8-espace-disque" "docker system df"
runsh "8-ressources" "docker compose -f docker-compose.prod.yml --env-file .env.prod stats --no-stream"

section "Synthèse"
if [ "$PLAN" -eq 1 ]; then
  printf 'Mode plan : aucune commande exécutée.\n' | tee -a "$OUT"
fi
printf 'Échecs : %s · Points passés en SKIP : %s · Rapport : %s\n' \
  "$FAILURES" "$SKIPS" "$OUT" | tee -a "$OUT"
printf 'Rappel (runbook) : une phase A sans échec ne lève aucun bloquant — elle autorise seulement à\n' | tee -a "$OUT"
printf 'demander l’approbation des phases C/D ; R1/R2 restent non validés tant que les exercices réels\n' | tee -a "$OUT"
printf 'n’ont pas produit leurs preuves. Consigner ce rapport : docs/audit/preuves/staging/ (référence + SHA256).\n' | tee -a "$OUT"
[ "$FAILURES" -eq 0 ] && exit 0 || exit 2
