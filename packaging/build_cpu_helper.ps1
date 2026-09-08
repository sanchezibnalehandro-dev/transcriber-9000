param(
    [string]$LlvmMingwRoot = "",
    [string]$BuildTools = ""
)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
if (-not $BuildTools) {
    $BuildTools = Join-Path $projectRoot ".build-tools"
}
if (-not $LlvmMingwRoot) {
    $packageRoot = Join-Path $env:LOCALAPPDATA "Microsoft\WinGet\Packages"
    $LlvmMingwRoot = Get-ChildItem "$packageRoot\MartinStorsjo.LLVM-MinGW.UCRT_*\llvm-mingw-*" -Directory |
        Select-Object -First 1 -ExpandProperty FullName
}

$cargo = Join-Path $env:USERPROFILE ".cargo\bin\cargo.exe"
$cmakeBin = Join-Path $BuildTools "cmake\data\bin"
$libclang = Join-Path $BuildTools "clang\native"
$make = Join-Path $LlvmMingwRoot "bin\mingw32-make.exe"
$cc = Join-Path $LlvmMingwRoot "bin\x86_64-w64-mingw32-clang.exe"
$cxx = Join-Path $LlvmMingwRoot "bin\x86_64-w64-mingw32-clang++.exe"
$ar = Join-Path $LlvmMingwRoot "bin\x86_64-w64-mingw32-ar.exe"
foreach ($required in @($cargo, (Join-Path $cmakeBin "cmake.exe"), (Join-Path $libclang "libclang.dll"), $make, $cc, $cxx, $ar)) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) {
        throw "Missing CPU helper build dependency: $required"
    }
}

$aliasDir = Join-Path $env:LOCALAPPDATA "Transcriber9000Build\llvm-link-alias"
New-Item -ItemType Directory -Path $aliasDir -Force | Out-Null
Copy-Item -LiteralPath (Join-Path $LlvmMingwRoot "x86_64-w64-mingw32\lib\libomp.dll.a") `
    -Destination (Join-Path $aliasDir "libgomp.a") -Force

$env:PATH = "$(Join-Path $LlvmMingwRoot 'bin');$cmakeBin;$(Split-Path $cargo);$env:PATH"
$env:LIBCLANG_PATH = $libclang
$posixRoot = $LlvmMingwRoot.Replace("\", "/")
$env:BINDGEN_EXTRA_CLANG_ARGS_x86_64_pc_windows_gnullvm = "--target=x86_64-w64-windows-gnu -resource-dir=$posixRoot/lib/clang/22 -isystem$posixRoot/include"
$env:CC = $cc
$env:CXX = $cxx
$env:AR = $ar
$env:CMAKE_GENERATOR = "MinGW Makefiles"
$env:CMAKE_MAKE_PROGRAM = $make
$env:CMAKE_C_COMPILER = $cc
$env:CMAKE_CXX_COMPILER = $cxx
$env:CFLAGS = "-D_WIN32_WINNT=0x0A00"
$env:CXXFLAGS = "-D_WIN32_WINNT=0x0A00"
$env:CXXSTDLIB = "c++"
$env:CARGO_TARGET_X86_64_PC_WINDOWS_GNULLVM_LINKER = $cc
$env:RUSTFLAGS = "-C link-arg=-fuse-ld=lld -L native=$aliasDir"

$targetDir = Join-Path $projectRoot ".cache\llama-helper-cpu-gnullvm"
& $cargo build --manifest-path (Join-Path $projectRoot "llama-helper\Cargo.toml") `
    --release --target x86_64-pc-windows-gnullvm --target-dir $targetDir
if ($LASTEXITCODE -ne 0) {
    throw "CPU helper build failed with exit code $LASTEXITCODE"
}

$releaseDir = Join-Path $targetDir "x86_64-pc-windows-gnullvm\release"
foreach ($dll in @("libc++.dll", "libunwind.dll", "libomp.dll")) {
    Copy-Item -LiteralPath (Join-Path $LlvmMingwRoot "x86_64-w64-mingw32\bin\$dll") `
        -Destination (Join-Path $releaseDir $dll) -Force
}

'{"type":"ping"}' | & (Join-Path $releaseDir "llama-helper.exe")
if ($LASTEXITCODE -ne 0) {
    throw "CPU helper JSONL ping failed with exit code $LASTEXITCODE"
}
