# Start Singh360 server + ngrok public tunnel.
# Opt-in only — your normal VS Code workflow (python server.py) is unchanged.

$ErrorActionPreference = "Stop"
$Root = $PSScriptRoot
$Port = 8766
$NgrokUrl = "https://twig-convent-makeshift.ngrok-free.dev"

Set-Location $Root

$venvActivate = Join-Path $Root ".venv\Scripts\Activate.ps1"
if (Test-Path $venvActivate) {
    . $venvActivate
}

$env:SINGH360_PORT = "$Port"

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
Write-Host "Local app:       http://127.0.0.1:$Port/app"
Write-Host "Public app:      $NgrokUrl/app" -ForegroundColor Green
Write-Host "Ngrok dashboard: http://127.0.0.1:4040"
Write-Host ""
Write-Host "Starting ngrok in a new window..." -ForegroundColor Yellow

Start-Process powershell -ArgumentList @(
    "-NoExit",
    "-Command",
    "Write-Host 'Ngrok -> localhost:$Port ($NgrokUrl)' -ForegroundColor Cyan; Write-Host 'Dashboard: http://127.0.0.1:4040' -ForegroundColor DarkGray; ngrok http $Port --url $NgrokUrl"
)

Start-Sleep -Seconds 3

try {
    $tunnels = Invoke-RestMethod -Uri "http://127.0.0.1:4040/api/tunnels" -ErrorAction Stop
    $public = ($tunnels.tunnels | Where-Object { $_.public_url -eq $NgrokUrl } | Select-Object -First 1).public_url
    if ($public) {
        Write-Host "Ngrok tunnel ready: $public/app" -ForegroundColor Green
        Write-Host ""
    } else {
        Write-Host "Public app:      $NgrokUrl/app" -ForegroundColor Green
        Write-Host ""
    }
} catch {
    Write-Host "Public app:      $NgrokUrl/app" -ForegroundColor Green
    Write-Host "Ngrok is starting — check the ngrok window or http://127.0.0.1:4040 if the tunnel is not ready yet." -ForegroundColor DarkYellow
    Write-Host ""
}

Write-Host "Starting server (Ctrl+C stops server only; close the ngrok window to stop the tunnel)." -ForegroundColor Green
Write-Host ""

python server.py
