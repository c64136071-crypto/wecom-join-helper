#ifndef MyAppVersion
  #define MyAppVersion "1.0.0"
#endif
#ifndef SourceDir
  #error SourceDir must be provided with /DSourceDir=...
#endif
#ifndef OutputDir
  #define OutputDir "."
#endif

[Setup]
AppId={{97A6AC46-C73C-4D8C-9AB9-7964B94EF021}
AppName=Join Helper
AppVersion={#MyAppVersion}
AppPublisher=WeCom Join Helper contributors
DefaultDirName={localappdata}\Programs\WeComJoinHelper
DefaultGroupName=Join Helper
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir={#OutputDir}
OutputBaseFilename=JoinHelper-Setup-v{#MyAppVersion}
SetupIconFile=..\assets\wecom-rusher.ico
UninstallDisplayIcon={app}\JoinHelper.exe
LicenseFile=..\LICENSE
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: checkedonce

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\Join Helper"; Filename: "{app}\JoinHelper.exe"; WorkingDir: "{app}"
Name: "{autodesktop}\Join Helper"; Filename: "{app}\JoinHelper.exe"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\JoinHelper.exe"; Description: "{cm:LaunchProgram,Join Helper}"; Flags: nowait postinstall skipifsilent
