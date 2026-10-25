# Lance la pile locale. Génère .env avec des secrets aléatoires s'il n'existe pas (jamais commité).
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$envFile = Join-Path $root '.env'

function New-Secret([int]$bytes) {
    $buf = New-Object byte[] $bytes
    [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($buf)
    return ([Convert]::ToBase64String($buf) -replace '[+/=]', '')
}

if (-not (Test-Path $envFile)) {
    $content = (Get-Content (Join-Path $root '.env.example') -Raw)
    $content = $content -replace 'POSTGRES_PASSWORD=.*', "POSTGRES_PASSWORD=$(New-Secret 24)"
    $content = $content -replace 'MF_OWNER_PASSWORD=.*', "MF_OWNER_PASSWORD=$(New-Secret 24)"
    $content = $content -replace 'MF_APP_PASSWORD=.*', "MF_APP_PASSWORD=$(New-Secret 24)"
    $content = $content -replace 'MF_JWT_SECRET=.*', "MF_JWT_SECRET=$(New-Secret 48)"
    [System.IO.File]::WriteAllText($envFile, $content.Replace("`r`n", "`n"))
    Write-Host '.env généré avec des secrets aléatoires (local uniquement).'
}

docker compose --env-file $envFile -f (Join-Path $root 'infra/docker-compose.yml') up -d --build @args
