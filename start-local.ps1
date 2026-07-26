[CmdletBinding()]
param([switch]$NoBrowser)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$Root = $PSScriptRoot
$Port = 8766
$Url = "http://127.0.0.1:$Port/app"
$Python = Join-Path $Root '.venv\Scripts\python.exe'
$Runtime = Join-Path $Root '.docs\runtime'
$Stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$Log = Join-Path $Runtime "start-local-$Stamp.log"
$PidFile = Join-Path $Runtime 'singh360-local.pid'
$BrowserMarker = Join-Path $Runtime 'singh360-browser-open.txt'
$BuildCommit = Join-Path $Runtime 'frontend-build-commit.txt'

New-Item -ItemType Directory -Path $Runtime -Force | Out-Null
Set-Location $Root

function Write-Log([string]$Message) {
    $line = "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] $Message"
    $line | Tee-Object -FilePath $Log -Append | Write-Host
}

function Invoke-NativeLogged([string]$File, [string[]]$Arguments) {
    $previous = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        & $File @Arguments 2>&1 | Tee-Object -FilePath $Log -Append | Out-Host
        return $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previous
    }
}

function Get-Health {
    try {
        $reply = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/api/health" -TimeoutSec 3
        return ($reply.ok -eq $true)
    } catch { return $false }
}

function Get-Listener {
    return @(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue) |
        Select-Object -First 1
}

function Test-OwnedProcess([int]$ProcessId) {
    $process = Get-CimInstance Win32_Process -Filter ("ProcessId=" + $ProcessId) -ErrorAction SilentlyContinue
    if (-not $process) { return $false }
    $command = [string]$process.CommandLine
    return $command -match '(?i)server\.py' -and
        $command.IndexOf($Root, [StringComparison]::OrdinalIgnoreCase) -ge 0
}

try {
    Write-Log "Repository: $Root"
    if (-not (Test-Path $Python)) { throw "Python environment not found: $Python" }

    $git = Get-Command git.exe -ErrorAction SilentlyContinue
    if ($git) {
        $commit = (git.exe rev-parse HEAD | Out-String).Trim()
        $dirty = (git.exe status --porcelain | Out-String).Trim()
        Write-Log "Current commit: $commit"
        if ((Invoke-NativeLogged $git.Source @('fetch', 'origin', '--prune')) -ne 0) {
            throw "Git fetch failed. Log: $Log"
        }
        if ($dirty) {
            Write-Log 'Working tree is dirty; fetched updates were not pulled over local work.'
        } else {
            $upstream = (git.exe rev-parse --abbrev-ref --symbolic-full-name '@{u}' | Out-String).Trim()
            if ($upstream) {
                if ((Invoke-NativeLogged $git.Source @('pull', '--ff-only')) -ne 0) {
                    throw "Fast-forward pull failed. Log: $Log"
                }
                $commit = (git.exe rev-parse HEAD | Out-String).Trim()
            }
        }

        $built = if (Test-Path $BuildCommit) { (Get-Content $BuildCommit -First 1).Trim() } else { '' }
        if (-not (Test-Path (Join-Path $Root 'frontend\dist\index.html')) -or $built -ne $commit) {
            $npm = (Get-Command npm.cmd -ErrorAction Stop).Source
            Write-Log "Building frontend for commit $commit."
            Push-Location (Join-Path $Root 'frontend')
            try {
                if ((Invoke-NativeLogged $npm @('run', 'build')) -ne 0) {
                    throw "Frontend build failed. Log: $Log"
                }
            } finally { Pop-Location }
            Set-Content -LiteralPath $BuildCommit -Value $commit -Encoding ASCII
        }
    }

    if (Get-Health) {
        $listener = Get-Listener
        if (-not $listener -or -not (Test-OwnedProcess ([int]$listener.OwningProcess))) {
            throw "Port $Port is healthy but is not owned by this Singh360 repository."
        }
        Write-Log "Existing Singh360 server PID $($listener.OwningProcess) is healthy; no duplicate was started."
        if (-not $NoBrowser -and -not (Test-Path $BrowserMarker)) {
            Start-Process $Url
            Set-Content $BrowserMarker "$(Get-Date -Format o) $Url" -Encoding UTF8
        }
        Write-Log "Project Home ready: $Url"
        exit 0
    }

    $listener = Get-Listener
    if ($listener) {
        if (-not (Test-OwnedProcess ([int]$listener.OwningProcess))) {
            throw "Port $Port belongs to an unrelated process. PID $($listener.OwningProcess)"
        }
        Stop-Process -Id $listener.OwningProcess -Force
        Start-Sleep -Milliseconds 700
    }
    Remove-Item $PidFile, $BrowserMarker -Force -ErrorAction SilentlyContinue

    $stdout = Join-Path $Runtime "server-$Stamp.stdout.log"
    $stderr = Join-Path $Runtime "server-$Stamp.stderr.log"
    $env:SINGH360_PORT = [string]$Port
    $env:PYTHONUNBUFFERED = '1'
    $server = Start-Process -FilePath $Python -ArgumentList @('server.py') -WorkingDirectory $Root `
        -WindowStyle Hidden -RedirectStandardOutput $stdout -RedirectStandardError $stderr -PassThru
    Set-Content $PidFile $server.Id -Encoding ASCII
    Write-Log "Started Singh360 server PID $($server.Id)."

    $deadline = (Get-Date).AddSeconds(120)
    while ((Get-Date) -lt $deadline -and -not (Get-Health)) {
        if ($server.HasExited) { throw "Server exited during startup. Error log: $stderr" }
        Start-Sleep -Milliseconds 500
    }
    if (-not (Get-Health)) { throw "Health check timed out. Error log: $stderr" }
    if (-not $NoBrowser) {
        Start-Process $Url
        Set-Content $BrowserMarker "$(Get-Date -Format o) $Url" -Encoding UTF8
    }
    Write-Log "Project Home ready: $Url"
    exit 0
} catch {
    Write-Log "START FAILED: $($_.Exception.Message)"
    Write-Error "$($_.Exception.Message)`nLog: $Log"
    exit 1
}
