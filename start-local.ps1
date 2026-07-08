# Start Singh360 local server only (no ngrok).
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force
$ErrorActionPreference = "Stop"

$Root = $PSScriptRoot
$Port = 8766
$LocalApp = "http://127.0.0.1:$Port/app"

Set-Location $Root

$venvActivate = Join-Path $Root ".venv\Scripts\Activate.ps1"
if (-not (Test-Path $venvActivate)) {
    Write-Error "Python venv not found at $venvActivate — run: python -m venv .venv"
    exit 1
}

. $venvActivate
$env:SINGH360_PORT = "$Port"

# Build frontend when dist is missing or package files are newer.
$distDir = Join-Path $Root "frontend\dist"
$pkgJson = Join-Path $Root "frontend\package.json"
$pkgLock = Join-Path $Root "frontend\package-lock.json"
$needsBuild = -not (Test-Path $distDir)
if (-not $needsBuild) {
    $distTime = (Get-Item $distDir).LastWriteTime
    if ((Test-Path $pkgJson) -and (Get-Item $pkgJson).LastWriteTime -gt $distTime) { $needsBuild = $true }
    if ((Test-Path $pkgLock) -and (Get-Item $pkgLock).LastWriteTime -gt $distTime) { $needsBuild = $true }
}
if ($needsBuild) {
    Write-Host "Building frontend (dist missing or package files changed)..." -ForegroundColor Yellow
    Push-Location (Join-Path $Root "frontend")
    try {
        if (Test-Path $pkgLock) { npm ci } else { npm install }
        npm run build
        if ($LASTEXITCODE -ne 0) { throw "npm run build failed with exit code $LASTEXITCODE" }
    } finally {
        Pop-Location
    }
    Write-Host "Frontend build complete." -ForegroundColor Green
}

Write-Host ""
Write-Host "=== Singh360 LOCAL ===" -ForegroundColor Cyan
Write-Host "Local app: $LocalApp" -ForegroundColor Green
Write-Host ""
Write-Host "Starting server (Ctrl+C to stop)..." -ForegroundColor Yellow
Write-Host ""

python server.py
