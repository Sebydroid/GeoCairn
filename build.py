"""Construit l'exécutable Windows et contrôle la livraison.

    python build.py              # version fenêtrée, dans dist/Carto/
    python build.py --console    # variante avec console, pour diagnostiquer

Enchaîne la construction PyInstaller puis l'autotest du programme livré : une
livraison incomplète — ressource oubliée, bibliothèque étrangère embarquée —
est ainsi détectée ici plutôt que chez l'utilisateur.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

RACINE = Path(__file__).resolve().parent
SPEC = RACINE / "carto.spec"


def afficher(texte: str) -> None:
    """Écrit sans buter sur un caractère absent de la console Windows."""
    encodage = sys.stdout.encoding or "utf-8"
    print(texte.encode(encodage, "replace").decode(encodage), flush=True)


def taille_lisible(dossier: Path) -> str:
    octets = sum(f.stat().st_size for f in dossier.rglob("*") if f.is_file())
    return f"{octets / 1024 / 1024:.0f} Mo"


def construire(console: bool) -> Path:
    sortie = RACINE / ("dist-console" if console else "dist")
    travail = RACINE / ("build-console" if console else "build")
    for chemin in (sortie, travail):
        shutil.rmtree(chemin, ignore_errors=True)

    environnement = dict(os.environ)
    if console:
        environnement["CARTO_CONSOLE"] = "1"

    afficher(f"construction ({'console' if console else 'fenetree'})...")
    debut = time.perf_counter()
    resultat = subprocess.run(
        [
            sys.executable, "-m", "PyInstaller", str(SPEC), "--noconfirm",
            "--distpath", str(sortie), "--workpath", str(travail),
        ],
        cwd=RACINE,
        env=environnement,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if resultat.returncode != 0:
        afficher(resultat.stdout[-4000:])
        afficher(resultat.stderr[-4000:])
        raise SystemExit("la construction a echoue")

    ecartes = [
        ligne.strip()
        for ligne in resultat.stdout.splitlines()
        if "[carto.spec]" in ligne
    ]
    if ecartes:
        afficher(f"  {len(ecartes)} bibliotheque(s) etrangere(s) ecartee(s)")
        for ligne in ecartes[:5]:
            afficher("  " + ligne)
        if len(ecartes) > 5:
            afficher(f"  ... et {len(ecartes) - 5} autres")

    afficher(f"terminee en {time.perf_counter() - debut:.0f} s")
    return sortie / "Carto"


def controler(livraison: Path) -> bool:
    """Lance l'autotest du programme livré, dans des données isolées."""
    executable = livraison / "Carto.exe"
    if not executable.is_file():
        afficher(f"executable introuvable : {executable}")
        return False

    afficher(f"\nlivraison : {livraison}  ({taille_lisible(livraison)})")
    environnement = dict(
        os.environ, CARTO_DATA_DIR=tempfile.mkdtemp(prefix="carto-controle-")
    )
    resultat = subprocess.run(
        [str(executable), "--autotest"],
        env=environnement,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=180,
    )
    afficher(((resultat.stdout or "") + (resultat.stderr or "")).strip())
    return resultat.returncode == 0


def main() -> int:
    console = "--console" in sys.argv
    livraison = construire(console)

    if console:
        ok = controler(livraison)
    else:
        # La version fenêtrée n'écrit rien sur la sortie standard : on contrôle
        # avec la variante console, construite pour l'occasion.
        afficher("\ncontrole de la livraison via la variante console...")
        ok = controler(construire(True))

    afficher("\nRESULTAT : " + ("livraison conforme" if ok else "ANOMALIE"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
