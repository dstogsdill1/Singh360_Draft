param(
  [ValidateSet('Selection','Slides')][string]$Mode = 'Selection',
  [string]$OutputDir = '',
  [string]$PresentationPath = '',
  [string]$SlideNumbers = 'ALL'
)

$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Windows.Forms
if (-not $OutputDir) {
  $OutputDir = Join-Path $env:TEMP ("Singh360_PowerPoint_" + (Get-Date -Format 'yyyyMMdd-HHmmss'))
}
New-Item -ItemType Directory -Force $OutputDir | Out-Null

function Get-ActivePowerPoint {
  try { return [Runtime.InteropServices.Marshal]::GetActiveObject('PowerPoint.Application') }
  catch { return New-Object -ComObject PowerPoint.Application }
}

function Safe-Text($shape) {
  try {
    if ($shape.HasTextFrame -eq -1 -and $shape.TextFrame.HasText -eq -1) {
      return [string]$shape.TextFrame.TextRange.Text
    }
  } catch {}
  return ''
}

function Get-SlideTitle($slide) {
  try {
    if ($slide.Shapes.HasTitle -eq -1) { return [string]$slide.Shapes.Title.TextFrame.TextRange.Text }
  } catch {}
  return "PowerPoint Slide $($slide.SlideIndex)"
}

function Export-ShapeRecord($shape, [int]$slideIndex, [string]$folder) {
  $record = [ordered]@{
    id = [guid]::NewGuid().ToString('N').Substring(0,16)
    slideIndex = $slideIndex
    name = [string]$shape.Name
    kind = 'image'
    leftPt = [double]$shape.Left
    topPt = [double]$shape.Top
    widthPt = [double]$shape.Width
    heightPt = [double]$shape.Height
    rotation = [double]$shape.Rotation
    text = (Safe-Text $shape)
    image = ''
  }
  $safe = (($shape.Name -replace '[^A-Za-z0-9._-]+','_').Trim('_'))
  if (-not $safe) { $safe = 'shape' }
  $file = Join-Path $folder ("slide_{0:000}_shape_{1}_{2}.png" -f $slideIndex, $shape.ZOrderPosition, $safe)
  try {
    # ppShapeFormatPNG = 2. Export preserves cropping/rotation/transparency.
    $shape.Export($file, 2)
    if (Test-Path $file) { $record.image = [IO.Path]::GetFileName($file) }
  } catch {
    $record.kind = 'text'
  }
  if (-not $record.image -and $record.text) { $record.kind = 'text' }
  return [pscustomobject]$record
}

$ppt = Get-ActivePowerPoint
$ppt.Visible = -1
$openedHere = $false
$presentation = $null
$slides = @()

if ($Mode -eq 'Selection') {
  if (-not $ppt.ActivePresentation) { throw 'Open a PowerPoint presentation first.' }
  $presentation = $ppt.ActivePresentation
  $selection = $ppt.ActiveWindow.Selection
  # ppSelectionShapes=2, ppSelectionText=3, ppSelectionSlides=1
  if ($selection.Type -eq 2) {
    $slide = $ppt.ActiveWindow.View.Slide
    $slides = @([pscustomobject]@{ Slide=$slide; Shapes=@($selection.ShapeRange) })
  } elseif ($selection.Type -eq 3) {
    $slide = $ppt.ActiveWindow.View.Slide
    try { $shape = $selection.ShapeRange.Item(1) } catch { throw 'Select one or more complete objects, not only text inside an object.' }
    $slides = @([pscustomobject]@{ Slide=$slide; Shapes=@($shape) })
  } elseif ($selection.Type -eq 1) {
    foreach ($rangeSlide in @($selection.SlideRange)) {
      $slides += [pscustomobject]@{ Slide=$rangeSlide; Shapes=@($rangeSlide.Shapes) }
    }
  } else {
    throw 'Select one or more PowerPoint objects or slides first.'
  }
} else {
  if (-not $PresentationPath) {
    $dlg = New-Object System.Windows.Forms.OpenFileDialog
    $dlg.Filter = 'PowerPoint (*.pptx;*.pptm)|*.pptx;*.pptm'
    $dlg.Title = 'Choose PowerPoint deck to import into Singh360'
    if ($dlg.ShowDialog() -ne [System.Windows.Forms.DialogResult]::OK) { throw 'Cancelled.' }
    $PresentationPath = $dlg.FileName
  }
  $presentation = $ppt.Presentations.Open($PresentationPath, -1, 0, 0)
  $openedHere = $true
  $wanted = @()
  if ($SlideNumbers -and $SlideNumbers.ToUpperInvariant() -ne 'ALL') {
    foreach ($part in ($SlideNumbers -split '[,; ]+')) {
      if ($part -match '^\d+$') { $wanted += [int]$part }
    }
  }
  foreach ($slide in @($presentation.Slides)) {
    if ($wanted.Count -eq 0 -or $wanted -contains [int]$slide.SlideIndex) {
      $slides += [pscustomobject]@{ Slide=$slide; Shapes=@($slide.Shapes) }
    }
  }
}

$manifest = [ordered]@{
  version = 1
  mode = $Mode.ToLowerInvariant()
  presentation = [string]$presentation.Name
  sourcePath = [string]$presentation.FullName
  slideWidthPt = [double]$presentation.PageSetup.SlideWidth
  slideHeightPt = [double]$presentation.PageSetup.SlideHeight
  exportedAt = (Get-Date).ToString('s')
  slides = @()
}

foreach ($entry in $slides) {
  $slide = $entry.Slide
  $slideRecord = [ordered]@{
    slideIndex = [int]$slide.SlideIndex
    title = (Get-SlideTitle $slide)
    objects = @()
  }
  foreach ($shape in $entry.Shapes) {
    try { $slideRecord.objects += Export-ShapeRecord $shape ([int]$slide.SlideIndex) $OutputDir }
    catch { Write-Warning "Could not export $($shape.Name): $($_.Exception.Message)" }
  }
  $manifest.slides += [pscustomobject]$slideRecord
}

$manifestPath = Join-Path $OutputDir 'manifest.json'
$manifest | ConvertTo-Json -Depth 8 | Set-Content -Encoding UTF8 $manifestPath
if ($openedHere) { $presentation.Close() }
Write-Host $manifestPath
