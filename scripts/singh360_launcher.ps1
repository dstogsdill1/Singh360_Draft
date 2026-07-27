[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("Start", "Stop")]
    [string]$Action,

    [int]$Port = 8766,

    [switch]$NoBrowser
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$global:LASTEXITCODE = 0

$repo = [System.IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot)).TrimEnd("\")
$python = Join-Path $repo ".venv\Scripts\python.exe"
$server = Join-Path $repo "server.py"
$runtimeDir = Join-Path $repo ".docs\runtime"
$logDir = Join-Path $repo ".docs\runtime_logs"
$pidFile = Join-Path $runtimeDir "singh360-draft.pid"
$stateFile = Join-Path $runtimeDir "singh360-draft.state.json"
$browserFile = Join-Path $runtimeDir "singh360-draft.browser.pid"
$appUrl = "http://127.0.0.1:$Port/app"

function Get-PortListener {
    $listeners = @(
        Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
            Select-Object -ExpandProperty OwningProcess -Unique
    )
    if ($listeners.Count -eq 0) {
        return $null
    }
    if ($listeners.Count -gt 1) {
        throw "Port $Port has multiple listener PIDs: $($listeners -join ', ')."
    }
    return Get-CimInstance Win32_Process -Filter ("ProcessId=" + $listeners[0]) -ErrorAction SilentlyContinue
}

function Test-Singh360Process {
    param([AllowNull()]$Process)

    if (-not $Process -or -not $Process.CommandLine) {
        return $false
    }

    $pythonQuoted = [regex]::Escape('"' + $python + '"')
    $pythonBare = [regex]::Escape($python)
    $serverQuoted = [regex]::Escape('"' + $server + '"')
    $serverBare = [regex]::Escape($server)
    $relativeServer = [regex]::Escape("server.py")
    $pattern = (
        "^\s*(?:$pythonQuoted|$pythonBare)\s+" +
        "(?:-u\s+)?" +
        "(?:$serverQuoted|$serverBare|$relativeServer)(?:\s|$)"
    )
    return [bool]([regex]::IsMatch(
        [string]$Process.CommandLine,
        $pattern,
        [System.Text.RegularExpressions.RegexOptions]::IgnoreCase
    ))
}

function Show-ProcessIdentity {
    param([AllowNull()]$Process)

    if (-not $Process) {
        Write-Host "PID: unavailable"
        Write-Host "Executable: unavailable"
        Write-Host "Command line: unavailable"
        return
    }
    $executable = if ($Process.ExecutablePath) { $Process.ExecutablePath } else { "(unavailable)" }
    $commandLine = if ($Process.CommandLine) { $Process.CommandLine } else { "(unavailable)" }
    Write-Host ("PID: " + $Process.ProcessId)
    Write-Host ("Executable: " + $executable)
    Write-Host ("Command line: " + $commandLine)
}

function Clear-LauncherState {
    foreach ($path in @($pidFile, $stateFile, $browserFile)) {
        if (Test-Path -LiteralPath $path) {
            Remove-Item -LiteralPath $path -Force
        }
    }
}

function Repair-LauncherState {
    param($Process)

    New-Item -ItemType Directory -Path $runtimeDir -Force | Out-Null
    $pidText = [string]$Process.ProcessId
    $pidTemp = "$pidFile.tmp-$PID"
    $stateTemp = "$stateFile.tmp-$PID"
    Set-Content -LiteralPath $pidTemp -Value $pidText -NoNewline -Encoding ascii
    Move-Item -LiteralPath $pidTemp -Destination $pidFile -Force
    [ordered]@{
        pid = [int]$Process.ProcessId
        port = $Port
        repository = $repo
        executable = [string]$Process.ExecutablePath
        commandLine = [string]$Process.CommandLine
        repairedAt = (Get-Date).ToString("o")
    } | ConvertTo-Json | Set-Content -LiteralPath $stateTemp -Encoding utf8
    Move-Item -LiteralPath $stateTemp -Destination $stateFile -Force
}

function Open-AppOnce {
    param([int]$ServerPid)

    if ($NoBrowser -or $env:SINGH360_LAUNCHER_NO_BROWSER -eq "1") {
        Write-Host "Browser launch suppressed for automated verification."
        return
    }

    $alreadyOpened = (
        (Test-Path -LiteralPath $browserFile) -and
        ((Get-Content -LiteralPath $browserFile -Raw).Trim() -eq [string]$ServerPid)
    )
    if ($alreadyOpened) {
        Write-Host "Singh360 Draft is already open in the browser."
        return
    }

    Start-Process $appUrl
    Set-Content -LiteralPath $browserFile -Value $ServerPid -NoNewline -Encoding ascii
}

function Test-FrontendBuildRequired {
    $distIndex = Join-Path $repo "frontend\dist\index.html"
    if (-not (Test-Path -LiteralPath $distIndex)) {
        return $true
    }

    $sourceFiles = @()
    $sourceDir = Join-Path $repo "frontend\src"
    if (Test-Path -LiteralPath $sourceDir) {
        $sourceFiles += Get-ChildItem -LiteralPath $sourceDir -File -Recurse
    }
    foreach ($relative in @(
        "frontend\index.html",
        "frontend\package.json",
        "frontend\package-lock.json",
        "frontend\vite.config.ts",
        "frontend\tsconfig.json",
        "frontend\tsconfig.app.json",
        "frontend\tsconfig.node.json"
    )) {
        $candidate = Join-Path $repo $relative
        if (Test-Path -LiteralPath $candidate) {
            $sourceFiles += Get-Item -LiteralPath $candidate
        }
    }
    if ($sourceFiles.Count -eq 0) {
        return $false
    }

    $newestSource = ($sourceFiles | Measure-Object -Property LastWriteTimeUtc -Maximum).Maximum
    $buildTime = (Get-Item -LiteralPath $distIndex).LastWriteTimeUtc
    return $newestSource -gt $buildTime
}

function Ensure-StartPrerequisites {
    if (-not (Test-Path -LiteralPath $python)) {
        Write-Host "Creating the Singh360 Draft Python environment..."
        & py -3 -m venv (Join-Path $repo ".venv")
        if ($LASTEXITCODE -ne 0) {
            throw "Unable to create the Singh360 Draft Python environment."
        }
    }

    & $python -c "import flask, openpyxl, fitz" *> $null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Installing Python dependencies..."
        & $python -m pip install -r (Join-Path $repo "requirements.txt")
        if ($LASTEXITCODE -ne 0) {
            throw "Python dependency installation failed."
        }
    }

    if (-not (Test-FrontendBuildRequired)) {
        Write-Host "Frontend production build is current; skipping rebuild."
        return
    }

    $nodeCommand = Get-Command node.exe -ErrorAction SilentlyContinue
    if (-not $nodeCommand) {
        throw "Node.js/npm is required to build Singh360 Draft."
    }
    $node = $nodeCommand.Source
    $npmCli = Join-Path (Split-Path -Parent $node) "node_modules\npm\bin\npm-cli.js"
    if (-not (Test-Path -LiteralPath $npmCli)) {
        throw "The Node.js npm CLI was not found at $npmCli."
    }

    $frontendDir = Join-Path $repo "frontend"
    if (-not (Test-Path -LiteralPath (Join-Path $frontendDir "node_modules"))) {
        $npmArguments = '"' + $npmCli + '" ci'
        $install = Start-Process `
            -FilePath $node `
            -ArgumentList $npmArguments `
            -WorkingDirectory $frontendDir `
            -NoNewWindow `
            -Wait `
            -PassThru
        if ($install.ExitCode -ne 0) {
            throw "Frontend dependency installation failed."
        }
    }

    $tsc = Join-Path $frontendDir "node_modules\typescript\bin\tsc"
    $vite = Join-Path $frontendDir "node_modules\vite\bin\vite.js"
    if (-not (Test-Path -LiteralPath $tsc) -or -not (Test-Path -LiteralPath $vite)) {
        throw "Frontend build tools are missing; remove frontend\node_modules and restart to reinstall them."
    }

    Write-Host "Frontend sources changed; building the production frontend..."
    $typecheck = Start-Process `
        -FilePath $node `
        -ArgumentList ('"' + $tsc + '" -b') `
        -WorkingDirectory $frontendDir `
        -NoNewWindow `
        -Wait `
        -PassThru
    if ($typecheck.ExitCode -ne 0) {
        throw "Frontend TypeScript build failed."
    }
    $bundle = Start-Process `
        -FilePath $node `
        -ArgumentList ('"' + $vite + '" build') `
        -WorkingDirectory $frontendDir `
        -NoNewWindow `
        -Wait `
        -PassThru
    if ($bundle.ExitCode -ne 0) {
        throw "Frontend Vite build failed."
    }
    if (-not (Test-Path -LiteralPath (Join-Path $frontendDir "dist\index.html"))) {
        throw "Frontend build reported success but frontend\dist\index.html is missing."
    }
    Write-Host "Frontend production build completed. Vite size advisories are informational."
}

function Start-Singh360 {
    $listener = Get-PortListener
    if ($listener) {
        if (-not (Test-Singh360Process $listener)) {
            Clear-LauncherState
            Write-Host "ERROR: Port $Port belongs to an unrelated process. Nothing was terminated." -ForegroundColor Red
            Show-ProcessIdentity $listener
            return 1
        }
        Repair-LauncherState $listener
        Write-Host ("Singh360 Draft is already running (PID " + $listener.ProcessId + ").") -ForegroundColor Green
        Open-AppOnce ([int]$listener.ProcessId)
        return 0
    }

    Clear-LauncherState
    Ensure-StartPrerequisites
    New-Item -ItemType Directory -Path $runtimeDir -Force | Out-Null
    New-Item -ItemType Directory -Path $logDir -Force | Out-Null

    $stamp = (Get-Date).ToString("yyyyMMdd-HHmmss")
    $stdout = Join-Path $logDir "singh360-draft-$stamp.out.log"
    $stderr = Join-Path $logDir "singh360-draft-$stamp.err.log"
    $env:SINGH360_PORT = [string]$Port
    $started = Start-Process `
        -FilePath $python `
        -ArgumentList "server.py" `
        -WorkingDirectory $repo `
        -WindowStyle Hidden `
        -RedirectStandardOutput $stdout `
        -RedirectStandardError $stderr `
        -PassThru

    $deadline = (Get-Date).AddSeconds(45)
    $listener = $null
    do {
        Start-Sleep -Milliseconds 500
        $listener = Get-PortListener
        $started.Refresh()
    } until ($listener -or $started.HasExited -or (Get-Date) -gt $deadline)

    if (-not $listener) {
        if (-not $started.HasExited) {
            Stop-Process -Id $started.Id -Force -ErrorAction SilentlyContinue
        }
        throw "Singh360 Draft did not begin listening on port $Port. Review $stderr."
    }
    if (-not (Test-Singh360Process $listener)) {
        if (-not $started.HasExited) {
            Stop-Process -Id $started.Id -Force -ErrorAction SilentlyContinue
        }
        Write-Host "ERROR: An unrelated process acquired port $Port while Singh360 Draft was starting. It was not terminated." -ForegroundColor Red
        Show-ProcessIdentity $listener
        return 1
    }

    Repair-LauncherState $listener
    Write-Host ("Singh360 Draft is running at $appUrl (PID " + $listener.ProcessId + ").") -ForegroundColor Green
    Open-AppOnce ([int]$listener.ProcessId)
    return 0
}

function Stop-Singh360 {
    $listener = Get-PortListener
    if (-not $listener) {
        Clear-LauncherState
        Write-Host "Singh360 Draft is already stopped. Stale launcher state was removed." -ForegroundColor Yellow
        return 0
    }
    if (-not (Test-Singh360Process $listener)) {
        Clear-LauncherState
        Write-Host "ERROR: Port $Port belongs to an unrelated process. Nothing was terminated." -ForegroundColor Red
        Show-ProcessIdentity $listener
        return 1
    }

    $verifiedParent = $null
    if ($listener.ParentProcessId) {
        $candidate = Get-CimInstance Win32_Process -Filter ("ProcessId=" + $listener.ParentProcessId) -ErrorAction SilentlyContinue
        if (Test-Singh360Process $candidate) {
            $verifiedParent = $candidate
        }
    }

    $listenerPid = [int]$listener.ProcessId
    Stop-Process -Id $listenerPid -Force
    $deadline = (Get-Date).AddSeconds(10)
    do {
        Start-Sleep -Milliseconds 200
        $remaining = Get-PortListener
    } until (-not $remaining -or (Get-Date) -gt $deadline)

    if ($remaining) {
        throw "Singh360 Draft PID $listenerPid did not release port $Port."
    }
    if ($verifiedParent) {
        Stop-Process -Id ([int]$verifiedParent.ProcessId) -Force -ErrorAction SilentlyContinue
    }
    Clear-LauncherState
    Write-Host ("Singh360 Draft PID $listenerPid stopped.") -ForegroundColor Green
    return 0
}

$createdMutex = $false
$mutexName = "Local\Singh360Draft-Launcher-$Port"
$mutex = [System.Threading.Mutex]::new($false, $mutexName)
try {
    try {
        $createdMutex = $mutex.WaitOne([TimeSpan]::FromSeconds(60))
    }
    catch [System.Threading.AbandonedMutexException] {
        $createdMutex = $true
    }
    if (-not $createdMutex) {
        throw "Timed out waiting for another Singh360 Draft launcher operation."
    }

    $result = if ($Action -eq "Start") { Start-Singh360 } else { Stop-Singh360 }
    exit $result
}
catch {
    Write-Host ("ERROR: " + $_.Exception.Message) -ForegroundColor Red
    exit 1
}
finally {
    if ($createdMutex) {
        $mutex.ReleaseMutex()
    }
    $mutex.Dispose()
}
