[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$Root = $PSScriptRoot
$Port = 8766
$Runtime = Join-Path $Root '.docs\runtime'
$Log = Join-Path $Runtime "stop-local-$(Get-Date -Format 'yyyyMMdd-HHmmss').log"
$PidFile = Join-Path $Runtime 'singh360-local.pid'
$BrowserMarker = Join-Path $Runtime 'singh360-browser-open.txt'
New-Item -ItemType Directory -Path $Runtime -Force | Out-Null

try {
    $listeners = @(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)
    foreach ($listener in $listeners) {
        $process = Get-CimInstance Win32_Process -Filter ("ProcessId=" + $listener.OwningProcess)
        $command = [string]$process.CommandLine
        if ($command -notmatch '(?i)server\.py' -or $command.IndexOf($Root, [StringComparison]::OrdinalIgnoreCase) -lt 0) {
            throw "Port $Port belongs to an unrelated process. PID $($listener.OwningProcess). Nothing was stopped."
        }
        Stop-Process -Id $listener.OwningProcess -Force
        "Stopped Singh360 PID $($listener.OwningProcess)." | Tee-Object -FilePath $Log | Write-Host
    }
    Remove-Item $PidFile, $BrowserMarker -Force -ErrorAction SilentlyContinue
    if (-not $listeners) { 'No Singh360 listener was running.' | Tee-Object -FilePath $Log | Write-Host }
    exit 0
} catch {
    $_.Exception.Message | Tee-Object -FilePath $Log | Write-Error
    exit 1
}
