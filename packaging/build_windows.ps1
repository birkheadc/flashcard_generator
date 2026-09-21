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
        uv run powershell -ExecutionPolicy Bypass -File packaging/build_windows.ps1

    Or, from an already-activated venv:

        powershell -ExecutionPolicy Bypass -File packaging/build_windows.ps1

    Use forward slashes in this path even on Windows: a backslash path typed
    into a bash-style shell (e.g. Git Bash) gets its backslash silently
    stripped by the shell's own escaping before PowerShell ever sees it.
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
        $candidatePaths = @(
            (Join-Path ${env:ProgramFiles(x86)} "Inno Setup 6\ISCC.exe"),
            (Join-Path $env:ProgramFiles "Inno Setup 6\ISCC.exe"),
            (Join-Path $env:LOCALAPPDATA "Programs\Inno Setup 6\ISCC.exe")
        )
        $isccPath = $candidatePaths | Where-Object { Test-Path $_ } | Select-Object -First 1
    }

    if ($isccPath) {
        # flashcard_generator/__init__.py's __version__ is this project's one
        # source of truth for its version number (also shown in the app's own
        # window title) — read it here instead of keeping a second, easy-to-
        # forget copy hardcoded in installer.iss.
        $version = (python -c "from flashcard_generator import __version__; print(__version__)").Trim()
        Write-Host "==> Building installer with Inno Setup (version $version)"
        & $isccPath "/DMyAppVersion=$version" "packaging\installer.iss"
        Write-Host "==> Installer written to dist\installer\FlashcardGeneratorSetup.exe"
    } else {
        Write-Warning "ISCC.exe (Inno Setup) not found on PATH or in its default install location."
        Write-Warning "Install it from https://jrsoftware.org/isinfo.php, then run: ISCC packaging/installer.iss"
    }
}
finally {
    Pop-Location
}
