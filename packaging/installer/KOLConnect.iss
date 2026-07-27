#define AppName "KOL联系助手"
#define AppVersion "0.2.1"
#define AppPublisher "KOL Connect"
#define AppExeName "KOLConnect.exe"

[Setup]
AppId={{C0F5B829-BD30-4A1F-83C9-455AE6DB8489}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={autopf}\KOLConnect
DefaultGroupName={#AppName}
SetupIconFile={#SourcePath}\..\..\assets\KOLConnect.ico
DisableProgramGroupPage=yes
OutputDir={#GetEnv('USERPROFILE')}\Desktop
OutputBaseFilename=KOLConnect_v0.2.1_setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayName={#AppName}
UninstallDisplayIcon={app}\{#AppExeName}

[Files]
Source: "{#SourcePath}\..\..\release\KOLConnect.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExeName}"
Name: "{group}\卸载 {#AppName}"; Filename: "{uninstallexe}"

[Run]
Filename: "{app}\{#AppExeName}"; Description: "启动 KOL联系助手"; Flags: nowait postinstall skipifsilent

; User data remains in the existing per-user application data directory.
; Do not add it to [InstallDelete] or [UninstallDelete].
