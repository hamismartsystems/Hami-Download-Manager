; Inno Setup script — HAMI Download Manager (HDM) 1.0.1
; Requires Inno Setup 6 (free): https://jrsoftware.org/isdl.php
; Build the app first: build_windows.bat  (creates dist\HDM-1.0.1\HDM-1.0.1.exe)
; Then right-click this file -> Compile, or run build_installer.bat
; Output: installer\HDM-1.0.1-Setup.exe

#define MyAppName "HAMI Download Manager (HDM)"
#define MyAppShort "HDM"
#define MyAppVersion "1.0.1"
#define MyAppPublisher "HAMI SMART SYSTEMS"
#define MyAppURL "https://hamidesigns.shop/hdm/"
#define MyAppExeName "HDM-1.0.1.exe"
#define MyBuildDir "dist\HDM-1.0.1"

[Setup]
AppId={{8F2C1A55-HDM1-1000-9000-HAMISMARTSYSTEMS}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={pf}\HAMI Download Manager
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=installer
OutputBaseFilename=HDM-{#MyAppVersion}-Setup
SetupIconFile=hdm-bmp.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
UninstallDisplayName={#MyAppName} {#MyAppVersion}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
PrivilegesRequiredOverridesAllowed=commandline
AlwaysShowComponentsList=no
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"; Flags: unchecked
Name: "startup"; Description: "Start HDM with Windows (hidden in tray)"; GroupDescription: "Options:"; Flags: unchecked

[InstallDelete]
Type: files; Name: "{app}\HDM-1.0.0.exe"

[Files]
Source: "{#MyBuildDir}\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#MyBuildDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\{#MyAppExeName}"; Comment: "HAMI Download Manager"
Name: "{group}\Uninstall {#MyAppShort}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "HAMIDownloadManager"; ValueData: """{app}\{#MyAppExeName}"" --silent"; Tasks: startup; Flags: uninsdeletevalue

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppShort} now"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{localappdata}\HDM"
