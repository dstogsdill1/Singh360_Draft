# Singh360 Draft local server plus ngrok tunnel.
# This file intentionally uses no PowerShell here-strings.
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force
$ErrorActionPreference = "Stop"

$Root = $PSScriptRoot
$Port = 8766
$LocalApp = "http://127.0.0.1:$Port/app"
$PublicRoot = "https://twig-convent-makeshift.ngrok-free.dev"
$PublicApp = "$PublicRoot/app"
$Python = Join-Path $Root ".venv\Scripts\python.exe"

Set-Location $Root

if (-not (Test-Path $Python)) {
    Write-Host "ERROR: Python virtual environment was not found:" -ForegroundColor Red
    Write-Host "  $Python" -ForegroundColor Red
    exit 1
}

if (-not (Get-Command ngrok -ErrorAction SilentlyContinue)) {
    Write-Host "ERROR: ngrok was not found on PATH." -ForegroundColor Red
    Write-Host "Install or repair ngrok, then run this script again." -ForegroundColor Yellow
    exit 1
}

$distIndex = Join-Path $Root "frontend\dist\index.html"
if (-not (Test-Path $distIndex)) {
    Write-Host "Frontend build is missing. Building now..." -ForegroundColor Yellow
    Push-Location (Join-Path $Root "frontend")
    try {
        if (-not (Test-Path "node_modules")) {
            npm install
            if ($LASTEXITCODE -ne 0) { throw "npm install failed." }
        }
        npm run build
        if ($LASTEXITCODE -ne 0) { throw "npm run build failed." }
    }
    finally {
        Pop-Location
    }
}

Write-Host ""
Write-Host "Stopping old Singh360 listener on port $Port..." -ForegroundColor DarkGray
$connections = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
if ($connections) {
    $connections |
        Select-Object -ExpandProperty OwningProcess -Unique |
        ForEach-Object {
            Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue
        }
}
Get-Process -Name ngrok -ErrorAction SilentlyContinue |
    Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 1

$serverCommand = 'cd /d "' + $Root + '" && set "SINGH360_PORT=' + $Port + '" && "' + $Python + '" server.py'
Write-Host "Starting local server in a new window..." -ForegroundColor Yellow
Start-Process -FilePath "cmd.exe" -ArgumentList @("/k", $serverCommand)

Write-Host "Waiting for $LocalApp ..." -ForegroundColor DarkGray
$ready = $false
for ($i = 0; $i -lt 60; $i++) {
    try {
        $response = Invoke-WebRequest -Uri $LocalApp -UseBasicParsing -TimeoutSec 3
        if ($response.StatusCode -eq 200) {
            $ready = $true
            break
        }
    }
    catch {
    }
    Start-Sleep -Seconds 1
}

if (-not $ready) {
    Write-Host "ERROR: The local app did not start." -ForegroundColor Red
    Write-Host "Check the Singh360 Server window for the actual Python error." -ForegroundColor Yellow
    exit 1
}

Write-Host "Local app ready: $LocalApp" -ForegroundColor Green

$ngrokCommand = 'ngrok http ' + $Port + ' --url ' + $PublicRoot
Write-Host "Starting ngrok in a new window..." -ForegroundColor Yellow
Start-Process -FilePath "cmd.exe" -ArgumentList @("/k", $ngrokCommand)

Start-Sleep -Seconds 3

Write-Host ""
Write-Host "Singh360 Draft is running." -ForegroundColor Green
Write-Host "Local app:  $LocalApp"
Write-Host "Public app: $PublicApp" -ForegroundColor Green
Write-Host ""
Write-Host "The server and ngrok are running in separate windows." -ForegroundColor DarkGray

Start-Process $LocalApp
