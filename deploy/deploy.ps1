# ---------------------------------------------------------------------------
# Warrigal Park FC — deployment script for Windows (PowerShell)
#
#   .\deploy\deploy.ps1
#   $env:APP_PORT=9000; .\deploy\deploy.ps1
#
# The script validates the checkout, backs up an existing database, and starts
# the application.  It never overwrites or deletes anything.
# ---------------------------------------------------------------------------
$ErrorActionPreference = 'Stop'

$ProjectRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $ProjectRoot

if (-not $env:APP_ENV)     { $env:APP_ENV = 'production' }
if (-not $env:APP_HOST)    { $env:APP_HOST = '0.0.0.0' }
if (-not $env:APP_PORT)    { $env:APP_PORT = '8080' }
if (-not $env:APP_DB_PATH) { $env:APP_DB_PATH = Join-Path $ProjectRoot 'data\warrigal_park.db' }
if (-not $env:APP_SEED)    { $env:APP_SEED = 'false' }

Write-Host '=============================================================='
Write-Host '  Warrigal Park FC - deployment'
Write-Host "  environment : $env:APP_ENV"
Write-Host "  listening   : $env:APP_HOST`:$env:APP_PORT"
Write-Host "  database    : $env:APP_DB_PATH"
Write-Host '=============================================================='

Write-Host ''
Write-Host '[1/5] Checking the Python runtime'
python --version

Write-Host ''
Write-Host '[2/5] Running the automated test suite'
python -m unittest discover -s tests -t .
if ($LASTEXITCODE -ne 0) { throw 'The test suite failed; deployment stopped.' }

Write-Host ''
Write-Host '[3/5] Preparing the data directory'
$dataDir = Split-Path -Parent $env:APP_DB_PATH
if (-not (Test-Path $dataDir)) { New-Item -ItemType Directory -Path $dataDir -Force | Out-Null }
if (Test-Path $env:APP_DB_PATH) {
    $stamp  = Get-Date -Format 'yyyyMMdd-HHmmss'
    $backup = "$env:APP_DB_PATH.$stamp.bak"
    Copy-Item $env:APP_DB_PATH $backup
    Write-Host "      existing database backed up to $backup"
} else {
    Write-Host '      no existing database; a new one will be created on first request'
}

Write-Host ''
Write-Host '[4/5] Applying the configuration'
python -c "from config import get_settings; s = get_settings(); print('      ' + s.describe())"
if ($env:APP_ENV -eq 'production' -and $env:APP_SEED -eq 'true') {
    throw 'APP_SEED must be false in production so the fictitious sample roster is never loaded over real club data.'
}

Write-Host ''
Write-Host '[5/5] Starting the application (Ctrl+C to stop)'
python wsgi.py
