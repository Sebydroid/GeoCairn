"""Fixtures communes aux tests."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Les tests d'interface tournent sans écran ni GPU.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault(
    "QTWEBENGINE_CHROMIUM_FLAGS", "--disable-gpu --no-sandbox --disable-dev-shm-usage"
)

from carto.database import Database  # noqa: E402
from carto.models import Point  # noqa: E402


@pytest.fixture(autouse=True)
def sans_reseau(monkeypatch):
    """Aucun test ne doit dépendre du service altimétrique de l'IGN.

    Dessiner un point demande son altitude en arrière-plan : sans ce garde-fou,
    la simple saisie d'une trace dans un test lançait de vraies requêtes vers
    Internet. La suite devenait tributaire d'un service extérieur, et pouvait
    s'y attarder. Les tests qui vérifient la récupération d'altitude
    fournissent leur propre transport et ne sont pas concernés.
    """
    def refuser(_url):
        raise OSError("réseau volontairement coupé pendant les tests")

    monkeypatch.setattr("carto.elevation._default_fetch", refuser)


@pytest.fixture
def db(tmp_path, monkeypatch):
    """Base SQLite isolée dans un répertoire temporaire."""
    monkeypatch.setenv("CARTO_DATA_DIR", str(tmp_path / "data"))
    database = Database(tmp_path / "data" / "test.db")
    yield database
    database.close()


@pytest.fixture
def sample_points() -> list[Point]:
    """Un petit tracé de 4 points (non fermé)."""
    return [
        Point(48.9300, 1.4400, 70.0),
        Point(48.9310, 1.4420, 72.5),
        Point(48.9325, 1.4415, 75.0),
        Point(48.9330, 1.4390, 71.0),
    ]
