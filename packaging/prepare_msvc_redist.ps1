param(
    [string]$RedistInstaller = "",
    [string]$Dark = "",
    [string]$Destination = ""
)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
if (-not $RedistInstaller) {
    $RedistInstaller = Join-Path $projectRoot ".release-input\vc_redist.x64.exe"
}
if (-not $Destination) {
    $Destination = Join-Path $projectRoot ".release-input\msvc-redist-x64"
}
if (-not $Dark) {
    $Dark = (Get-Command dark.exe -ErrorAction SilentlyContinue | Select-Object -First 1 -ExpandProperty Source)
}
if (-not $Dark -or -not (Test-Path -LiteralPath $Dark -PathType Leaf)) {
    throw "WiX Toolset 3 dark.exe was not found. Pass -Dark with an official WiX Toolset 3 binary."
}

$expectedInstallerSha256 = "CC0FF0EB1DC3F5188AE6300FAEF32BF5BEEBA4BDD6E8E445A9184072096B713B"
$expectedVersion = "14.44.35211.0"
$actualInstallerSha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $RedistInstaller).Hash
if ($actualInstallerSha256 -ne $expectedInstallerSha256) {
    throw "VC_redist.x64.exe is not the pinned official package: $actualInstallerSha256"
}
$installer = Get-Item -LiteralPath $RedistInstaller
if ($installer.VersionInfo.FileVersion -ne $expectedVersion) {
    throw "Unexpected VC Redistributable version: $($installer.VersionInfo.FileVersion)"
}
$signature = Get-AuthenticodeSignature -LiteralPath $RedistInstaller
if ($signature.Status -ne "Valid" -or $signature.SignerCertificate.Subject -notmatch "O=Microsoft Corporation") {
    throw "VC_redist.x64.exe does not have a valid Microsoft Authenticode signature."
}

$workingRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("transcriber-msvc-" + [guid]::NewGuid().ToString("N"))
$darkRoot = Join-Path $workingRoot "bundle"
$adminRoot = Join-Path $workingRoot "admin"
New-Item -ItemType Directory -Force -Path $darkRoot, $adminRoot, $Destination | Out-Null
try {
    & $Dark -nologo -x $darkRoot $installer.FullName
    if ($LASTEXITCODE -ne 0) {
        throw "WiX extraction failed with exit code $LASTEXITCODE"
    }
    $msi = Join-Path $darkRoot "AttachedContainer\packages\vcRuntimeMinimum_amd64\vc_runtimeMinimum_x64.msi"
    $process = Start-Process -FilePath "msiexec.exe" -ArgumentList @(
        "/a", ('"' + $msi + '"'), "/qn", ('TARGETDIR="' + $adminRoot + '"')
    ) -WindowStyle Hidden -Wait -PassThru
    if ($process.ExitCode -ne 0) {
        throw "VC Redistributable administrative extraction failed with exit code $($process.ExitCode)"
    }
    $sourceRoot = Join-Path $adminRoot "System64"
    foreach ($name in @("msvcp140.dll", "vcomp140.dll", "vcruntime140.dll", "vcruntime140_1.dll")) {
        Copy-Item -LiteralPath (Join-Path $sourceRoot $name) -Destination (Join-Path $Destination $name) -Force
    }
}
finally {
    if (Test-Path -LiteralPath $workingRoot) {
        Remove-Item -LiteralPath $workingRoot -Recurse -Force
    }
}

Write-Host "Prepared official app-local MSVC runtime: $Destination"
