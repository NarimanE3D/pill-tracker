#define MyAppName        "PillTracker"
#define MyAppVersion     "2.2.0"
#define MyAppPublisher   "Mandy"
#define MyAppURL         "https://github.com/NarimanE3D"
#define MyAppExeName     "PillTracker.exe"

; Point this to your PyInstaller onedir output
#define MyDistDir        "dist\PillTracker"

; (Recommended) keep a stable AppId GUID forever for proper upgrades
#define MyAppId          "{{6F7E2C8E-5A8D-4E5A-9C8B-1D237A6F1B11}"

[Setup]
AppId={#MyAppId}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}

DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes

; If you have a license, set it; otherwise remove this line entirely
; LicenseFile=LICENSE.txt

OutputDir=installer_output
OutputBaseFilename={#MyAppName}-Setup-{#MyAppVersion}

SetupIconFile=assets\icon.ico
UninstallDisplayIcon={app}\{#MyAppExeName}

Compression=lzma2
SolidCompression=yes
WizardStyle=modern

; Better UX / Windows integration
PrivilegesRequired=admin
ChangesAssociations=yes
ChangesEnvironment=yes

; Avoid mixing 32/64-bit installs
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

; Recommended for clean upgrades (works well when AppId stays constant)
; AppVersion doesn't decide upgrade logic—this does.
VersionInfoVersion={#MyAppVersion}
VersionInfoCompany={#MyAppPublisher}
VersionInfoProductName={#MyAppName}
VersionInfoDescription={#MyAppName}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional options:"; Flags: unchecked
Name: "startmenuicon"; Description: "Create Start Menu shortcuts"; GroupDescription: "Additional options:"; Flags: checkedonce

[Files]
; Install everything from the PyInstaller onedir folder
Source: "{#MyDistDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

; Optional: if you want to ship extra assets outside dist, add them explicitly:
; Source: "assets\*"; DestDir: "{app}\assets"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#MyAppName}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: startmenuicon
Name: "{autoprograms}\{#MyAppName}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"; Tasks: startmenuicon
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; If your app creates logs/cache under {app}, this ensures a clean removal
Type: filesandordirs; Name: "{app}\logs"
Type: filesandordirs; Name: "{app}\cache"
