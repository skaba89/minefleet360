# Contrôles qualité backend dans le conteneur (Python 3.12) : ruff, mypy, pytest (base minefleet_test).
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$compose = @('compose', '--env-file', (Join-Path $root '.env'), '-f', (Join-Path $root 'infra/docker-compose.yml'))
docker @compose exec api ruff check .
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
docker @compose exec api ruff format --check .
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
docker @compose exec api mypy app
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
docker @compose exec -e MF_ENV=test -e MF_DB_NAME=minefleet_test api pytest @args
exit $LASTEXITCODE
