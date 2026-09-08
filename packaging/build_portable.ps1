param(
    [string]$Python = "",
    [string]$CpuHelperDirectory = "",
    [string]$CudaHelper = "",
    [string]$CudaBin = "C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.4\bin",
    [string]$MsvcRedistDirectory = "",
    [string]$Ffmpeg = ""
)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
if (-not $Python) {
    $Python = Join-Path $projectRoot ".venv\Scripts\python.exe"
}
if (-not $CpuHelperDirectory) {
    $CpuHelperDirectory = Join-Path $projectRoot ".cache\llama-helper-cpu-gnullvm\x86_64-pc-windows-gnullvm\release"
}
if (-not $CudaHelper) {
    $CudaHelper = Join-Path $projectRoot ".release-input\llama-helper-cuda-sm86.exe"
}
if (-not $MsvcRedistDirectory) {
    $MsvcRedistDirectory = Join-Path $projectRoot ".release-input\msvc-redist-x64"
}
if (-not $Ffmpeg) {
    $Ffmpeg = Join-Path $projectRoot ".release-input\ffmpeg-n8.1.2-51-g7ba069f4f1-win64-lgpl-8.1\ffmpeg-n8.1.2-51-g7ba069f4f1-win64-lgpl-8.1\bin\ffmpeg.exe"
}

$expectedCudaHelperSha256 = "0E985621C2F90636728D28C45C55129C4E017BB09F0CFA0293C627147F2A32FF"
$actualCudaHelperSha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $CudaHelper).Hash
if ($actualCudaHelperSha256 -ne $expectedCudaHelperSha256) {
    throw "CUDA helper does not match the RTX 3060 acceptance artifact: $actualCudaHelperSha256"
}

$expectedFfmpegSha256 = "931223B06750580BB8DF494AD10F074D8390F76EF3E1C25E1CEC97135AA6C3FC"
$actualFfmpegSha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $Ffmpeg).Hash
if ($actualFfmpegSha256 -ne $expectedFfmpegSha256) {
    throw "FFmpeg does not match the pinned BtbN win64-lgpl artifact: $actualFfmpegSha256"
}
$ffmpegVersion = (& $Ffmpeg -version 2>&1 | Out-String)
if ($LASTEXITCODE -ne 0) {
    throw "Pinned FFmpeg failed its version check"
}
if ($ffmpegVersion -notmatch "ffmpeg version n8\.1\.2-51-g7ba069f4f1-20260907") {
    throw "Pinned FFmpeg reports an unexpected version"
}
if ($ffmpegVersion -match "--enable-gpl" -or $ffmpegVersion -match "--enable-nonfree") {
    throw "Pinned FFmpeg must not enable GPL or nonfree configuration"
}

$stageRoot = Join-Path $projectRoot ".release-staging"
if (Test-Path -LiteralPath $stageRoot) {
    $resolvedStage = (Resolve-Path -LiteralPath $stageRoot).Path
    if ($resolvedStage -ne (Join-Path $projectRoot ".release-staging")) {
        throw "Refusing to clear unexpected staging path: $resolvedStage"
    }
    Remove-Item -LiteralPath $resolvedStage -Recurse -Force
}

$cpuStage = Join-Path $stageRoot ".cache\llama-helper-cpu\release"
$cudaStage = Join-Path $stageRoot ".cache\llama-helper-cuda\release"
$whisperStage = Join-Path $stageRoot ".cache\whisper"
$ffmpegStage = Join-Path $stageRoot "tools\ffmpeg\bin"
foreach ($directory in @($cpuStage, $cudaStage, $whisperStage, $ffmpegStage)) {
    New-Item -ItemType Directory -Path $directory -Force | Out-Null
}

foreach ($name in @("llama-helper.exe", "libc++.dll", "libunwind.dll", "libomp.dll")) {
    Copy-Item -LiteralPath (Join-Path $CpuHelperDirectory $name) -Destination (Join-Path $cpuStage $name)
}
Copy-Item -LiteralPath $CudaHelper -Destination (Join-Path $cudaStage "llama-helper.exe")
foreach ($name in @("cudart64_12.dll", "cublas64_12.dll", "cublasLt64_12.dll")) {
    Copy-Item -LiteralPath (Join-Path $CudaBin $name) -Destination (Join-Path $cudaStage $name)
}
$expectedMsvcFiles = @{
    "msvcp140.dll" = "0F885B509A685D2BBFA652FED26B5FB31D88FBDAB0A978C641D1C7B8AA460AA9"
    "vcomp140.dll" = "55ABA23CDCD6484FBB06F4155B8CA75ADFCE7A881F10AFD0C49457165E677164"
    "vcruntime140.dll" = "D5E4D9A3E835FA679450145D6A7D94E36573A509317111904D9B3712C30D9066"
    "vcruntime140_1.dll" = "1F2D41C4AA5DB0BC33EBF7B66D72943A817D7CE6CBE880502A9403823633093F"
}
foreach ($entry in $expectedMsvcFiles.GetEnumerator()) {
    $source = Join-Path $MsvcRedistDirectory $entry.Key
    if (-not (Test-Path -LiteralPath $source -PathType Leaf)) {
        throw "Missing prepared Microsoft VC Redistributable file: $source"
    }
    $actualHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $source).Hash
    if ($actualHash -ne $entry.Value) {
        throw "Microsoft VC Redistributable file does not match the pinned official package: $($entry.Key) $actualHash"
    }
    Copy-Item -LiteralPath $source -Destination (Join-Path $cudaStage $entry.Key)
}
if (Test-Path -LiteralPath (Join-Path $cudaStage "nvcuda.dll")) {
    throw "nvcuda.dll must be supplied by the NVIDIA driver, not bundled"
}

Copy-Item -LiteralPath (Join-Path $projectRoot ".cache\whisper\base.pt") -Destination (Join-Path $whisperStage "base.pt")
Copy-Item -LiteralPath $Ffmpeg -Destination (Join-Path $ffmpegStage "ffmpeg.exe")

$env:PYTHONPATH = Join-Path $projectRoot ".build-tools"
& $Python -m PyInstaller --noconfirm --clean (Join-Path $PSScriptRoot "transcriber9000.spec")
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller failed with exit code $LASTEXITCODE"
}

$portableRoot = Join-Path $projectRoot "dist\Transcriber 9000"
foreach ($name in $expectedMsvcFiles.Keys) {
    Copy-Item -LiteralPath (Join-Path $MsvcRedistDirectory $name) `
        -Destination (Join-Path $portableRoot $name) -Force
}
foreach ($directory in @("input", "output", ".cache\transcriber\runs")) {
    New-Item -ItemType Directory -Path (Join-Path $portableRoot $directory) -Force | Out-Null
}

$junctions = Get-ChildItem -LiteralPath $portableRoot -Recurse -Force |
    Where-Object { $_.LinkType -eq "Junction" }
if ($junctions) {
    throw "Portable payload contains a junction: $($junctions[0].FullName)"
}

Write-Host "Portable build ready: $portableRoot"
