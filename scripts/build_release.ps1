param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern("^[0-9]+\.[0-9]+\.[0-9]+(?:-[0-9A-Za-z.-]+)?$")]
    [string]$Version,
    [string]$PythonExe = "python",
    [string]$OutputRoot = "",
    [switch]$SkipBootstrap
)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
if (-not $OutputRoot) {
    $OutputRoot = Join-Path $repoRoot "release"
}
$output = [System.IO.Path]::GetFullPath($OutputRoot)
$buildRoot = Join-Path $output ".build-v$Version"
$distRoot = Join-Path $buildRoot "dist"
$workRoot = Join-Path $buildRoot "work"
$stagingRoot = Join-Path $buildRoot "staging"
$bundleRoot = Join-Path $stagingRoot "JoinHelper"
$zipName = "JoinHelper-Portable-v$Version.zip"
$zipPath = Join-Path $output $zipName

New-Item -ItemType Directory -Path $output -Force | Out-Null
if (Test-Path -LiteralPath $buildRoot) {
    throw "Build directory already exists: $buildRoot"
}
if (Test-Path -LiteralPath $zipPath) {
    throw "Release archive already exists: $zipPath"
}
New-Item -ItemType Directory -Path $buildRoot -Force | Out-Null

if ($SkipBootstrap) {
    $buildPython = $PythonExe
} else {
    $venvRoot = Join-Path $buildRoot "venv"
    & $PythonExe -m venv $venvRoot
    if ($LASTEXITCODE -ne 0) { throw "Could not create build environment" }
    $buildPython = Join-Path $venvRoot "Scripts\python.exe"
    & $buildPython -m pip install --disable-pip-version-check -r (Join-Path $repoRoot "requirements.txt") -r (Join-Path $repoRoot "requirements-dev.txt")
    if ($LASTEXITCODE -ne 0) { throw "Could not install build dependencies" }
}

& $buildPython -m unittest discover -s (Join-Path $repoRoot "tests") -v
if ($LASTEXITCODE -ne 0) { throw "Unit tests failed" }

& $buildPython -m PyInstaller --clean --noconfirm --distpath $distRoot --workpath $workRoot (Join-Path $repoRoot "JoinHelper.spec")
if ($LASTEXITCODE -ne 0) { throw "PyInstaller build failed" }

$builtBundle = Join-Path $distRoot "JoinHelper"
if (-not (Test-Path -LiteralPath (Join-Path $builtBundle "JoinHelper.exe"))) {
    throw "PyInstaller output is incomplete"
}
New-Item -ItemType Directory -Path $bundleRoot -Force | Out-Null
Copy-Item -Path (Join-Path $builtBundle "*") -Destination $bundleRoot -Recurse -Force
Copy-Item -LiteralPath (Join-Path $repoRoot "portable.marker") -Destination $bundleRoot -Force
Copy-Item -LiteralPath (Join-Path $repoRoot "config.example.json") -Destination (Join-Path $bundleRoot "config.example.json") -Force
Copy-Item -LiteralPath (Join-Path $repoRoot "LICENSE") -Destination (Join-Path $bundleRoot "LICENSE.txt") -Force
Copy-Item -LiteralPath (Join-Path $repoRoot "templates") -Destination (Join-Path $bundleRoot "templates") -Recurse -Force
Copy-Item -LiteralPath (Join-Path $repoRoot "assets") -Destination (Join-Path $bundleRoot "assets") -Recurse -Force

$dataRoot = Join-Path $bundleRoot "data"
New-Item -ItemType Directory -Path $dataRoot -Force | Out-Null
Copy-Item -LiteralPath (Join-Path $repoRoot "config.example.json") -Destination (Join-Path $dataRoot "config.json") -Force

$smokeResult = Join-Path $buildRoot "frozen-smoke-result.json"
& (Join-Path $PSScriptRoot "frozen_smoke_test.ps1") -BundleRoot $bundleRoot -ResultPath $smokeResult

Compress-Archive -LiteralPath $bundleRoot -DestinationPath $zipPath -CompressionLevel Optimal
$hash = (Get-FileHash -LiteralPath $zipPath -Algorithm SHA256).Hash.ToLowerInvariant()
$checksumPath = "$zipPath.sha256"
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText($checksumPath, "$hash  $zipName`n", $utf8NoBom)

Write-Output "Portable=$zipPath"
Write-Output "Checksum=$checksumPath"
Write-Output "Bundle=$bundleRoot"
