param(
    [string]$PortableRoot = "",
    [string]$Iscc = "",
    [switch]$SkipTests
)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
if (-not $PortableRoot) {
    $PortableRoot = Join-Path $projectRoot "dist\Transcriber 9000"
}
$PortableRoot = (Resolve-Path -LiteralPath $PortableRoot).Path

$requiredFiles = @(
    "Transcriber 9000.exe",
    ".cache\llama-helper-cpu\release\llama-helper.exe",
    ".cache\llama-helper-cuda\release\llama-helper.exe",
    ".cache\whisper\base.pt",
    "tools\ffmpeg\bin\ffmpeg.exe",
    "resources\report_models.json",
    "report_templates\product_meeting.json"
)
foreach ($relativePath in $requiredFiles) {
    $candidate = Join-Path $PortableRoot $relativePath
    if (-not (Test-Path -LiteralPath $candidate -PathType Leaf)) {
        throw "Portable payload is incomplete: $relativePath"
    }
}

$ggufFiles = Get-ChildItem -LiteralPath $PortableRoot -Recurse -File -Filter "*.gguf"
if ($ggufFiles) {
    throw "Portable payload must not contain GGUF: $($ggufFiles[0].FullName)"
}
$junctions = Get-ChildItem -LiteralPath $PortableRoot -Recurse -Force |
    Where-Object { $_.LinkType -eq "Junction" }
if ($junctions) {
    throw "Portable payload contains a junction: $($junctions[0].FullName)"
}

if (-not $Iscc) {
    $isccCandidates = @(
        (Join-Path $env:LOCALAPPDATA "Programs\Inno Setup 6\ISCC.exe"),
        (Join-Path ${env:ProgramFiles(x86)} "Inno Setup 6\ISCC.exe"),
        (Join-Path $env:ProgramFiles "Inno Setup 6\ISCC.exe")
    )
    $Iscc = $isccCandidates | Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } |
        Select-Object -First 1
}
if (-not $Iscc -or -not (Test-Path -LiteralPath $Iscc -PathType Leaf)) {
    throw "Inno Setup 6 compiler (ISCC.exe) was not found. Install Inno Setup 6 or pass -Iscc."
}

if (-not $SkipTests) {
    $python = Join-Path $projectRoot ".venv\Scripts\python.exe"
    if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
        throw "Test interpreter was not found: $python"
    }
    & $python -m unittest tests.test_installer_packaging
    if ($LASTEXITCODE -ne 0) {
        throw "Installer packaging tests failed with exit code $LASTEXITCODE"
    }
}

$expectedRoot = (Join-Path $projectRoot "dist\Transcriber 9000")
if ($PortableRoot -ne $expectedRoot) {
    throw "The RC installer script currently accepts only the proven portable root: $expectedRoot"
}

& $Iscc "/Qp" (Join-Path $PSScriptRoot "transcriber9000.iss")
if ($LASTEXITCODE -ne 0) {
    throw "Inno Setup failed with exit code $LASTEXITCODE"
}

$setup = Join-Path $projectRoot "dist\installer\Transcriber 9000 Setup.exe"
if (-not (Test-Path -LiteralPath $setup -PathType Leaf)) {
    throw "Expected installer was not produced: $setup"
}
$setupFile = Get-Item -LiteralPath $setup
Write-Host "Installer ready: $($setupFile.FullName)"
Write-Host "Installer bytes: $($setupFile.Length)"

