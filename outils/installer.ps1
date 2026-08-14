# Installe ou désinstalle Géo Cairn pour l'utilisateur courant.
#
#   powershell -ExecutionPolicy Bypass -File installer.ps1
#   powershell -ExecutionPolicy Bypass -File installer.ps1 -Desinstaller
#
# L'installation se fait dans le profil de l'utilisateur : aucun droit
# d'administrateur n'est nécessaire. Les traces, elles, vivent dans
# AppData\Local\GeoCairn et ne sont touchées ni à l'installation ni à la
# désinstallation.

param(
    [switch]$Desinstaller,
    [string]$Destination = "$env:LOCALAPPDATA\Programs\GeoCairn",
    [switch]$Silencieux
)

$ErrorActionPreference = "Stop"

# $Nom est l'identifiant technique : nom du processus, de l'exécutable et des
# dossiers. $Affichage porte l'accent et l'espace, et ne sert qu'aux libellés
# vus par l'utilisateur — raccourcis et « Applications et fonctionnalités ».
$Nom = "GeoCairn"
$Affichage = "Géo Cairn"
$CleDesinstallation = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\GeoCairn"
$MenuDemarrer = "$env:APPDATA\Microsoft\Windows\Start Menu\Programs\$Affichage.lnk"
$Bureau = "$env:USERPROFILE\Desktop\$Affichage.lnk"
$DossierDonnees = "$env:LOCALAPPDATA\GeoCairn"


function Ecrire($texte) {
    Write-Host $texte
}

function Creer-Raccourci($chemin, $cible) {
    $shell = New-Object -ComObject WScript.Shell
    $raccourci = $shell.CreateShortcut($chemin)
    $raccourci.TargetPath = $cible
    $raccourci.WorkingDirectory = Split-Path $cible
    $raccourci.Description = "Gestion de traces GPX"
    $raccourci.Save()
}

function Verifier-Ferme($geste) {
    # Windows retient les fichiers d'une application qui tourne : les
    # remplacer laisserait une installation a moitie faite, melant deux
    # versions. Mieux vaut s'arreter avant d'avoir touche a quoi que ce soit.
    if (Get-Process -Name $Nom -ErrorAction SilentlyContinue) {
        throw "$Nom est ouvert. Fermez la fenetre, puis relancez $geste."
    }
}

function Installer {
    Verifier-Ferme "l'installation"

    # $PSScriptRoot et non $MyInvocation : dans une fonction, ce dernier
    # désigne l'appel, pas le fichier.
    $source = $PSScriptRoot
    if (-not (Test-Path (Join-Path $source "GeoCairn.exe"))) {
        # Le script est rangé dans outils/ pendant le développement : le
        # programme se trouve alors dans dist\GeoCairn.
        $candidat = Join-Path (Split-Path -Parent $source) "dist\GeoCairn"
        if (Test-Path (Join-Path $candidat "GeoCairn.exe")) {
            $source = $candidat
        }
    }
    if (-not (Test-Path (Join-Path $source "GeoCairn.exe"))) {
        throw "GeoCairn.exe est introuvable a cote de ce script."
    }

    Ecrire "Installation de $Nom"
    Ecrire "  depuis : $source"
    Ecrire "  vers   : $Destination"

    if (Test-Path $Destination) {
        Ecrire "  une version precedente est remplacee"
        # Seul le dossier du logiciel est remplace ; les traces sont ailleurs.
        Remove-Item -Recurse -Force $Destination
    }
    New-Item -ItemType Directory -Force -Path $Destination | Out-Null

    Ecrire "  copie des fichiers..."
    Copy-Item -Path (Join-Path $source "*") -Destination $Destination -Recurse -Force
    # Les scripts d'installation n'ont rien a faire dans le programme installe.
    Remove-Item -Force -ErrorAction SilentlyContinue `
        (Join-Path $Destination "Installer.bat"), `
        (Join-Path $Destination "Desinstaller.bat"), `
        (Join-Path $Destination "installer.ps1")

    $executable = Join-Path $Destination "GeoCairn.exe"
    Ecrire "  raccourcis..."
    Creer-Raccourci $MenuDemarrer $executable
    Creer-Raccourci $Bureau $executable

    $taille = (Get-ChildItem -Recurse $Destination | Measure-Object -Property Length -Sum).Sum / 1024
    New-Item -Path $CleDesinstallation -Force | Out-Null
    Set-ItemProperty $CleDesinstallation DisplayName $Affichage
    Set-ItemProperty $CleDesinstallation DisplayVersion (
        (Get-Item $executable).VersionInfo.FileVersion
    )
    Set-ItemProperty $CleDesinstallation Publisher $Affichage
    Set-ItemProperty $CleDesinstallation InstallLocation $Destination
    Set-ItemProperty $CleDesinstallation DisplayIcon $executable
    Set-ItemProperty $CleDesinstallation EstimatedSize ([int]$taille)
    Set-ItemProperty $CleDesinstallation NoModify 1
    Set-ItemProperty $CleDesinstallation NoRepair 1
    Set-ItemProperty $CleDesinstallation UninstallString (
        "powershell -ExecutionPolicy Bypass -File `"$Destination\desinstaller.ps1`" -Desinstaller"
    )
    Copy-Item $PSCommandPath (Join-Path $Destination "desinstaller.ps1") -Force

    Ecrire ""
    Ecrire "$Nom est installe."
    Ecrire "  raccourci : menu Demarrer et Bureau"
    Ecrire "  vos traces : $DossierDonnees (jamais touchees par une mise a jour)"

    if (-not $Silencieux) {
        $reponse = Read-Host "Lancer $Nom maintenant ? (O/n)"
        if ($reponse -eq "" -or $reponse -match "^[oOyY]") {
            Start-Process $executable
        }
    }
}

function Desinstaller-GeoCairn {
    Verifier-Ferme "la desinstallation"
    Ecrire "Desinstallation de $Nom"

    foreach ($lien in @($MenuDemarrer, $Bureau)) {
        if (Test-Path $lien) { Remove-Item -Force $lien }
    }
    if (Test-Path $CleDesinstallation) {
        Remove-Item -Recurse -Force $CleDesinstallation
    }
    if (Test-Path $Destination) {
        Ecrire "  suppression du programme..."
        # Le script s'execute depuis ce dossier : on le laisse se supprimer
        # apres coup.
        Start-Process powershell -ArgumentList @(
            "-NoProfile", "-Command",
            "Start-Sleep -Seconds 2; Remove-Item -Recurse -Force '$Destination'"
        ) -WindowStyle Hidden
    }

    Ecrire ""
    Ecrire "$Nom est desinstalle."
    Ecrire "Vos traces sont conservees dans : $DossierDonnees"
    if (-not $Silencieux) {
        $reponse = Read-Host "Supprimer aussi vos traces ? (o/N)"
        if ($reponse -match "^[oOyY]") {
            Remove-Item -Recurse -Force $DossierDonnees -ErrorAction SilentlyContinue
            Ecrire "Traces supprimees."
        }
    }
}

if ($Desinstaller) { Desinstaller-GeoCairn } else { Installer }
