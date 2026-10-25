# Applique les migrations Alembic (rôle mf_owner) sur la base de développement.
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
docker compose --env-file (Join-Path $root '.env') -f (Join-Path $root 'infra/docker-compose.yml') `
    exec api alembic upgrade head
