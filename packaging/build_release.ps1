$ErrorActionPreference = "Stop"

$packaging = Split-Path -Parent $MyInvocation.MyCommand.Path
$root = Split-Path -Parent $packaging
Set-Location $root

$releaseVersion = "v1.0.0"
$releaseName = "KOLConnect_$releaseVersion"
$releaseFileName = "$releaseName.exe"
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

& python (Join-Path $root "scripts\check_sqlite_runtime.py")
if ($LASTEXITCODE -ne 0) {
  throw "SQLite runtime safety gate failed."
}

foreach ($temporaryPath in @($workPath, $distPath)) {
  if (Test-Path -LiteralPath $temporaryPath) {
    Remove-Item -LiteralPath $temporaryPath -Recurse -Force
  }
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

$builtDirectory = Join-Path $distPath $releaseName
$builtExe = Join-Path $builtDirectory $releaseFileName
if (-not (Test-Path -LiteralPath $builtExe)) {
  throw "Build did not generate the ONEDIR executable: $builtExe"
}

$release = Join-Path $root "release"
$releaseDirectory = Join-Path $release $releaseName
$releaseExe = Join-Path $releaseDirectory $releaseFileName
$releaseZip = Join-Path $release "$releaseName.zip"
$legacyOneFileExe = Join-Path $release $releaseFileName
$stagingRoot = Join-Path $release ".staging-$([guid]::NewGuid().ToString('N'))"
$stagingDirectory = Join-Path $stagingRoot $releaseName
$stagingZip = Join-Path $stagingRoot "$releaseName.zip"
New-Item -ItemType Directory -Force -Path $release | Out-Null

Copy-Item -LiteralPath $builtDirectory -Destination $stagingDirectory -Recurse

$packagedSqlite = @(Get-ChildItem -LiteralPath $stagingDirectory -Recurse -File -Filter "sqlite3.dll")
if ($packagedSqlite.Count -ne 1) {
  throw "Expected exactly one packaged sqlite3.dll; found $($packagedSqlite.Count)."
}
$vendorSqlite = Join-Path $packaging "vendor\sqlite\windows-x64\sqlite3.dll"
$vendorHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $vendorSqlite).Hash
$packagedHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $packagedSqlite[0].FullName).Hash
if ($vendorHash -ne $packagedHash) {
  throw "Packaged SQLite runtime does not match the pinned library."
}

Add-Type -AssemblyName System.IO.Compression.FileSystem
$zipCreated = $false
for ($attempt = 1; $attempt -le 5; $attempt++) {
  try {
    Remove-Item -LiteralPath $stagingZip -Force -ErrorAction SilentlyContinue
    [System.IO.Compression.ZipFile]::CreateFromDirectory(
      $stagingDirectory,
      $stagingZip,
      [System.IO.Compression.CompressionLevel]::Optimal,
      $true
    )
    $zipCreated = $true
    break
  } catch [System.IO.IOException] {
    if ($attempt -eq 5) { throw }
    Start-Sleep -Milliseconds (200 * $attempt)
  }
}
if (-not $zipCreated) {
  throw "Release ZIP creation failed."
}

$archive = [System.IO.Compression.ZipFile]::OpenRead($stagingZip)
try {
  $invalidEntries = @($archive.Entries | Where-Object {
    $normalized = $_.FullName.Replace("\", "/")
    -not $normalized.StartsWith("$releaseName/", [System.StringComparison]::Ordinal)
  })
  if ($invalidEntries.Count -ne 0) {
    throw "Release ZIP must contain exactly one top-level $releaseName folder."
  }
} finally {
  $archive.Dispose()
}

$releaseFiles = @(Get-ChildItem -LiteralPath $stagingDirectory -Recurse -File)
$directorySize = ($releaseFiles | Measure-Object -Property Length -Sum).Sum
$exeHash = (Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $stagingDirectory $releaseFileName)).Hash
$zipHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $stagingZip).Hash

if (Test-Path -LiteralPath $releaseDirectory) {
  Remove-Item -LiteralPath $releaseDirectory -Recurse -Force
}
if (Test-Path -LiteralPath $releaseZip) {
  Remove-Item -LiteralPath $releaseZip -Force
}
if (Test-Path -LiteralPath $legacyOneFileExe) {
  Remove-Item -LiteralPath $legacyOneFileExe -Force
}
Move-Item -LiteralPath $stagingDirectory -Destination $releaseDirectory
Move-Item -LiteralPath $stagingZip -Destination $releaseZip
Remove-Item -LiteralPath $stagingRoot -Force

Write-Host "RELEASE_FORMAT = ONEDIR"
Write-Host "RELEASE_DIRECTORY = $releaseDirectory"
Write-Host "RELEASE_EXE = $releaseExe"
Write-Host "RELEASE_ZIP = $releaseZip"
Write-Host "DIRECTORY_SIZE = $directorySize"
Write-Host "FILE_COUNT = $($releaseFiles.Count)"
Write-Host "EXE_SHA256 = $exeHash"
Write-Host "ZIP_SHA256 = $zipHash"
Write-Host "SQLITE_RUNTIME = 3.53.1"
