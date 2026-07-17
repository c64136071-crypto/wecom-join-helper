param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern("^[0-9]+\.[0-9]+\.[0-9]+(?:-[0-9A-Za-z.-]+)?$")]
    [string]$Version,
    [Parameter(Mandatory = $true)]
    [string]$BundleRoot,
    [Parameter(Mandatory = $true)]
    [string]$OutputRoot,
    [string]$IsccPath = ""
)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$bundle = (Resolve-Path -LiteralPath $BundleRoot).Path
$output = [System.IO.Path]::GetFullPath($OutputRoot)
$source = Join-Path $output ".installer-source-v$Version"
$expectedName = "JoinHelper-Setup-v$Version.exe"
$expectedPath = Join-Path $output $expectedName

if (-not $IsccPath) {
    $candidates = @(
        (Join-Path ${env:ProgramFiles(x86)} "Inno Setup 6\ISCC.exe"),
        (Join-Path $env:ProgramFiles "Inno Setup 6\ISCC.exe"),
        (Join-Path $env:LOCALAPPDATA "Programs\Inno Setup 6\ISCC.exe")
    )
    $IsccPath = $candidates | Where-Object { $_ -and (Test-Path -LiteralPath $_) } | Select-Object -First 1
}
if (-not $IsccPath -or -not (Test-Path -LiteralPath $IsccPath)) {
    throw "ISCC.exe was not found"
}
if (-not (Test-Path -LiteralPath (Join-Path $bundle "JoinHelper.exe"))) {
    throw "Portable bundle is incomplete: $bundle"
}
if (Test-Path -LiteralPath $source) {
    throw "Installer source already exists: $source"
}
if (Test-Path -LiteralPath $expectedPath) {
    throw "Installer already exists: $expectedPath"
}

New-Item -ItemType Directory -Path $source -Force | Out-Null
Get-ChildItem -LiteralPath $bundle -Force |
    Where-Object { $_.Name -notin @("portable.marker", "data") } |
    ForEach-Object { Copy-Item -LiteralPath $_.FullName -Destination $source -Recurse -Force }

$scriptPath = Join-Path $repoRoot "installer\JoinHelper.iss"
& $IsccPath "/DMyAppVersion=$Version" "/DSourceDir=$source" "/DOutputDir=$output" $scriptPath
if ($LASTEXITCODE -ne 0) { throw "Inno Setup compilation failed" }
if (-not (Test-Path -LiteralPath $expectedPath)) { throw "Installer output is missing" }

$hash = (Get-FileHash -LiteralPath $expectedPath -Algorithm SHA256).Hash.ToLowerInvariant()
$checksumPath = "$expectedPath.sha256"
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText($checksumPath, "$hash  $expectedName`n", $utf8NoBom)

Write-Output "Installer=$expectedPath"
Write-Output "Checksum=$checksumPath"
Write-Output "InstallerSource=$source"
