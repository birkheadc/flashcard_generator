# Building the Windows installer

This has to be run **on Windows** — PyInstaller builds a native executable
for whatever OS it runs on and can't cross-compile from Linux/macOS, so none
of this can be exercised from the Linux dev container this repo is normally
developed in.

## Prerequisites

- Windows 10/11, x64.
- [uv](https://docs.astral.sh/uv/) with the project's `packaging` dependency
  group installed:

  ```powershell
  uv sync --group packaging
  ```

- [Inno Setup 6](https://jrsoftware.org/isinfo.php) — only needed to produce
  the installer `.exe`; skip it if you just want the raw PyInstaller build
  in `dist\FlashcardGenerator\`.

## Build

From the repo root:

```powershell
uv run powershell -ExecutionPolicy Bypass -File packaging\build_windows.ps1
```

This runs PyInstaller (spec: `packaging/flashcard_generator.spec`), producing
a one-folder app at `dist\FlashcardGenerator\`, then invokes Inno Setup if
`ISCC.exe` is found, producing `dist\installer\FlashcardGeneratorSetup.exe`
— the single file to hand to an end user.

To do either step by hand instead:

```powershell
pyinstaller packaging/flashcard_generator.spec --distpath dist --workpath build
ISCC packaging\installer.iss
```

## Verify (per ROADMAP.md Phase 10)

1. Run `dist\FlashcardGenerator\FlashcardGenerator.exe` directly — confirms
   PyInstaller's bundling is complete before layering the installer on top.
2. Run `FlashcardGeneratorSetup.exe` on a machine that has never had the
   project's Python/uv environment on it, install, and launch from the
   Start Menu shortcut.
3. Exercise the paths that depend on bundled non-code data specifically,
   since those are what a plain "it launches" check won't catch:
   - Any toolbar icon rendering (qtawesome's icon fonts).
   - "Suggest Clips" against a loaded recording (silero-vad's model weights
     — first click after launch is the one that proves the data files were
     actually collected, per the `collect_data_files` calls in the spec).
   - Import audio → add a clip → mark a cloze → Export → open the `.apkg`
     in a real Anki install, i.e. the existing Phase 6 verify step, now
     against the packaged build instead of `uv run`.
4. Uninstall via "Apps & Features" and confirm it cleans up (Inno Setup's
   generated uninstaller handles this; there's nothing custom to check
   beyond "it's gone").

## Known size/behavior notes

- `silero-vad` depends on `torch`; on Windows the plain PyPI `torch` wheel
  is the CPU-only build (~120MB), not the much larger CUDA build Linux
  pulls in by default — no extra index configuration needed for this
  project's Windows target. Total installed size is expect to land somewhere
  around 400-600MB, mostly torch's own DLLs.
- The build is one-folder (`COLLECT`), not one-file: a one-file PyInstaller
  build would re-extract torch's DLLs into a temp directory on every launch,
  which is slow enough to feel broken. The installer is still the single
  artifact a user deals with — what it installs behaves like normal
  installed Windows software.
- UPX compression is off in the spec. It shrinks the DLLs but has a history
  of triggering Windows Defender/AV false positives on PyInstaller output,
  and torch's DLLs are exactly the large binaries where that risk shows up.
- There's no app icon configured yet (`icon=None` in the spec, and Inno
  Setup falls back to `FlashcardGenerator.exe`'s own icon for shortcuts).
  Add one by pointing the spec's `icon=` at a `.ico` file once one exists.
