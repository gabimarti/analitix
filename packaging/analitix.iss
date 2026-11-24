; ---------------------------------------------------------------------------
; Script: analitix.iss
; Autor: Gabriel Marti
; Contacto: https://github.com/gabimarti
; Fecha de creación: 2026-09-29
; ---------------------------------------------------------------------------
; Instalador de Windows (Inno Setup 6). Uso: scripts\build_windows.bat, que
; compila antes dist\Analitix\ con PyInstaller y llama a
;   ISCC /DAppVersion=<versión> packaging\analitix.iss
; Instalación por usuario, sin permisos de administrador. Pregunta dónde
; guardar los datos: crea ahí "Analitix\informes_analiticas" y
; "Analitix\data" y lo apunta en HKCU\Software\Analitix\HomeDir, que la app
; lee al arrancar (config._installed_home_dir). Al desinstalar nunca se
; borran los datos del usuario.
; Prueba desatendida: Analitix-Setup-X.exe /VERYSILENT /DIR=<programa> /DATADIR=<carpeta>

#ifndef DistDir
  #define DistDir "..\dist\Analitix"
#endif
#ifndef AppVersion
  #error Falta /DAppVersion=<versión> (lo pasa scripts\build_windows.bat)
#endif

[Setup]
AppId={{6F1C2B7E-4E0A-4C58-9C2B-2A7D5E9B3F41}
AppName=Analitix
AppVersion={#AppVersion}
AppVerName=Analitix {#AppVersion}
AppPublisher=Gabriel Marti
AppPublisherURL=https://gabimarti.github.io/
DefaultDirName={autopf}\Analitix
PrivilegesRequired=lowest
DisableProgramGroupPage=yes
OutputDir=..\dist
OutputBaseFilename=Analitix-Setup-{#AppVersion}
SetupIconFile=..\build\analitix.ico
UninstallDisplayIcon={app}\Analitix.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"
Name: "catalan"; MessagesFile: "compiler:Languages\Catalan.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "{#DistDir}\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Dirs]
Name: "{code:GetHomeDir}\data"; Flags: uninsneveruninstall
Name: "{code:GetHomeDir}\informes_analiticas"; Flags: uninsneveruninstall

[Registry]
Root: HKCU; Subkey: "Software\Analitix"; ValueType: string; ValueName: "HomeDir"; ValueData: "{code:GetHomeDir}"; Flags: uninsdeletekey

[Icons]
Name: "{autoprograms}\Analitix"; Filename: "{app}\Analitix.exe"
Name: "{autodesktop}\Analitix"; Filename: "{app}\Analitix.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\Analitix.exe"; Description: "{cm:LaunchProgram,Analitix}"; Flags: nowait postinstall skipifsilent

[Code]
var
  DataPage: TInputDirWizardPage;
  CurrentHome: String;

procedure InitializeWizard;
begin
  DataPage := CreateInputDirPage(wpSelectDir,
    'Carpeta de tus datos',
    '¿Dónde quieres guardar tus datos?',
    'Analitix creará en la carpeta que elijas una carpeta "Analitix" con dos subcarpetas:' + #13#10 +
    '  · informes_analiticas: deja aquí los PDF de tus analíticas.' + #13#10 +
    '  · data: la base de datos cifrada con tu contraseña.' + #13#10#13#10 +
    'Si ya tienes una carpeta "Analitix" de una instalación anterior, elige la carpeta que la contiene y se seguirán usando tus datos. Al desinstalar Analitix, esta carpeta no se borra.',
    False, '');
  DataPage.Add('');
  // Orden: /DATADIR explícito (pruebas desatendidas); si no, la ubicación
  // vigente, que el usuario puede haber cambiado desde la app
  // (Configuración); si no, la anterior del instalador; si no, Documentos.
  if ExpandConstant('{param:DATADIR|}') <> '' then
    DataPage.Values[0] := ExpandConstant('{param:DATADIR}')
  else if RegQueryStringValue(HKCU, 'Software\Analitix', 'HomeDir', CurrentHome) and (CurrentHome <> '') then
    DataPage.Values[0] := ExtractFileDir(CurrentHome)
  else
    DataPage.Values[0] := GetPreviousData('DataParent', ExpandConstant('{userdocs}'));
end;

procedure RegisterPreviousData(PreviousDataKey: Integer);
begin
  SetPreviousData(PreviousDataKey, 'DataParent', DataPage.Values[0]);
end;

function GetHomeDir(Param: String): String;
begin
  Result := AddBackslash(DataPage.Values[0]) + 'Analitix';
end;
