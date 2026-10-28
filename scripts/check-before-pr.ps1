# Executer depuis la racine du depot : .\scripts\check-before-pr.ps1
# Prerequis: Python 3.12, environnement backend installe, Node 22 et npm ci frontend.
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot

function Invoke-Check {
    param([string]$Name, [string]$Path, [string]$Program, [string[]]$Arguments)
    Write-Host "[CHECK] $Name" -ForegroundColor Cyan
    Push-Location (Join-Path $root $Path)
    try {
        & $Program @Arguments
        if ($LASTEXITCODE -ne 0) {
            throw "$Name a echoue (code $LASTEXITCODE)"
        }
    }
    finally {
        Pop-Location
    }
}

Invoke-Check "Ruff lint" "backend" "ruff" @("check", ".")
Invoke-Check "Ruff format" "backend" "ruff" @("format", "--check", ".")
Invoke-Check "mypy" "backend" "mypy" @("app")
Invoke-Check "Tests backend" "backend" "pytest" @("-q", "-p", "no:warnings")
Invoke-Check "Frontend types" "frontend" "npm" @("run", "typecheck")
Invoke-Check "Frontend unit tests" "frontend" "npm" @("test")
Write-Host "Controles locaux reussis. Verifier aussi la CI GitHub (migrations, RLS, audit)." -ForegroundColor Green
