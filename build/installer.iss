; Inno Setup script dla "Anonimizator Pism".
;
; WAZNE OGRANICZENIE SRODOWISKA: ten plik jest pisany i weryfikowany tylko
; skladniowo tutaj (Linux) - Inno Setup Compiler (ISCC.exe) to natywne
; narzedzie Windows i nie da sie go uruchomic ani przetestowac na tej
; maszynie. Faktyczna kompilacja (`iscc build\installer.iss`) dzieje sie
; wylacznie w GitHub Actions na runnerze windows-latest, PO tym jak
; `pyinstaller build/anonimizator.spec` wyprodukuje katalog one-dir w
; dist/AnonimizatorPism/ - ten skrypt zaklada, ze ten katalog juz istnieje
; wzgledem lokalizacji tego pliku .iss (..\dist\AnonimizatorPism).
;
; Decyzja o instalacji per-user (nie Program Files/admin):
; `PrivilegesRequired=lowest` + `DefaultDirName={autopf}` normalnie wymaga
; uprawnien administratora dla Program Files. Poniewaz docelowy uzytkownik to
; nietechniczny prawnik, ktory moze nie miec uprawnien admina na sluzbowym
; komputerze, wybieramy kompromis: instalacja do
; {localappdata}\Programy\AnonimizatorPism (per-user, bez UAC), z
; PrivilegesRequired=lowest. Kosztem jest to, ze aplikacja instaluje sie tylko
; dla biezacego uzytkownika Windows, nie systemowo dla wszystkich - uznane za
; akceptowalne wobec priorytetu "zero tarcia przy instalacji".

#define MyAppName "Anonimizator Pism"
#define MyAppVersion "0.2.0"
; TODO: podmienic na docelowego wydawce/firme przed pierwszym wydaniem.
#define MyAppPublisher "Wydawca aplikacji (uzupelnij)"
#define MyAppURL "https://github.com/cenkierpiotr/anonimizator-pism"
#define MyAppExeName "AnonimizatorPism.exe"
; Katalog wyjsciowy PyInstaller (one-dir) wzgledem tego pliku .iss.
#define DistDir "..\dist\AnonimizatorPism"

[Setup]
AppId={{B3F1E6B4-2A9A-4E1C-9C7D-7F6A2E5B8C10}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
; Instalacja per-user, bez wymogu admina - patrz uzasadnienie w naglowku pliku.
DefaultDirName={localappdata}\Programy\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
; Jeden plik .exe instalatora ze skrotem na pulpicie (wymog z planu).
OutputDir=Output
OutputBaseFilename=AnonimizatorPism-Setup-{#MyAppVersion}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
; Krotka strona informacyjna (offline z jednym wyjatkiem - LibreOffice on-demand,
; patrz plan sekcja "Pobieranie LibreOffice na zadanie").
InfoBeforeFile=installer_info_before.txt
; Instalator jest niepodpisany (patrz TODO w anonimizator.spec dot. code
; signing, Faza 5) - SmartScreen prawdopodobnie ostrzeze przy pierwszym
; uruchomieniu, to swiadomie odlozone, nie blad tego skryptu.
UninstallDisplayIcon={app}\{#MyAppExeName}
; Nie kompresujemy do jednego archiwum - kopiujemy caly katalog one-dir,
; wiec ArchitecturesInstallIn64BitMode nie jest wymagane osobno, ale wymuszamy
; 64-bit, bo PyInstaller na windows-latest builduje pod x64.
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "polish"; MessagesFile: "compiler:Languages\Polish.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: checkedonce

[Files]
; Caly katalog one-dir wyprodukowany przez PyInstaller - wszystkie pliki i
; podkatalogi (model spaCy, gazetteery, tessdata, ewentualny vendorowany
; Tesseract - patrz build/anonimizator.spec).
Source: "{#DistDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#MyAppName}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Sprzatanie ewentualnego cache LibreOffice pobranego on-demand oraz
; katalogow tymczasowych aplikacji (patrz plan, sekcja "Higiena plikow
; tymczasowych") - nie zostawiamy nieanonimizowanych plikow posrednich po
; odinstalowaniu.
Type: filesandordirs; Name: "{localappdata}\AnonimizatorPism"
