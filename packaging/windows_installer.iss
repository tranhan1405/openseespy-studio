#define AppName "OpenSeesPy Studio"
#ifndef AppVersion
  #define AppVersion "0.2.0-alpha.1"
#endif
#ifndef RepoRoot
  #define RepoRoot ".."
#endif

[Setup]
AppId={{8E7AC837-C7DB-4CDA-BF51-6D7CB2EAC1C7}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=Tran-Van Han
DefaultDirName={localappdata}\Programs\OpenSeesPy Studio
DefaultGroupName=OpenSeesPy Studio
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir={#RepoRoot}\dist\installer
OutputBaseFilename=OpenSeesPy-Studio-{#AppVersion}-Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\OpenSeesPyStudio.exe

[Files]
Source: "{#RepoRoot}\dist\OpenSeesPyStudio\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\OpenSeesPy Studio"; Filename: "{app}\OpenSeesPyStudio.exe"
Name: "{autodesktop}\OpenSeesPy Studio"; Filename: "{app}\OpenSeesPyStudio.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: unchecked

[Run]
Filename: "{app}\OpenSeesPyStudio.exe"; Description: "Launch OpenSeesPy Studio"; Flags: nowait postinstall skipifsilent
