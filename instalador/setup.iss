; Instalador do Organized YouTube Music Downloads for iPod (Inno Setup 6).
; Não rode direto: use  py instalador\montar.py  (ele prepara a pasta e passa Versao/Fonte).

#define Nome "Organized YouTube Music Downloads for iPod"
#ifndef Versao
  #define Versao "0.0.0"
#endif
#ifndef Fonte
  #define Fonte "build\app"
#endif
#define Repo "https://github.com/DestroyerHead/Organized-YouTube-Music-Downloads-for-iPod"

[Setup]
AppId={{27AEC425-5D83-41B9-8AB2-BC1A28F6B680}
AppName={#Nome}
AppVersion={#Versao}
AppVerName={#Nome} {#Versao}
AppPublisher=DestroyerHead
AppPublisherURL={#Repo}
AppSupportURL={#Repo}/issues
AppUpdatesURL={#Repo}/releases
; Instala só pro usuário atual (sem administrador). A pasta precisa ser gravável:
; o programa guarda o histórico em {app}\dados e atualiza o yt-dlp sozinho.
PrivilegesRequired=lowest
DefaultDirName={autopf}\{#Nome}
DefaultGroupName={#Nome}
DisableProgramGroupPage=yes
OutputDir=saida
OutputBaseFilename=Organized-YouTube-Music-Downloads-for-iPod-Setup-{#Versao}
SetupIconFile={#Fonte}\icone.ico
UninstallDisplayIcon={app}\icone.ico
UninstallDisplayName={#Nome}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
InfoAfterFile=depois_de_instalar.txt
CloseApplications=yes

[Languages]
Name: "pt"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"
Name: "en"; MessagesFile: "compiler:Default.isl"

[CustomMessages]
pt.SemItunes=O iTunes não foi encontrado neste PC.%n%nEle é necessário pra mandar as músicas pro iPod: o programa coloca as músicas no iTunes e você sincroniza o iPod por ele. Sem o iTunes, as músicas só ficam salvas numa pasta.%n%nQuer abrir a página do iTunes na Microsoft Store agora?%n(A instalação continua do mesmo jeito.)
en.SemItunes=iTunes was not found on this PC.%n%nIt is required to send the songs to your iPod: the app adds the songs to iTunes and you sync the iPod with it. Without iTunes, songs are only saved to a folder.%n%nOpen the iTunes page in the Microsoft Store now?%n(Setup will continue either way.)
pt.Atalho=Criar atalho na área de trabalho
en.Atalho=Create a desktop shortcut
pt.Abrir=Abrir o programa agora
en.Abrir=Open the app now
pt.PastaExtensao=Pasta da extensão do Chrome
en.PastaExtensao=Chrome extension folder
pt.Registrando=Registrando a extensão no Chrome...
en.Registrando=Registering the Chrome extension...

[Tasks]
Name: "atalho"; Description: "{cm:Atalho}"

[Files]
Source: "{#Fonte}\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Dirs]
; histórico, configuração e log: ficam mesmo se desinstalar (pra não perder nada)
Name: "{app}\dados"; Flags: uninsneveruninstall

[Icons]
; "Abrir" dentro da pasta: a extensão usa ele pra abrir o programa quando está fechado
Name: "{app}\Abrir"; Filename: "{app}\python\pythonw.exe"; Parameters: """{app}\ipod_musicas.pyw"""; WorkingDir: "{app}"; IconFilename: "{app}\icone.ico"
Name: "{group}\{#Nome}"; Filename: "{app}\python\pythonw.exe"; Parameters: """{app}\ipod_musicas.pyw"""; WorkingDir: "{app}"; IconFilename: "{app}\icone.ico"
Name: "{group}\{cm:PastaExtensao}"; Filename: "{app}\extensao"
Name: "{group}\{cm:UninstallProgram,{#Nome}}"; Filename: "{uninstallexe}"
Name: "{userdesktop}\{#Nome}"; Filename: "{app}\python\pythonw.exe"; Parameters: """{app}\ipod_musicas.pyw"""; WorkingDir: "{app}"; IconFilename: "{app}\icone.ico"; Tasks: atalho

[Registry]
; mensageiro da extensão do Chrome (Native Messaging) — sai junto ao desinstalar
Root: HKCU; Subkey: "Software\Google\Chrome\NativeMessagingHosts\com.ipodmusicas.app"; ValueType: string; ValueName: ""; ValueData: "{app}\mensageiro\com.ipodmusicas.app.json"; Flags: uninsdeletekey

[Run]
Filename: "{app}\python\python.exe"; Parameters: """{app}\mensageiro\instalar.py"""; WorkingDir: "{app}"; Flags: runhidden; StatusMsg: "{cm:Registrando}"
Filename: "{app}\python\pythonw.exe"; Parameters: """{app}\ipod_musicas.pyw"""; WorkingDir: "{app}"; Description: "{cm:Abrir}"; Flags: postinstall nowait skipifsilent

[UninstallDelete]
; arquivos criados depois da instalação (atualizações do yt-dlp, caches, registro do mensageiro)
Type: filesandordirs; Name: "{app}\python"
Type: filesandordirs; Name: "{app}\musicas\__pycache__"
Type: filesandordirs; Name: "{app}\mensageiro\__pycache__"
Type: files; Name: "{app}\mensageiro\com.ipodmusicas.app.json"

[Code]
function ItunesInstalado(): Boolean;
var
  Codigo: Integer;
begin
  { iTunes da Microsoft Store (AppleInc.iTunes) ou o instalador clássico da Apple }
  Result := FileExists(ExpandConstant('{commonpf64}\iTunes\iTunes.exe')) or
            FileExists(ExpandConstant('{commonpf32}\iTunes\iTunes.exe'));
  if not Result then
    Result := Exec('powershell.exe',
      '-NoProfile -ExecutionPolicy Bypass -Command "if (Get-AppxPackage -Name AppleInc.iTunes) { exit 0 } else { exit 1 }"',
      '', SW_HIDE, ewWaitUntilTerminated, Codigo) and (Codigo = 0);
end;

function InitializeSetup(): Boolean;
var
  Codigo: Integer;
begin
  Result := True;
  if (not WizardSilent()) and (not ItunesInstalado()) then
    if MsgBox(CustomMessage('SemItunes'), mbConfirmation, MB_YESNO) = IDYES then
      ShellExec('open', 'https://apps.microsoft.com/detail/9pb2mz1zmb1s', '', '', SW_SHOWNORMAL, ewNoWait, Codigo);
end;
