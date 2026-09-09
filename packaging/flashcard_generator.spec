# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller build spec for Flashcard Generator.

Must be run on Windows — PyInstaller does not cross-compile, so this can't
be exercised from the Linux dev container. Build from the repo root:

    pyinstaller packaging/flashcard_generator.spec --distpath dist --workpath build

See packaging/README.md for the full build + installer procedure.
"""

import os

from PyInstaller.utils.hooks import collect_data_files

PROJECT_ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))

# qtawesome (icon font files) and silero-vad (model weights) ship this as
# package data rather than importable code, so PyInstaller's static import
# analysis can't discover it on its own — collected explicitly so toolbar
# icons and "Suggest Clips" don't silently fail only once a packaged user
# reaches them.
datas = []
datas += collect_data_files("qtawesome")
datas += collect_data_files("silero_vad")

a = Analysis(
    [os.path.join(PROJECT_ROOT, "packaging", "pyinstaller_entry.py")],
    pathex=[PROJECT_ROOT],
    binaries=[],
    datas=datas,
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="FlashcardGenerator",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    # UPX-compressing torch's large DLLs is slow and has a history of
    # tripping Windows Defender/AV heuristics on PyInstaller builds; left
    # off by default. Safe to try `--upx-dir` if installer size matters.
    upx=False,
    console=False,
    icon=None,
)

# onedir (COLLECT), not onefile: a onefile build has to self-extract torch's
# ~100MB+ of DLLs into a temp dir on every launch, which is slow enough to
# feel broken on first impression. The installer (packaging/installer.iss)
# is the single artifact end users actually run; what it installs is a
# normal one-folder app, same as most Windows software.
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="FlashcardGenerator",
)
