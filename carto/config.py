"""Emplacement des données utilisateur.

Les données (base SQLite) sont stockées hors du répertoire d'installation afin
qu'une mise à jour du logiciel ne puisse jamais les effacer :
    C:\\Users\\[Nom]\\AppData\\Local\\Carto\\
La variable d'environnement CARTO_DATA_DIR permet de surcharger cet emplacement
(utilisée par les tests).
"""

from __future__ import annotations

import os
from pathlib import Path

from . import APP_NAME

ENV_DATA_DIR = "CARTO_DATA_DIR"
DB_FILENAME = "carto.db"


def data_dir() -> Path:
    """Répertoire des données utilisateur, créé au besoin."""
    override = os.environ.get(ENV_DATA_DIR)
    if override:
        path = Path(override)
    elif os.name == "nt":
        local = os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local")
        path = Path(local) / APP_NAME
    else:
        base = os.environ.get("XDG_DATA_HOME") or (Path.home() / ".local" / "share")
        path = Path(base) / APP_NAME

    path.mkdir(parents=True, exist_ok=True)
    return path


def db_path() -> Path:
    """Chemin complet du fichier de base de données."""
    return data_dir() / DB_FILENAME


def resource_path(*parts: str) -> Path:
    """Chemin d'une ressource embarquée (html, js, icônes)."""
    return Path(__file__).resolve().parent / "resources" / Path(*parts)
