param(
    [Parameter(Mandatory = $true)]
    [string]$SetupPath,
    [Parameter(Mandatory = $true)]
    [string]$InstallRoot,
    [Parameter(Mandatory = $true)]
    [string]$ResultPath
)

$ErrorActionPreference = "Stop"
$setup = (Resolve-Path -LiteralPath $SetupPath).Path
$install = [System.IO.Path]::GetFullPath($InstallRoot)
if (Test-Path -LiteralPath $install) {
    throw "Installer smoke destination already exists: $install"
}

$quotedInstall = '"' + $install + '"'
$arguments = @(
    "/VERYSILENT",
    "/SUPPRESSMSGBOXES",
    "/NORESTART",
    "/MERGETASKS=!desktopicon",
    "/DIR=$quotedInstall"
)
$installProcess = Start-Process -FilePath $setup -ArgumentList $arguments -PassThru -Wait
if ($installProcess.ExitCode -ne 0) {
    throw "Installer exited with code $($installProcess.ExitCode)"
}

$executable = Join-Path $install "JoinHelper.exe"
if (-not (Test-Path -LiteralPath $executable)) {
    throw "Installed executable was not found"
}
if (Test-Path -LiteralPath (Join-Path $install "portable.marker")) {
    throw "Installed build incorrectly contains portable.marker"
}

& (Join-Path $PSScriptRoot "frozen_smoke_test.ps1") -BundleRoot $install -ResultPath $ResultPath

$uninstaller = Join-Path $install "unins000.exe"
if (-not (Test-Path -LiteralPath $uninstaller)) {
    throw "unins000.exe was not found"
}
$uninstallProcess = Start-Process -FilePath $uninstaller -ArgumentList @("/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART") -PassThru -Wait
if ($uninstallProcess.ExitCode -ne 0) {
    throw "Uninstaller exited with code $($uninstallProcess.ExitCode)"
}
Start-Sleep -Seconds 1
if (Test-Path -LiteralPath $executable) {
    throw "Installed program files remain after uninstall"
}

Write-Output "INSTALLER_SMOKE_TEST_OK"
