param(
    [string]$Python = "",
    [string]$CpuHelperDirectory = "",
    [string]$CudaHelper = "",
    [string]$CudaBin = "C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.4\bin"
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

$expectedCudaHelperSha256 = "0E985621C2F90636728D28C45C55129C4E017BB09F0CFA0293C627147F2A32FF"
$actualCudaHelperSha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $CudaHelper).Hash
if ($actualCudaHelperSha256 -ne $expectedCudaHelperSha256) {
    throw "CUDA helper does not match the RTX 3060 acceptance artifact: $actualCudaHelperSha256"
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
foreach ($name in @("msvcp140.dll", "vcomp140.dll", "vcruntime140.dll", "vcruntime140_1.dll")) {
    Copy-Item -LiteralPath (Join-Path $env:WINDIR "System32\$name") -Destination (Join-Path $cudaStage $name)
}
if (Test-Path -LiteralPath (Join-Path $cudaStage "nvcuda.dll")) {
    throw "nvcuda.dll must be supplied by the NVIDIA driver, not bundled"
}

Copy-Item -LiteralPath (Join-Path $projectRoot ".cache\whisper\base.pt") -Destination (Join-Path $whisperStage "base.pt")
Copy-Item -LiteralPath (Join-Path $projectRoot "tools\ffmpeg\bin\ffmpeg.exe") -Destination (Join-Path $ffmpegStage "ffmpeg.exe")

$env:PYTHONPATH = Join-Path $projectRoot ".build-tools"
& $Python -m PyInstaller --noconfirm --clean (Join-Path $PSScriptRoot "transcriber9000.spec")
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller failed with exit code $LASTEXITCODE"
}

$portableRoot = Join-Path $projectRoot "dist\Transcriber 9000"
foreach ($directory in @("input", "output", ".cache\transcriber\runs")) {
    New-Item -ItemType Directory -Path (Join-Path $portableRoot $directory) -Force | Out-Null
}

$junctions = Get-ChildItem -LiteralPath $portableRoot -Recurse -Force |
    Where-Object { $_.LinkType -eq "Junction" }
if ($junctions) {
    throw "Portable payload contains a junction: $($junctions[0].FullName)"
}

Write-Host "Portable build ready: $portableRoot"
