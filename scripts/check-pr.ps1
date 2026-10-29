# Prévalidation locale : mêmes commandes principales que la CI GitHub.
# Usage : powershell -ExecutionPolicy Bypass -File .\scripts\check-pr.ps1
# Option : -Full pour exécuter aussi les tests backend (base de test requise).
param([switch]$Full)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$root = Split-Path -Parent $PSScriptRoot
$compose = Join-Path $root 'infra/docker-compose.yml'
$envFile = Join-Path $root '.env'

function Invoke-Checked([string]$label, [scriptblock]$action) {
    Write-Host "==> $label" -ForegroundColor Cyan
    & $action
    if ($LASTEXITCODE -ne 0) {
        throw "$label : échec (code $LASTEXITCODE). Arrêt avant PR."
    }
}

if (-not (Test-Path $envFile)) {
    throw "Fichier .env absent. Lancer scripts/dev-up.ps1 d'abord."
}
if (-not (Test-Path $compose)) {
    throw "Fichier Docker Compose introuvable."
}

Push-Location $root
try {
    Invoke-Checked 'Docker Compose disponible' { docker compose version }
    Invoke-Checked 'Conteneur API actif' { docker compose --env-file $envFile -f $compose exec -T api python --version }
    Invoke-Checked 'Ruff lint backend' { docker compose --env-file $envFile -f $compose exec -T api ruff check . }
    Invoke-Checked 'Ruff format backend' { docker compose --env-file $envFile -f $compose exec -T api ruff format --check . }
    Invoke-Checked 'Mypy backend' { docker compose --env-file $envFile -f $compose exec -T api mypy app }
    # Python local doit disposer de PyYAML : python -m pip install pyyaml==6.0.3
    Invoke-Checked 'Permissions frontend générées' { python scripts/gen_permissions.py --check }
    Push-Location (Join-Path $root 'frontend')
    try {
        Invoke-Checked 'TypeScript' { npm run typecheck }
        Invoke-Checked 'Tests frontend' { npm test }
        Invoke-Checked 'Build frontend' { npm run build }
    }
    finally {
        Pop-Location
    }
    if ($Full) {
        Invoke-Checked 'Tests backend complets' {
            docker compose --env-file $envFile -f $compose exec -T api pytest -q -p no:warnings --cov=app --cov-branch --cov-report=term-missing:skip-covered --cov-fail-under=85
        }
    }
    Write-Host 'Contrôles locaux terminés avec succès.' -ForegroundColor Green
}
finally {
    Pop-Location
}
