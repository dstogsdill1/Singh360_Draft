# Singh360 Draft local launcher with safe Git fetch/pull and conditional frontend build.
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force
$ErrorActionPreference = "Stop"

$Root = $PSScriptRoot
$Port = 8766
$LocalApp = "http://127.0.0.1:$Port/app"
$Python = Join-Path $Root ".venv\Scripts\python.exe"
$Git = (Get-Command git.exe -ErrorAction SilentlyContinue).Source
$Npm = (Get-Command npm.cmd -ErrorAction SilentlyContinue).Source
$RuntimeDir = Join-Path $Root ".docs\runtime"
New-Item -ItemType Directory -Force -Path $RuntimeDir | Out-Null
$Stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$Log = Join-Path $RuntimeDir "start-local-$Stamp.log"

function Log([string]$Message) {
    $line = "[$(Get-Date -Format HH:mm:ss)] $Message"
    Write-Host $line
    Add-Content -Path $Log -Value $line
}

Set-Location $Root
Log "Repository: $Root"

if (-not (Test-Path $Python)) {
    throw "Python virtual environment was not found: $Python"
}

$beforeCommit = ""
$afterCommit = ""
if ($Git) {
    $beforeCommit = (& $Git rev-parse HEAD 2>$null).Trim()
    Log "Current commit: $beforeCommit"
    Log "Fetching GitHub updates."
    & $Git fetch origin --prune 2>&1 | Tee-Object -FilePath $Log -Append | Out-Host

    $dirty = (& $Git status --porcelain).Trim()
    $upstream = (& $Git rev-parse --abbrev-ref --symbolic-full-name "@{u}" 2>$null).Trim()
    if ($dirty) {
        Log "Local working-tree changes exist. Updates were fetched but not pulled over local work."
    }
    elseif ($upstream) {
        Log "Working tree is clean. Pulling fast-forward-only from $upstream."
        & $Git pull --ff-only 2>&1 | Tee-Object -FilePath $Log -Append | Out-Host
        if ($LASTEXITCODE -ne 0) {
            throw "Git pull --ff-only failed. No merge or history rewrite was attempted."
        }
    }
    else {
        Log "The current branch has no upstream. Fetch completed; automatic pull was skipped."
    }
    $afterCommit = (& $Git rev-parse HEAD 2>$null).Trim()
}

$dist = Join-Path $Root "frontend\dist\index.html"
$needsBuild = -not (Test-Path $dist) -or ($beforeCommit -and $afterCommit -and $beforeCommit -ne $afterCommit)
if ($needsBuild) {
    if (-not $Npm) { throw "npm.cmd was not found." }
    Log "Building the frontend because the build is missing or the commit changed."
    Push-Location (Join-Path $Root "frontend")
    try {
        & $Npm ci 2>&1 | Tee-Object -FilePath $Log -Append | Out-Host
        if ($LASTEXITCODE -ne 0) { throw "npm ci failed." }
        & $Npm run build 2>&1 | Tee-Object -FilePath $Log -Append | Out-Host
        if ($LASTEXITCODE -ne 0) { throw "npm run build failed." }
    }
    finally {
        Pop-Location
    }
}
else {
    Log "Existing frontend build is current."
}

$connections = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
if ($connections) {
    Log "Stopping the existing local process on port $Port."
    $connections | Select-Object -ExpandProperty OwningProcess -Unique | ForEach-Object {
        Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue
    }
}

$serverCommand = 'cd /d "' + $Root + '" && set "SINGH360_PORT=' + $Port + '" && "' + $Python + '" server.py'
Start-Process -FilePath "cmd.exe" -ArgumentList @("/k", $serverCommand)

$ready = $false
for ($i = 0; $i -lt 60; $i++) {
    try {
        $response = Invoke-WebRequest -Uri "$LocalApp/../api/health" -UseBasicParsing -TimeoutSec 3
        if ($response.StatusCode -eq 200) {
            $ready = $true
            break
        }
    }
    catch {}
    Start-Sleep -Seconds 1
}

if (-not $ready) {
    throw "The local app did not start. Log: $Log"
}

Log "Local app ready: $LocalApp"
Start-Process $LocalApp
