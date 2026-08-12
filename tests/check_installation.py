"""Vérifie l'installation et la désinstallation de bout en bout.

    python tests/check_installation.py

Installe dans un répertoire temporaire, contrôle raccourcis, entrée de
désinstallation et présence du programme, puis désinstalle et vérifie que tout
est retiré — sauf les traces de l'utilisateur, qui doivent survivre.

Diagnostic hors pytest : il touche au menu Démarrer, au Bureau et au registre
de la session, et remet tout en état ensuite.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
SCRIPT = RACINE / "outils" / "installer.ps1"

MENU = Path(os.environ.get("APPDATA", "")) / (
    r"Microsoft\Windows\Start Menu\Programs\Carto.lnk"
)
BUREAU = Path(os.environ.get("USERPROFILE", "")) / "Desktop" / "Carto.lnk"
CLE = r"HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\Carto"


def powershell(*arguments) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", *arguments],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=600,
    )


def cle_existe() -> bool:
    sortie = powershell("-Command", f"Test-Path '{CLE}'")
    return "True" in sortie.stdout


def main() -> int:
    if not SCRIPT.is_file():
        print(f"script d'installation introuvable : {SCRIPT}", flush=True)
        return 1
    if not (RACINE / "dist" / "Carto" / "Carto.exe").is_file():
        print("construire d'abord : python build.py", flush=True)
        return 1

    destination = Path(tempfile.mkdtemp(prefix="carto-install-")) / "Carto"
    donnees = Path(os.environ.get("LOCALAPPDATA", "")) / "Carto"
    donnees_avant = donnees.is_dir()

    print(f"installation vers : {destination}", flush=True)
    resultat = powershell(
        "-File", str(SCRIPT), "-Destination", str(destination), "-Silencieux"
    )
    print(resultat.stdout.strip(), flush=True)
    if resultat.returncode != 0:
        print(resultat.stderr[-2000:], flush=True)
        return 1

    constats = {
        "programme installé": (destination / "Carto.exe").is_file(),
        "ressources copiées": (
            destination / "_internal" / "carto" / "resources" / "map.html"
        ).is_file(),
        "raccourci menu Démarrer": MENU.is_file(),
        "raccourci Bureau": BUREAU.is_file(),
        "entrée de désinstallation": cle_existe(),
        "désinstalleur déposé": (destination / "desinstaller.ps1").is_file(),
    }
    for libelle, ok in constats.items():
        print(f"  [{'ok ' if ok else 'ECHEC'}] {libelle}", flush=True)

    print("\ndésinstallation...", flush=True)
    retrait = powershell(
        "-File", str(SCRIPT), "-Desinstaller",
        "-Destination", str(destination), "-Silencieux",
    )
    print(retrait.stdout.strip(), flush=True)
    time.sleep(5)   # la suppression du dossier est différée

    apres = {
        "raccourci menu Démarrer retiré": not MENU.is_file(),
        "raccourci Bureau retiré": not BUREAU.is_file(),
        "entrée de désinstallation retirée": not cle_existe(),
        "programme retiré": not (destination / "Carto.exe").is_file(),
        "traces de l'utilisateur conservées": donnees.is_dir() or not donnees_avant,
    }
    for libelle, ok in apres.items():
        print(f"  [{'ok ' if ok else 'ECHEC'}] {libelle}", flush=True)

    echecs = sum(1 for ok in list(constats.values()) + list(apres.values()) if not ok)
    print("\nRESULTAT :",
          "installation et desinstallation conformes" if not echecs
          else f"{echecs} anomalie(s)", flush=True)
    return 0 if not echecs else 1


if __name__ == "__main__":
    sys.exit(main())
