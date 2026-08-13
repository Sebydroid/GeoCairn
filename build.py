"""Construit l'exécutable Windows, l'installeur, et contrôle la livraison.

    python build.py                  # version fenêtrée, dans dist/Carto/
    python build.py --console        # variante avec console, pour diagnostiquer
    python build.py --installateur   # + installeur .exe (Inno Setup)
    python build.py --archive        # + archive ZIP prête à distribuer

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


def chemin_assaini() -> str:
    """PATH réduit au système et à l'environnement virtuel du projet.

    La construction se fait déjà depuis le venv, mais cela ne suffit pas :
    pour résoudre les dépendances des bibliothèques natives, PyInstaller
    parcourt le PATH du système. C'est par là qu'il ramassait les
    bibliothèques d'Anaconda. En restreignant le PATH, la contamination est
    empêchée à la source plutôt que corrigée après coup.
    """
    systeme = Path(os.environ.get("SystemRoot", r"C:\Windows"))
    garde = [
        str(Path(sys.executable).parent),      # Scripts du venv
        str(systeme / "System32"),
        str(systeme),
        str(systeme / "System32" / "Wbem"),
    ]
    return os.pathsep.join(garde)


def taille_lisible(dossier: Path) -> str:
    octets = sum(f.stat().st_size for f in dossier.rglob("*") if f.is_file())
    return f"{octets / 1024 / 1024:.0f} Mo"


def construire(console: bool) -> Path:
    sortie = RACINE / ("dist-console" if console else "dist")
    travail = RACINE / ("build-console" if console else "build")
    for chemin in (sortie, travail):
        shutil.rmtree(chemin, ignore_errors=True)

    environnement = dict(os.environ, PATH=chemin_assaini())
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
    sortie = ((resultat.stdout or "") + (resultat.stderr or "")).strip()
    afficher(sortie)

    plaintes = reperer_plaintes(sortie)
    if plaintes:
        afficher("\nle programme se plaint de sa livraison :")
        for ligne in plaintes:
            afficher(f"  {ligne}")
        return False

    return resultat.returncode == 0


#: Traces d'une livraison incomplète que le programme signale sans pour autant
#: s'arrêter : sans cela, une ressource oubliée passerait inaperçue.
PLAINTES = (
    "could not find",
    "will not be correct",
    "failed to",
    "no such file",
    "introuvable",
    "qt.qpa",
)


def reperer_plaintes(sortie: str) -> list[str]:
    """Lignes de la sortie qui trahissent une livraison bancale."""
    return [
        ligne.strip()
        for ligne in sortie.splitlines()
        if any(motif in ligne.lower() for motif in PLAINTES)
    ]


def version() -> str:
    """Version déclarée par l'application, sans l'importer."""
    source = (RACINE / "carto" / "__init__.py").read_text(encoding="utf-8")
    for ligne in source.splitlines():
        if ligne.startswith("APP_VERSION"):
            return ligne.split("=", 1)[1].strip().strip('"').strip("'")
    return "0.0.0"


def joindre_scripts_installation(livraison: Path) -> None:
    """Dépose les scripts d'installation à côté du programme."""
    outils = RACINE / "outils"
    for nom in ("Installer.bat", "Desinstaller.bat", "installer.ps1"):
        source = outils / nom
        if source.is_file():
            shutil.copy2(source, livraison / nom)


def archiver(livraison: Path) -> Path:
    """Archive ZIP prête à être copiée sur une clé ou envoyée par courriel."""
    sortie = RACINE / "dist-installeur"
    sortie.mkdir(exist_ok=True)
    base = sortie / f"Carto-{version()}"
    afficher("\ncreation de l'archive...")
    chemin = Path(
        shutil.make_archive(str(base), "zip", livraison.parent, livraison.name)
    )
    afficher(f"archive : {chemin}  ({chemin.stat().st_size / 1024 / 1024:.0f} Mo)")
    return chemin


def trouver_iscc() -> Path | None:
    """Compilateur Inno Setup, s'il est installé.

    L'outil s'installe aussi bien pour la machine que pour le seul utilisateur
    — c'est le cas d'une installation par winget, qui le dépose alors dans
    AppData. Les deux emplacements sont donc explorés, et le registre sert de
    dernier recours.
    """
    racines = [
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs",
        Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")),
        Path(os.environ.get("ProgramFiles", r"C:\Program Files")),
    ]
    candidats = []
    trouve = shutil.which("iscc")
    if trouve:
        candidats.append(Path(trouve))
    for racine in racines:
        for version in ("Inno Setup 6", "Inno Setup 5"):
            candidats.append(racine / version / "ISCC.exe")

    candidats.extend(_iscc_depuis_le_registre())
    return next((c for c in candidats if c.is_file()), None)


def _iscc_depuis_le_registre() -> list[Path]:
    """Emplacements déclarés par le programme d'installation d'Inno Setup."""
    try:
        import winreg
    except ImportError:
        return []

    trouves = []
    cles = [
        (winreg.HKEY_CURRENT_USER,
         r"Software\Microsoft\Windows\CurrentVersion\Uninstall\Inno Setup 6_is1"),
        (winreg.HKEY_LOCAL_MACHINE,
         r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\Inno Setup 6_is1"),
        (winreg.HKEY_LOCAL_MACHINE,
         r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"
         r"\Inno Setup 6_is1"),
    ]
    for racine, chemin in cles:
        try:
            with winreg.OpenKey(racine, chemin) as cle:
                dossier, _type = winreg.QueryValueEx(cle, "InstallLocation")
                trouves.append(Path(dossier) / "ISCC.exe")
        except OSError:
            continue
    return trouves


def construire_installateur(livraison: Path) -> bool:
    """Produit l'installeur .exe, si Inno Setup est disponible."""
    iscc = trouver_iscc()
    if iscc is None:
        afficher(
            "\nInno Setup n'est pas installe : l'installeur .exe ne peut pas\n"
            "etre construit. C'est un outil gratuit, a installer une seule fois :\n"
            "    winget install JRSoftware.InnoSetup\n"
            "L'archive ZIP et son script Installer.bat restent utilisables tels\n"
            "quels, sans aucun outil supplementaire."
        )
        return False

    afficher(f"\nconstruction de l'installeur ({iscc})...")
    resultat = subprocess.run(
        [str(iscc), f"/DMaVersion={version()}", str(RACINE / "installateur.iss")],
        cwd=RACINE, capture_output=True, text=True,
        encoding="utf-8", errors="replace",
    )
    if resultat.returncode != 0:
        afficher(resultat.stdout[-3000:])
        afficher(resultat.stderr[-3000:])
        return False

    produit = RACINE / "dist-installeur" / f"Carto-{version()}-installation.exe"
    if produit.is_file():
        afficher(
            f"installeur : {produit}  "
            f"({produit.stat().st_size / 1024 / 1024:.0f} Mo)"
        )
    return True


def main() -> int:
    console = "--console" in sys.argv
    livraison = construire(console)
    joindre_scripts_installation(livraison)

    if console:
        ok = controler(livraison)
    else:
        # La version fenêtrée n'écrit rien sur la sortie standard : on contrôle
        # avec la variante console, construite pour l'occasion.
        afficher("\ncontrole de la livraison via la variante console...")
        ok = controler(construire(True))

    if ok and "--archive" in sys.argv:
        archiver(livraison)
    if ok and "--installateur" in sys.argv:
        construire_installateur(livraison)

    afficher("\nRESULTAT : " + ("livraison conforme" if ok else "ANOMALIE"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
