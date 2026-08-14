"""Emplacement des données utilisateur.

Les données (base SQLite) sont stockées hors du répertoire d'installation afin
qu'une mise à jour du logiciel ne puisse jamais les effacer :
    C:\\Users\\[Nom]\\AppData\\Local\\GeoCairn\\
La variable d'environnement GEOCAIRN_DATA_DIR permet de surcharger cet
emplacement (utilisée par les tests).

Le logiciel s'est d'abord appelé Carto et rangeait ses traces à côté, dans
`...\\Local\\Carto\\carto.db`. Une installation existante les retrouve donc au
premier lancement sous le nouveau nom, sans rien demander à l'utilisateur.
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

from . import APP_SLUG

ENV_DATA_DIR = "GEOCAIRN_DATA_DIR"
DB_FILENAME = "geocairn.db"

#: Emplacement et nom de fichier de l'époque « Carto ».
ANCIEN_DOSSIER = "Carto"
ANCIENNE_BASE = "carto.db"

#: Fichiers annexes que SQLite laisse à côté de la base quand le programme
#: précédent ne s'est pas fermé proprement. Repris avec elle : la base seule
#: serait amputée des dernières traces enregistrées.
SUFFIXES_SQLITE = ("", "-wal", "-shm")


def is_frozen() -> bool:
    """Vrai si le programme tourne depuis l'exécutable produit par PyInstaller."""
    return getattr(sys, "frozen", False)


def install_dir() -> Path:
    """Répertoire d'où le logiciel s'exécute.

    C'est celui qu'une mise à jour remplace ; aucune donnée utilisateur ne doit
    s'y trouver.
    """
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def base_dir() -> Path:
    """Répertoire qui contient le dossier de données du logiciel."""
    if os.name == "nt":
        local = os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local")
        return Path(local)
    base = os.environ.get("XDG_DATA_HOME") or (Path.home() / ".local" / "share")
    return Path(base)


def reprendre_donnees_heritees(ancien: Path, nouveau: Path) -> bool:
    """Recopie la base de l'ancien nom vers le nouveau. Vrai si reprise.

    Une copie, et non un déplacement : l'ancien dossier reste en place comme
    filet, au cas où la reprise tomberait au mauvais moment. L'opération ne
    fait rien si la nouvelle base existe déjà, et peut donc être tentée à
    chaque lancement.
    """
    source = ancien / ANCIENNE_BASE
    cible = nouveau / DB_FILENAME
    if cible.exists() or not source.is_file():
        return False

    try:
        for suffixe in SUFFIXES_SQLITE:
            annexe = source.with_name(ANCIENNE_BASE + suffixe)
            if annexe.is_file():
                shutil.copy2(annexe, cible.with_name(DB_FILENAME + suffixe))
    except OSError:
        # Un échec ne doit pas empêcher le programme de démarrer : il ouvrira
        # une bibliothèque vide, et les traces restent dans l'ancien dossier.
        return False
    return True


def data_dir() -> Path:
    """Répertoire des données utilisateur, créé au besoin."""
    override = os.environ.get(ENV_DATA_DIR)
    if override:
        path = Path(override)
        path.mkdir(parents=True, exist_ok=True)
        return path

    base = base_dir()
    path = base / APP_SLUG
    path.mkdir(parents=True, exist_ok=True)
    reprendre_donnees_heritees(base / ANCIEN_DOSSIER, path)
    return path


def db_path() -> Path:
    """Chemin complet du fichier de base de données."""
    return data_dir() / DB_FILENAME


def resource_dir() -> Path:
    """Répertoire des ressources embarquées (html, JavaScript, feuilles).

    PyInstaller les dépose à côté de l'exécutable — ou, en mode fichier unique,
    dans le dossier temporaire d'extraction désigné par `sys._MEIPASS`.
    """
    if is_frozen():
        base = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
        return base / "geocairn" / "resources"
    return Path(__file__).resolve().parent / "resources"


def resource_path(*parts: str) -> Path:
    """Chemin d'une ressource embarquée (html, js, icônes)."""
    return resource_dir() / Path(*parts)
