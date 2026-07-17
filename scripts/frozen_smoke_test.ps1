param(
    [Parameter(Mandatory = $true)]
    [string]$BundleRoot,
    [string]$ResultPath = ""
)

$ErrorActionPreference = "Stop"
$bundle = (Resolve-Path -LiteralPath $BundleRoot).Path
$executable = Join-Path $bundle "JoinHelper.exe"
if (-not (Test-Path -LiteralPath $executable)) {
    throw "JoinHelper.exe was not found in $bundle"
}

if (-not $ResultPath) {
    $ResultPath = Join-Path ([System.IO.Path]::GetTempPath()) "join-helper-smoke-result.json"
}
$result = [System.IO.Path]::GetFullPath($ResultPath)
if (Test-Path -LiteralPath $result) {
    Remove-Item -LiteralPath $result -Force
}

$quotedResult = '"' + $result + '"'
$process = Start-Process -FilePath $executable -ArgumentList @("--smoke-test", $quotedResult) -PassThru -Wait
if ($process.ExitCode -ne 0) {
    throw "Frozen smoke test exited with code $($process.ExitCode)"
}
if (-not (Test-Path -LiteralPath $result)) {
    throw "Frozen smoke test did not write $result"
}

$payload = Get-Content -LiteralPath $result -Raw -Encoding UTF8 | ConvertFrom-Json
if ($payload.status -ne "SMOKE_TEST_OK") {
    throw "Frozen smoke test result was $($payload.status)"
}
if (-not $payload.vision_match -or -not $payload.ocr_keyword_match) {
    throw "Frozen smoke test did not exercise vision and OCR successfully"
}

Write-Output "SMOKE_TEST_OK"
Write-Output "Result=$result"
