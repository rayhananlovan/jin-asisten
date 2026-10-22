; Inno Setup script — build.bat runs this when Inno Setup 6 is installed.
#define AppVersion "1.0.0"

[Setup]
AppId={{8C2B0F3E-5A1D-4E7B-9C4A-JINASGHARD01}
AppName=Jin Asghard
AppVersion={#AppVersion}
AppPublisher=Rehan
DefaultDirName={code:DefaultInstallDir}
DefaultGroupName=Jin Asghard
PrivilegesRequired=lowest
OutputDir=dist
OutputBaseFilename=JinAsghard-Setup-{#AppVersion}
SetupIconFile=build\jin.ico
UninstallDisplayIcon={app}\JinAsghard.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern

[Languages]
Name: "en"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Buat ikon di Desktop"; Flags: unchecked
Name: "autostart"; Description: "Jalankan Jin saat Windows menyala"; Flags: unchecked

[Files]
Source: "dist\JinAsghard\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{group}\Jin Asghard"; Filename: "{app}\JinAsghard.exe"
Name: "{group}\Uninstall Jin Asghard"; Filename: "{uninstallexe}"
Name: "{userdesktop}\Jin Asghard"; Filename: "{app}\JinAsghard.exe"; Tasks: desktopicon

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "JinAsghard"; ValueData: """{app}\JinAsghard.exe"" --minimized"; Tasks: autostart; Flags: uninsdeletevalue

[Run]
Filename: "{app}\JinAsghard.exe"; Description: "Buka Jin Asghard"; Flags: nowait postinstall skipifsilent

[Code]
function DefaultInstallDir(Param: String): String;
begin
  if DirExists('D:\') then
    Result := 'D:\JinAsghard'
  else
    Result := ExpandConstant('{localappdata}\Programs\JinAsghard');
end;
