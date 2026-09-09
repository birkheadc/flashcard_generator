; Inno Setup script for Flashcard Generator.
; Requires Inno Setup 6 (https://jrsoftware.org/isinfo.php) and a PyInstaller
; build already produced at dist\FlashcardGenerator (see README.md).
;
; Build with:  ISCC packaging\installer.iss   (run from the repo root)

#define MyAppName "Flashcard Generator"
; Overridden by build_windows.ps1 via `ISCC /DMyAppVersion=x.y.z`, which reads
; the version straight from flashcard_generator/__init__.py — that file (also
; shown in the app's own window title) is this project's one source of truth
; for its version number, so a standalone `ISCC installer.iss` run (no /D
; override) falls back to this literal rather than silently stamping the
; wrong version.
#ifndef MyAppVersion
  #define MyAppVersion "0.1.0"
#endif
#define MyAppPublisher "Colby Birkhead"
#define MyAppExeName "FlashcardGenerator.exe"

[Setup]
AppId={{B1D534A1-4C33-460A-864E-736EC7CC4265}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
UninstallDisplayIcon={app}\{#MyAppExeName}
OutputDir=..\dist\installer
OutputBaseFilename=FlashcardGeneratorSetup
Compression=lzma2
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
WizardStyle=modern

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: unchecked

[Files]
Source: "..\dist\FlashcardGenerator\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName}"; Flags: nowait postinstall skipifsilent
