# Start Singh360 local server + ngrok public tunnel (one command).
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force
$ErrorActionPreference = "Stop"

$Root = $PSScriptRoot
$Port = 8766
$NgrokUrl = "https://twig-convent-makeshift.ngrok-free.dev"
$LocalApp = "http://127.0.0.1:$Port/app"

Set-Location $Root

$venvActivate = Join-Path $Root ".venv\Scripts\Activate.ps1"
if (-not (Test-Path $venvActivate)) {
    Write-Error "Python venv not found at $venvActivate — run: python -m venv .venv"
    exit 1
}

$env:SINGH360_PORT = "$Port"

# Kill stale ngrok so the reserved domain is free.
Get-Process -Name ngrok -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 1

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

if (-not (Get-Command ngrok -ErrorAction SilentlyContinue)) {
    Write-Error @"
ngrok not found on PATH.
Install from https://ngrok.com/download, then run once:
  ngrok config add-authtoken <your-token>
"@
    exit 1
}

Write-Host ""
Write-Host "=== Singh360 LIVE ===" -ForegroundColor Cyan
Write-Host ""

$serverCmd = @"
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force
Set-Location '$Root'
. '$venvActivate'
`$env:SINGH360_PORT = '$Port'
Write-Host 'Singh360 server starting on $LocalApp' -ForegroundColor Green
python server.py
"@

Write-Host "Starting local server in a new window..." -ForegroundColor Yellow
Start-Process powershell -ArgumentList @("-NoExit", "-Command", $serverCmd)

# Wait for the app to respond before starting ngrok.
$ready = $false
Write-Host "Waiting for local app at $LocalApp ..." -ForegroundColor DarkGray
for ($i = 0; $i -lt 45; $i++) {
    try {
        $resp = Invoke-WebRequest -Uri $LocalApp -UseBasicParsing -TimeoutSec 3
        if ($resp.StatusCode -eq 200) {
            $ready = $true
            break
        }
    } catch {
        # server still starting
    }
    Start-Sleep -Seconds 1
}

if (-not $ready) {
    Write-Error "Local app did not return HTTP 200 at $LocalApp within 45 seconds. Check the server window for errors."
    exit 1
}

Write-Host "Local app ready: $LocalApp" -ForegroundColor Green
Write-Host ""

$ngrokCmd = @"
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force
Write-Host 'Ngrok tunnel -> localhost:$Port ($NgrokUrl)' -ForegroundColor Cyan
Write-Host 'Dashboard: http://127.0.0.1:4040' -ForegroundColor DarkGray
ngrok http $Port --url $NgrokUrl
"@

Write-Host "Starting ngrok in a new window..." -ForegroundColor Yellow
Start-Process powershell -ArgumentList @("-NoExit", "-Command", $ngrokCmd)

Start-Sleep -Seconds 3

try {
    $tunnels = Invoke-RestMethod -Uri "http://127.0.0.1:4040/api/tunnels" -ErrorAction Stop
    $public = ($tunnels.tunnels | Where-Object { $_.public_url -eq $NgrokUrl } | Select-Object -First 1).public_url
    if ($public) {
        Write-Host "Ngrok tunnel ready." -ForegroundColor Green
    }
} catch {
    Write-Host "Ngrok is starting — check the ngrok window or http://127.0.0.1:4040 if the tunnel is not ready yet." -ForegroundColor DarkYellow
}

Write-Host ""
Write-Host "SUCCESS — Singh360 is live" -ForegroundColor Green
Write-Host "  Local app:  $LocalApp"
Write-Host "  Public app: $NgrokUrl/app" -ForegroundColor Green
Write-Host ""
Write-Host "Server and ngrok run in separate windows. Close those windows to stop them." -ForegroundColor DarkGray
Write-Host ""
