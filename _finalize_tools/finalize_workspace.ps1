$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $Root
if (-not (Test-Path ".git")) { throw "This must run from the Singh360_SmartDraw repository root." }

$Stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$Archive = Join-Path $Root ".docs\archive\final_workspace_cleanup_$Stamp"
New-Item -ItemType Directory -Force $Archive | Out-Null
Set-Content -Path (Join-Path $Root ".finalizer_archive_path") -Value $Archive -Encoding UTF8

Write-Host ""
Write-Host "============================================================"
Write-Host " Singh360 final workspace cleanup + component publish"
Write-Host "============================================================"
Write-Host "Backup/archive: $Archive"
Write-Host ""

$PreservedPpt = @(Get-ChildItem $Root -File -Filter "*.pptx" -ErrorAction SilentlyContinue | Where-Object {
  $_.Name -like "Singh360_Component_Library_Real*.pptx" -or
  $_.Name -like "Singh360 Component Library Real*.pptx"
})
$PreservedPpt | ForEach-Object { Write-Host "Preserving local PowerPoint: $($_.Name)" }

$IgnorePath = Join-Path $Root ".gitignore"
$Ignore = Get-Content $IgnorePath -Raw
$Block = @"

# Local personal PowerPoint palette - keep in the working folder, never commit
Singh360_Component_Library_Real*.pptx
Singh360 Component Library Real*.pptx

# Published component catalog - intentionally committed for team access
!docs/component-library/
!docs/component-library/**
"@
if ($Ignore -notmatch "Local personal PowerPoint palette") {
  Add-Content -Path $IgnorePath -Value $Block
}

function Move-ToArchive([System.IO.FileInfo]$File, [string]$Subfolder = "root_clutter") {
  if (-not $File.Exists) { return }
  $TargetDir = Join-Path $Archive $Subfolder
  New-Item -ItemType Directory -Force $TargetDir | Out-Null
  $Target = Join-Path $TargetDir $File.Name
  $n = 1
  while (Test-Path $Target) {
    $Target = Join-Path $TargetDir ("{0}-{1}{2}" -f $File.BaseName,$n,$File.Extension)
    $n++
  }
  Move-Item -LiteralPath $File.FullName -Destination $Target -Force
  Write-Host "Archived: $($File.Name)"
}

$KeepRoot = @(
  "server.py","config.py","requirements.txt","README.md","AGENTS.md",".gitignore",
  "start-local.ps1","start-live.ps1","FINALIZE_WORKSPACE_AND_PUBLISH.bat"
)
$RootFiles = @(Get-ChildItem $Root -File -ErrorAction SilentlyContinue)
foreach ($File in $RootFiles) {
  if ($KeepRoot -contains $File.Name) { continue }
  if ($PreservedPpt.FullName -contains $File.FullName) { continue }

  $move = $false
  if ($File.Extension -in @(".bat", ".pdf", ".zip")) { $move = $true }
  elseif ($File.Extension -eq ".pptx") { $move = $true }
  elseif ($File.Extension -eq ".ps1") { $move = $true }
  elseif ($File.Extension -eq ".txt" -and $File.Name -ne "requirements.txt") { $move = $true }
  elseif ($File.Name -eq "readme") { $move = $true }
  elseif ($File.Name -like "README_*.md") { $move = $true }
  elseif ($File.Name -in @(
    "Microsoft.Services.Store.winmd","temp.py","fix_dashboard.py",
    "singh360-rebuild-hero.png","singh360-repaired-homepage-top.png"
  )) { $move = $true }

  if ($move) { Move-ToArchive $File }
}

$ScriptDir = Join-Path $Root "scripts"
if (Test-Path $ScriptDir) {
  $OneTimePattern = '^(install_|rollback_|publish_|push_|repo_cleanup|send_powerpoint_|import_powerpoint_|enable_github_|open_singh360_|clean_component_library|copy_to_singh360|first_pass)'
  Get-ChildItem $ScriptDir -File -ErrorAction SilentlyContinue | Where-Object {
    $_.Name -match $OneTimePattern -and $_.Name -notlike "smoke_*"
  } | ForEach-Object { Move-ToArchive $_ "one_time_scripts" }
}

$Py = if (Test-Path ".venv\Scripts\python.exe") { ".venv\Scripts\python.exe" } else { "python" }
& $Py "_finalize_tools\publish_component_catalog.py"
if ($LASTEXITCODE -ne 0) { throw "Component catalog publishing failed." }

& $Py -m compileall server.py core
if ($LASTEXITCODE -ne 0) { throw "Python syntax check failed." }
if (Test-Path "frontend\package.json") {
  Push-Location frontend
  npm run build
  $BuildCode = $LASTEXITCODE
  Pop-Location
  if ($BuildCode -ne 0) { throw "Frontend build failed." }
}

Write-Host ""
Write-Host "Current Git changes:"
git status --short
Write-Host ""
Write-Host "The local PowerPoint remains in place and is ignored."
Write-Host "The public catalog was generated under docs\component-library with relative links."
Write-Host ""
$Confirm = Read-Host "Type PUBLISH to commit and push these cleanup/catalog changes, or press Enter to stop"
if ($Confirm -ne "PUBLISH") {
  Write-Host "Stopped before Git commit. Files are ready for review."
  exit 0
}

git add -A
$Staged = git diff --cached --name-only
if (-not $Staged) {
  Write-Host "No Git changes to commit."
  exit 0
}

git commit -m "Clean workspace and publish component catalog"
$Branch = (git branch --show-current).Trim()
git push origin $Branch
if ($LASTEXITCODE -ne 0) { throw "Git push failed." }

Write-Host ""
Write-Host "Pushed branch: $Branch"
Write-Host "Repository catalog files now exist under docs/component-library."

try {
  $Catalog = Get-Content "docs\component-library\catalog.json" -Raw | ConvertFrom-Json
  $First = $Catalog | Select-Object -First 1
  $Rel = if ($First.real) { $First.real } else { $First.edge }
  if ($Rel) {
    Start-Sleep -Seconds 3
    $Raw = "https://raw.githubusercontent.com/dstogsdill1/Singh360_SmartDraw/$Branch/docs/component-library/$Rel"
    Write-Host "Testing: $Raw"
    $Response = Invoke-WebRequest -Uri $Raw -Method Head -UseBasicParsing -TimeoutSec 20
    Write-Host "Raw GitHub asset status: $($Response.StatusCode)"
  }
} catch {
  Write-Warning "GitHub may still be processing the push. Raw asset test: $($_.Exception.Message)"
}

Write-Host ""
Write-Host "Permanent catalog after GitHub Pages is enabled for /docs:"
Write-Host "https://dstogsdill1.github.io/Singh360_SmartDraw/component-library/"
Write-Host ""
Write-Host "DONE. Old helper clutter is backed up under:"
Write-Host $Archive
