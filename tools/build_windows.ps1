<#
.SYNOPSIS
Build and verify the Windows x64 single-file release using a chosen Python.
.EXAMPLE
pwsh -File tools/build_windows.ps1 -Python .venv-build/Scripts/python.exe
# Install first: <python> -m pip install -r requirements-build.txt
#>
[CmdletBinding()]
param(
    [string]$Python = "python",
    [string]$TestTempDirectory = ""
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
$root = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$distDir = Join-Path $root "dist"
$name = "F1-Team-Radio-Studio-v1.0.1-windows-x64"
$exe = Join-Path $distDir "$name.exe"
$report = Join-Path $distDir "self-test-report.json"
$licenseZip = Join-Path $distDir "F1-Team-Radio-Studio-v1.0.1-licenses.zip"

Push-Location -LiteralPath $root
try {
    # Resolve the chosen interpreter before changing any build output.
    $preflight = @'
import platform, struct, sys
from teamradio import __version__
assert sys.platform == 'win32' and struct.calcsize('P') == 8 and platform.machine().upper() in ('AMD64', 'X86_64'), 'Windows x64 Python is required'
assert sys.version_info[:2] == (3, 13), 'Python 3.13 is required'
assert __version__ == '1.0.1', 'Update release names and version resources before changing the application version'
print(sys.executable)
'@
    $pythonPath = & $Python -c $preflight
    if ($LASTEXITCODE -ne 0) { throw "Python environment preflight failed." }
    $Python = ([string]$pythonPath).Trim()
    foreach ($inputPath in @("assets", "LICENSES", "THIRD-PARTY-NOTICES.txt", "packaging/app.ico")) {
        if (-not (Test-Path -LiteralPath (Join-Path $root $inputPath))) {
            throw "Required release input is missing: $inputPath"
        }
    }

    & $Python -m PyInstaller --noconfirm --clean --distpath $distDir --workpath (Join-Path $root "build/pyinstaller") (Join-Path $root "packaging/TeamRadioStudio.spec")
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed with exit code $LASTEXITCODE." }
    if (-not (Test-Path -LiteralPath $exe -PathType Leaf)) { throw "EXE was not created: $exe" }

    # Windowed executables must be explicitly awaited, including the one-file child.
    if (Test-Path -LiteralPath $report) {
        $oldReport = Get-Item -LiteralPath $report
        if ($oldReport.DirectoryName -ne $distDir -or $oldReport.Name -ne "self-test-report.json") { throw "Unexpected self-test report path." }
        Remove-Item -LiteralPath $oldReport.FullName -Force
    }
    $verifyArgs = @((Join-Path $root "tools/verify_windows_exe.py"), $exe, $distDir)
    if ($TestTempDirectory) { $verifyArgs += @("--temp", $TestTempDirectory) }
    & $Python @verifyArgs
    if ($LASTEXITCODE -ne 0) { throw "Packaged EXE verification failed. See reports in $distDir" }

    Copy-Item -LiteralPath (Join-Path $root "THIRD-PARTY-NOTICES.txt") -Destination $distDir -Force
    $distLicenses = Join-Path $distDir "LICENSES"
    if (Test-Path -LiteralPath $distLicenses) {
        $oldLicenses = Get-Item -LiteralPath $distLicenses
        if ($oldLicenses.Parent.FullName -ne $distDir -or $oldLicenses.Name -ne "LICENSES") { throw "Unexpected license output path." }
        Remove-Item -LiteralPath $oldLicenses.FullName -Recurse -Force
    }
    Copy-Item -LiteralPath (Join-Path $root "LICENSES") -Destination $distLicenses -Recurse
    Compress-Archive -LiteralPath @((Join-Path $distDir "THIRD-PARTY-NOTICES.txt"), $distLicenses) -DestinationPath $licenseZip -Force

    $releaseFiles = @($exe, $licenseZip, (Join-Path $distDir "THIRD-PARTY-NOTICES.txt"), $report, (Join-Path $distDir "gui-smoke-test-report.json"))
    $sums = foreach ($file in $releaseFiles) {
        $hash = (Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash.ToLowerInvariant()
        "{0}  {1}" -f $hash, (Split-Path -Leaf $file)
    }
    $sums | Set-Content -LiteralPath (Join-Path $distDir "SHA256SUMS.txt") -Encoding ascii
    Write-Host "Verified release artifacts: $distDir"
}
finally {
    Pop-Location
}
