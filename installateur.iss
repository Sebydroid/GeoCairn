; Recette de l'installeur Windows de Carto (Inno Setup 6).
;
;   iscc installateur.iss
;
; Produit dist-installeur\Carto-<version>-installation.exe : un installeur
; classique, avec raccourcis, entrée dans « Applications et fonctionnalités »
; et désinstallation.
;
; L'installation se fait dans le profil de l'utilisateur : aucun droit
; d'administrateur n'est demandé, et plusieurs comptes d'un même poste ont
; chacun leur installation et leurs traces.

#define MonNom "Carto"
#define MonEditeur "Carto"
#define MonExe "Carto.exe"
#ifndef MaVersion
  #define MaVersion "1.0.0"
#endif

[Setup]
AppId={{8E2C7A34-5F41-4B9E-9C3D-0A6B1D5E7F20}
AppName={#MonNom}
AppVersion={#MaVersion}
AppPublisher={#MonEditeur}
DefaultDirName={localappdata}\Programs\{#MonNom}
DefaultGroupName={#MonNom}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=dist-installeur
OutputBaseFilename={#MonNom}-{#MaVersion}-installation
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
; Le désinstalleur doit pouvoir retirer proprement le dossier du programme.
UninstallDisplayIcon={app}\{#MonExe}
UninstallDisplayName={#MonNom} {#MaVersion}

[Languages]
Name: "francais"; MessagesFile: "compiler:Languages\French.isl"

[Tasks]
Name: "bureau"; Description: "Créer un raccourci sur le Bureau"; \
    GroupDescription: "Raccourcis :"

[Files]
; Tout le dossier produit par PyInstaller, sauf les scripts d'installation
; sans objet une fois installé.
Source: "dist\{#MonNom}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs; \
    Excludes: "Installer.bat,Desinstaller.bat,installer.ps1"

[Icons]
Name: "{group}\{#MonNom}"; Filename: "{app}\{#MonExe}"
Name: "{userdesktop}\{#MonNom}"; Filename: "{app}\{#MonExe}"; Tasks: bureau

[Run]
Filename: "{app}\{#MonExe}"; Description: "Lancer {#MonNom}"; \
    Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Le dossier du programme uniquement. Les traces vivent dans
; {localappdata}\Carto et ne doivent jamais être touchées ici.
Type: filesandordirs; Name: "{app}"

[Messages]
francais.WelcomeLabel2=Cet assistant va installer [name/ver] sur votre ordinateur.%n%nVos traces sont conservées dans votre profil utilisateur : une mise à jour ou une désinstallation ne les efface pas.
