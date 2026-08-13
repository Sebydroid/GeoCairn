"""Vérifie l'installeur .exe produit par Inno Setup.

    python tests/check_installateur.py

Installe en mode silencieux dans un répertoire temporaire, contrôle le
programme et l'entrée de désinstallation, lance l'autotest du programme
installé, puis désinstalle et vérifie que tout est retiré.

Diagnostic hors pytest : il installe réellement le logiciel, puis remet la
machine en état.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
CLE = (
    r"HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall"
    r"\{8E2C7A34-5F41-4B9E-9C3D-0A6B1D5E7F20}_is1"
)


def afficher(texte: str) -> None:
    """Écrit sans buter sur un caractère absent de la console Windows."""
    encodage = sys.stdout.encoding or "utf-8"
    print(texte.encode(encodage, "replace").decode(encodage), flush=True)


def installeur() -> Path | None:
    dossier = RACINE / "dist-installeur"
    candidats = sorted(dossier.glob("Carto-*-installation.exe"))
    return candidats[-1] if candidats else None


def powershell(commande: str) -> str:
    sortie = subprocess.run(
        ["powershell", "-NoProfile", "-Command", commande],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=300,
    )
    return sortie.stdout.strip()


def main() -> int:
    exe = installeur()
    if exe is None:
        afficher("aucun installeur : lancer d'abord "
                 "python build.py --installateur")
        return 1

    destination = Path(tempfile.mkdtemp(prefix="carto-setup-")) / "Carto"
    afficher(f"installeur  : {exe.name}  "
             f"({exe.stat().st_size / 1024 / 1024:.0f} Mo)")
    afficher(f"destination : {destination}")

    pose = subprocess.run(
        [str(exe), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART",
         "/NOICONS", f"/DIR={destination}"],
        capture_output=True, timeout=600,
    )
    afficher(f"installation : code {pose.returncode}")

    constats = {
        "programme installé": (destination / "Carto.exe").is_file(),
        "ressources copiées": (
            destination / "_internal" / "carto" / "resources" / "map.html"
        ).is_file(),
        "désinstalleur présent": any(destination.glob("unins*.exe")),
        "entrée de désinstallation": "True" in powershell(f"Test-Path '{CLE}'"),
    }

    # Le programme installé doit être opérationnel, pas seulement présent.
    if constats["programme installé"]:
        controle = subprocess.run(
            [str(destination / "Carto.exe"), "--autotest"],
            env=dict(os.environ,
                     CARTO_DATA_DIR=tempfile.mkdtemp(prefix="carto-donnees-")),
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=180,
        )
        constats["autotest du programme installé"] = controle.returncode == 0
        for ligne in (controle.stdout or "").splitlines():
            afficher(f"    {ligne}")

    for libelle, ok in constats.items():
        afficher(f"  [{'ok ' if ok else 'ECHEC'}] {libelle}")

    afficher("\ndesinstallation...")
    desinstalleur = next(iter(destination.glob("unins*.exe")), None)
    if desinstalleur is not None:
        subprocess.run(
            [str(desinstalleur), "/VERYSILENT", "/SUPPRESSMSGBOXES"],
            capture_output=True, timeout=600,
        )
        time.sleep(8)

    apres = {
        "programme retiré": not (destination / "Carto.exe").is_file(),
        "entrée de désinstallation retirée":
            "False" in powershell(f"Test-Path '{CLE}'"),
    }
    for libelle, ok in apres.items():
        afficher(f"  [{'ok ' if ok else 'ECHEC'}] {libelle}")

    echecs = sum(
        1 for ok in list(constats.values()) + list(apres.values()) if not ok
    )
    afficher("\nRESULTAT : " + ("installeur conforme" if not echecs
                                else f"{echecs} anomalie(s)"))
    return 0 if not echecs else 1


if __name__ == "__main__":
    sys.exit(main())
