<#
.SYNOPSIS
    Builds Flashcard Generator into a Windows installer.

.DESCRIPTION
    Runs PyInstaller against packaging/flashcard_generator.spec, then (if
    Inno Setup's ISCC.exe is available) wraps the result into a single
    installer executable. Windows-only — PyInstaller does not cross-compile.

.NOTES
    Run from an environment that has the project's "packaging" dependency
    group installed, e.g.:

        uv sync --group packaging
        uv run powershell -ExecutionPolicy Bypass -File packaging\build_windows.ps1

    Or, from an already-activated venv:

        powershell -ExecutionPolicy Bypass -File packaging\build_windows.ps1
#>

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot

Push-Location $RepoRoot
try {
    Write-Host "==> Running PyInstaller"
    pyinstaller packaging/flashcard_generator.spec --distpath dist --workpath build --noconfirm

    $isccCmd = Get-Command ISCC.exe -ErrorAction SilentlyContinue
    if ($isccCmd) {
        $isccPath = $isccCmd.Source
    } else {
        $defaultPath = Join-Path ${env:ProgramFiles(x86)} "Inno Setup 6\ISCC.exe"
        $isccPath = if (Test-Path $defaultPath) { $defaultPath } else { $null }
    }

    if ($isccPath) {
        Write-Host "==> Building installer with Inno Setup"
        & $isccPath "packaging\installer.iss"
        Write-Host "==> Installer written to dist\installer\FlashcardGeneratorSetup.exe"
    } else {
        Write-Warning "ISCC.exe (Inno Setup) not found on PATH or in its default install location."
        Write-Warning "Install it from https://jrsoftware.org/isinfo.php, then run: ISCC packaging\installer.iss"
    }
}
finally {
    Pop-Location
}
