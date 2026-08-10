"""Sécurité des données : emplacement du fichier de base (Jalon 1 / Jalon 7)."""

from __future__ import annotations

import os
from pathlib import Path

from carto import config


def test_data_dir_hors_du_repertoire_du_logiciel(monkeypatch, tmp_path):
    """Les données ne doivent jamais vivre dans le dossier du code source."""
    monkeypatch.delenv(config.ENV_DATA_DIR, raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "AppData" / "Local"))

    directory = config.data_dir()
    project_root = Path(config.__file__).resolve().parent.parent

    assert directory.exists()
    assert project_root not in directory.resolve().parents
    assert directory.resolve() != project_root


def test_data_dir_utilise_localappdata(monkeypatch, tmp_path):
    monkeypatch.delenv(config.ENV_DATA_DIR, raising=False)
    local = tmp_path / "AppData" / "Local"
    monkeypatch.setenv("LOCALAPPDATA", str(local))

    if os.name == "nt":
        assert config.data_dir() == local / "Carto"
    else:
        assert config.data_dir().name == "Carto"


def test_override_par_variable_denvironnement(monkeypatch, tmp_path):
    monkeypatch.setenv(config.ENV_DATA_DIR, str(tmp_path / "ailleurs"))
    assert config.data_dir() == tmp_path / "ailleurs"
    assert config.db_path() == tmp_path / "ailleurs" / "carto.db"


def test_ressource_map_html_presente():
    assert config.resource_path("map.html").is_file()
