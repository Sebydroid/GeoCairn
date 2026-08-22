; Recette de l'installeur Windows de Géo Cairn (Inno Setup 6).
;
;   iscc installateur.iss
;
; Produit dist-installeur\GeoCairn-<version>-installation.exe : un installeur
; classique, avec raccourcis, entrée dans « Applications et fonctionnalités »
; et désinstallation.
;
; L'installation se fait dans le profil de l'utilisateur : aucun droit
; d'administrateur n'est demandé, et plusieurs comptes d'un même poste ont
; chacun leur installation et leurs traces.

; Ce fichier est en UTF-8 avec BOM : sans cette marque, Inno Setup le lit en
; ANSI et affiche « GÃ©o Cairn » là où il devrait afficher « Géo Cairn ».

; Le nom affiché porte un accent et une espace ; les dossiers, l'exécutable et
; le fichier produit s'en tiennent à l'identifiant, sans accent ni espace.
#define MonNom "Géo Cairn"
#define MonIdentifiant "GeoCairn"
#define MonEditeur "Géo Cairn"
#define MonExe "GeoCairn.exe"
#ifndef MaVersion
  #define MaVersion "0.2"
#endif

[Setup]
AppId={{8E2C7A34-5F41-4B9E-9C3D-0A6B1D5E7F20}
AppName={#MonNom}
AppVersion={#MaVersion}
AppPublisher={#MonEditeur}
DefaultDirName={localappdata}\Programs\{#MonIdentifiant}
DefaultGroupName={#MonNom}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=dist-installeur
OutputBaseFilename={#MonIdentifiant}-{#MaVersion}-installation
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
; Icône de l'assistant d'installation et du raccourci de désinstallation.
SetupIconFile=geocairn\resources\geocairn.ico
; Le désinstalleur doit pouvoir retirer proprement le dossier du programme.
UninstallDisplayIcon={app}\{#MonExe}
UninstallDisplayName={#MonNom} {#MaVersion}

; Mise à jour, programme ouvert. Windows retient les fichiers d'une application
; qui tourne : sans ces trois directives, la copie échouerait à mi-chemin et
; laisserait un mélange de deux versions.
;   AppMutex          : la marque posée par le programme (voir geocairn/mutex.py).
;                       Le nom doit rester identique des deux côtés.
;   CloseApplications : propose de fermer ce qui retient les fichiers.
;   RestartApplications=no : la page finale offre déjà de relancer Géo Cairn ;
;                       le redémarrage automatique en ouvrirait un second.
AppMutex=GeoCairn.Application.Running
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "francais"; MessagesFile: "compiler:Languages\French.isl"

[Tasks]
Name: "bureau"; Description: "Créer un raccourci sur le Bureau"; \
    GroupDescription: "Raccourcis :"

[InstallDelete]
; Le dossier des bibliothèques est vidé avant la copie. « ignoreversion » écrase
; les fichiers de même nom mais n'efface jamais les autres : une bibliothèque
; d'une version antérieure y resterait, et serait chargée au lancement à la
; place de la nouvelle. Seul {app}\_internal est visé — le désinstalleur, lui,
; vit directement dans {app} et doit survivre à la mise à jour.
Type: filesandordirs; Name: "{app}\_internal"

[Files]
; Tout le dossier produit par PyInstaller, sauf les scripts d'installation
; sans objet une fois installé.
Source: "dist\{#MonIdentifiant}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs; \
    Excludes: "Installer.bat,Desinstaller.bat,installer.ps1"

[Icons]
Name: "{group}\{#MonNom}"; Filename: "{app}\{#MonExe}"
Name: "{userdesktop}\{#MonNom}"; Filename: "{app}\{#MonExe}"; Tasks: bureau

[Run]
Filename: "{app}\{#MonExe}"; Description: "Lancer {#MonNom}"; \
    Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Le dossier du programme uniquement. Les traces vivent dans
; {localappdata}\GeoCairn et ne doivent jamais être touchées ici.
Type: filesandordirs; Name: "{app}"

[Messages]
francais.WelcomeLabel2=Cet assistant va installer [name/ver] sur votre ordinateur.%n%nVos traces sont conservées dans votre profil utilisateur : une mise à jour ou une désinstallation ne les efface pas.
