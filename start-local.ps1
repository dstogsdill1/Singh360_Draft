# Singh360 Draft local-only startup.
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force
$ErrorActionPreference = "Stop"

$Root = $PSScriptRoot
$Port = 8766
$LocalApp = "http://127.0.0.1:$Port/app"
$Python = Join-Path $Root ".venv\Scripts\python.exe"

Set-Location $Root

if (-not (Test-Path $Python)) {
    Write-Host "ERROR: Python virtual environment was not found:" -ForegroundColor Red
    Write-Host "  $Python" -ForegroundColor Red
    exit 1
}

$connections = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
if ($connections) {
    $connections |
        Select-Object -ExpandProperty OwningProcess -Unique |
        ForEach-Object {
            Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue
        }
}

$serverCommand = 'cd /d "' + $Root + '" && set "SINGH360_PORT=' + $Port + '" && "' + $Python + '" server.py'
Start-Process -FilePath "cmd.exe" -ArgumentList @("/k", $serverCommand)

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
    exit 1
}

Write-Host "Local app: $LocalApp" -ForegroundColor Green
Start-Process $LocalApp
