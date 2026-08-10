param(
    [Parameter(Mandatory=$true)][string]$DataDir,
    [Parameter(Mandatory=$true)][string]$XEditExe,
    [string]$PythonExe = "python",
    [string]$RepoRoot = "",
    [string]$OutDir = ""
)

$ErrorActionPreference = "Stop"

if (-not $RepoRoot) {
    $RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
}
if (-not $OutDir) {
    $OutDir = Join-Path $RepoRoot "results\janus_bear_v4_3"
}

$DataDir = (Resolve-Path $DataDir).Path
$XEditExe = (Resolve-Path $XEditExe).Path
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null

$Masters = @(
    "Fallout3.esm",
    "Anchorage.esm",
    "ThePitt.esm",
    "BrokenSteel.esm",
    "PointLookout.esm",
    "Zeta.esm"
)

Write-Host "[JANUS v4.3] Verifying required master filenames..."
foreach ($m in $Masters) {
    $p = Join-Path $DataDir $m
    if (-not (Test-Path -LiteralPath $p -PathType Leaf)) {
        throw "Missing required master: $p"
    }
}

$XEditDir = Split-Path -Parent $XEditExe
$EditScriptsDir = Join-Path $XEditDir "Edit Scripts"
New-Item -ItemType Directory -Force -Path $EditScriptsDir | Out-Null

$ExporterSource = Join-Path $RepoRoot "tools\fo3edit_janus_bear_effective_refr_export_v4_3.pas"
$ExporterDest = Join-Path $EditScriptsDir "fo3edit_janus_bear_effective_refr_export_v4_3.pas"
Copy-Item -LiteralPath $ExporterSource -Destination $ExporterDest -Force

$XEditInventory = Join-Path $EditScriptsDir "JANUS-Bear-Effective-REFR-v4.3.tsv"
if (Test-Path -LiteralPath $XEditInventory) {
    Remove-Item -LiteralPath $XEditInventory -Force
}

Write-Host "[JANUS v4.3] Launching xEdit in Fallout 3 mode with exactly six requested masters..."
$QuickEdit = '-quickedit:"' + ($Masters -join ' ') + '"'
$ScriptArg = '-script:"fo3edit_janus_bear_effective_refr_export_v4_3.pas"'
$Arguments = @(
    "-FO3",
    "-autoload",
    "-nobuildrefs",
    $QuickEdit,
    $ScriptArg
)

$proc = Start-Process -FilePath $XEditExe -ArgumentList $Arguments -Wait -PassThru
if ($proc.ExitCode -ne 0) {
    throw "xEdit exited with code $($proc.ExitCode)"
}
if (-not (Test-Path -LiteralPath $XEditInventory -PathType Leaf)) {
    throw "xEdit completed but the v4.3 inventory was not created. Check the xEdit Messages tab/log for an admission BLOCKED message."
}

$Inventory = Join-Path $OutDir "JANUS-Bear-Effective-REFR-v4.3.tsv"
Copy-Item -LiteralPath $XEditInventory -Destination $Inventory -Force

$Acquisition = Join-Path $OutDir "JANUS-Bear-Acquisition-v4.3.json"
$EnabledInventory = Join-Path $OutDir "JANUS-Bear-Effective-REFR-v4.3-enabled-only.tsv"
$AnalysisAll = Join-Path $OutDir "JANUS-Bear-Spatial-v4.3-all-effective.json"
$AnalysisEnabled = Join-Path $OutDir "JANUS-Bear-Spatial-v4.3-enabled-only.json"
$Final = Join-Path $OutDir "JANUS-BEAR-REAL-ESM-SPATIAL-RESULT-v4.3.json"

Write-Host "[JANUS v4.3] Hash-binding master bytes and admitting effective REFR inventory..."
& $PythonExe (Join-Path $RepoRoot "tools\verify_janus_bear_v4_3_acquisition.py") `
    --master-dir $DataDir `
    --inventory $Inventory `
    --out $Acquisition `
    --enabled-only-out $EnabledInventory
if ($LASTEXITCODE -ne 0) {
    throw "v4.3 acquisition verifier BLOCKED the dataset."
}

Write-Host "[JANUS v4.3] Running v4.2 statistical core on all effective non-deleted REFRs..."
& $PythonExe (Join-Path $RepoRoot "tools\analyze_teddy_gnome_enrichment_v4_2.py") `
    --tsv $Inventory `
    --out $AnalysisAll `
    --pretty
if ($LASTEXITCODE -ne 0) { throw "v4.2 all-effective analysis failed." }

Write-Host "[JANUS v4.3] Running initially-enabled-only sensitivity analysis..."
& $PythonExe (Join-Path $RepoRoot "tools\analyze_teddy_gnome_enrichment_v4_2.py") `
    --tsv $EnabledInventory `
    --out $AnalysisEnabled `
    --pretty
if ($LASTEXITCODE -ne 0) { throw "v4.2 enabled-only analysis failed." }

Write-Host "[JANUS v4.3] Finalizing hash-bound real-result receipt..."
& $PythonExe (Join-Path $RepoRoot "tools\finalize_janus_bear_v4_3_result.py") `
    --acquisition $Acquisition `
    --all-analysis $AnalysisAll `
    --enabled-analysis $AnalysisEnabled `
    --out $Final
if ($LASTEXITCODE -ne 0) { throw "v4.3 finalization failed." }

Write-Host ""
Write-Host "JANUS Bear v4.3 COMPLETE"
Write-Host "Inventory: $Inventory"
Write-Host "Acquisition receipt: $Acquisition"
Write-Host "All-effective analysis: $AnalysisAll"
Write-Host "Enabled-only analysis: $AnalysisEnabled"
Write-Host "Final result: $Final"
Write-Host ""
Write-Host "Do not publish the raw master files. The final JSON contains hashes and aggregate/statistical evidence only."
