[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force

$Root = $PSScriptRoot
$Port = 8766
$LocalRoot = "http://127.0.0.1:$Port"
$ProjectId = "b0904c99f2404524"
$Target = "$LocalRoot/app?project=$ProjectId&mode=editor"
$PythonConsole = Join-Path $Root ".venv\Scripts\python.exe"
$PythonWindowless = Join-Path $Root ".venv\Scripts\pythonw.exe"
$Python = if (Test-Path $PythonWindowless) { $PythonWindowless } else { $PythonConsole }
$Runtime = Join-Path $Root ".docs\runtime"
$LogDir = Join-Path $Root ".docs\runtime_logs\$(Get-Date -Format 'yyyyMMdd_HHmmss')"
$ServerPidFile = Join-Path $Runtime "singh360-server.pid"
$NgrokPidFile = Join-Path $Runtime "singh360-ngrok.pid"
$ServerOut = Join-Path $LogDir "server.stdout.log"
$ServerErr = Join-Path $LogDir "server.stderr.log"
$NgrokOut = Join-Path $LogDir "ngrok.stdout.log"
$NgrokErr = Join-Path $LogDir "ngrok.stderr.log"

New-Item -ItemType Directory -Path $Runtime -Force | Out-Null
New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
Set-Location $Root

function Stop-Pid([string]$Path) {
    if (-not (Test-Path $Path)) { return }
    $raw = Get-Content $Path -ErrorAction SilentlyContinue | Select-Object -First 1
    $value = 0
    if ([int]::TryParse([string]$raw, [ref]$value) -and $value -gt 0) {
        Stop-Process -Id $value -Force -ErrorAction SilentlyContinue
    }
    Remove-Item $Path -Force -ErrorAction SilentlyContinue
}

function Wait-Health([string]$Url) {
    for ($i = 1; $i -le 80; $i++) {
        try {
            $reply = Invoke-RestMethod -Uri $Url -TimeoutSec 3
            if ($reply.ok -eq $true) { return $true }
        } catch {
        }
        Start-Sleep -Milliseconds 500
    }
    return $false
}

Stop-Pid $ServerPidFile
Stop-Pid $NgrokPidFile
Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
    Select-Object -ExpandProperty OwningProcess -Unique |
    ForEach-Object { Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue }
Get-Process -Name ngrok -ErrorAction SilentlyContinue |
    Stop-Process -Force -ErrorAction SilentlyContinue

$env:SINGH360_PORT = [string]$Port
$server = Start-Process `
    -FilePath $Python `
    -ArgumentList @("server.py") `
    -WorkingDirectory $Root `
    -WindowStyle Hidden `
    -RedirectStandardOutput $ServerOut `
    -RedirectStandardError $ServerErr `
    -PassThru
Set-Content $ServerPidFile $server.Id -Encoding ASCII

if (-not (Wait-Health "$LocalRoot/api/health")) {
    Get-Content $ServerOut -Tail 120 -ErrorAction SilentlyContinue
    Get-Content $ServerErr -Tail 120 -ErrorAction SilentlyContinue
    throw "Singh360 did not start."
}

$ngrokCommand = Get-Command ngrok.exe -ErrorAction SilentlyContinue
if (-not $ngrokCommand) { $ngrokCommand = Get-Command ngrok -ErrorAction SilentlyContinue }
if ($ngrokCommand) {
    $ngrok = Start-Process `
        -FilePath $ngrokCommand.Source `
        -ArgumentList @(
            "http",
            [string]$Port,
            "--url",
            "https://twig-convent-makeshift.ngrok-free.dev"
        ) `
        -WorkingDirectory $Root `
        -WindowStyle Hidden `
        -RedirectStandardOutput $NgrokOut `
        -RedirectStandardError $NgrokErr `
        -PassThru
    Set-Content $NgrokPidFile $ngrok.Id -Encoding ASCII
}

Start-Process $Target
Write-Host "Mi Tienda 829 is open: $Target" -ForegroundColor Green
Write-Host "Server and ngrok are hidden. Closing this window will not stop them." -ForegroundColor Green
Start-Sleep -Seconds 2
