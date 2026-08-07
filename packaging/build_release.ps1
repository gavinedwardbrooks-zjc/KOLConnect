$ErrorActionPreference = "Stop"

$packaging = Split-Path -Parent $MyInvocation.MyCommand.Path
$root = Split-Path -Parent $packaging
Set-Location $root

$releaseVersion = "v0.2.0"
$releaseFileName = "KOLConnect_$releaseVersion.exe"
$workPath = Join-Path $packaging ".pyinstaller-build"
$distPath = Join-Path $packaging ".pyinstaller-dist"
$specFile = Join-Path $packaging "spec\KOLConnect.spec"
$iconPath = Join-Path $root "assets\KOLConnect.ico"

if (-not (Test-Path -LiteralPath $iconPath)) {
  throw "Application icon is missing: $iconPath"
}
if (-not (Test-Path -LiteralPath $specFile)) {
  throw "PyInstaller spec is missing: $specFile"
}

$pyInstallerArgs = @(
  "-m", "PyInstaller", "--noconfirm", "--clean",
  "--workpath", $workPath,
  "--distpath", $distPath,
  $specFile
)
& python @pyInstallerArgs
if ($LASTEXITCODE -ne 0) {
  throw "PyInstaller build failed."
}

$builtExe = Join-Path $distPath "KOLConnect.exe"
if (-not (Test-Path -LiteralPath $builtExe)) {
  throw "Build did not generate KOLConnect.exe; release copy stopped."
}

$release = Join-Path $root "release"
$releaseExe = Join-Path $release $releaseFileName
New-Item -ItemType Directory -Force -Path $release | Out-Null
Copy-Item $builtExe $releaseExe -Force
Write-Host "Built: $releaseExe"
