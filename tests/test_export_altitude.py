"""Choix de l'altitude au moment de l'export GPX.

Une trace peut porter deux altitudes : celle du fichier dont elle vient, et
celle calculée par le service de l'IGN. Le format GPX n'a qu'une balise
« ele » : quand les deux existent, c'est à l'utilisateur de trancher.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET

import pytest
from PyQt6.QtWidgets import QInputDialog, QMessageBox

from geocairn.app import create_app
from geocairn.database import Database
from geocairn.gpx import (
    ELE_AUTO,
    ELE_FICHIER,
    ELE_IGN,
    GPX_NS,
    LIBELLES_ELEVATION,
    altitudes_disponibles,
    build_gpx,
)
from geocairn.models import Point
from geocairn.ui.main_window import MainWindow

NS = {"gpx": GPX_NS}

#: Trace importée : chaque point porte l'altitude de son fichier d'origine.
IMPORTEE = [
    Point(48.930, 1.440, 10.0),
    Point(48.931, 1.442, 20.0),
    Point(48.932, 1.441, 30.0),
]

#: Trace dessinée à la main : aucune altitude d'origine.
DESSINEE = [Point(48.930, 1.440), Point(48.931, 1.442), Point(48.932, 1.441)]

IGN = [70.0, 72.0, 75.0]


@pytest.fixture(scope="session")
def qapp():
    app = create_app(["geocairn-tests"])
    yield app
    app.processEvents()


@pytest.fixture(scope="module")
def _fenetre(qapp, tmp_path_factory):
    """Fenêtre partagée : une par test épuiserait le moteur web."""
    database = Database(tmp_path_factory.mktemp("export") / "geocairn.db")
    win = MainWindow(db=database)
    yield win
    win.close()


@pytest.fixture
def window(_fenetre, monkeypatch):
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: None))
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: None))
    for track in _fenetre.db.list_tracks(None):
        _fenetre.db.delete_track(track.id)
    _fenetre.tree_panel.refresh()
    yield _fenetre


# ------------------------------------------------------------- outillage


def altitudes_du_fichier(chemin) -> list[float]:
    racine = ET.parse(chemin).getroot()
    return [
        float(e.text)
        for e in racine.findall("gpx:trk/gpx:trkseg/gpx:trkpt/gpx:ele", NS)
    ]


def choix_fige(monkeypatch, rang: int | None, demandes: list) -> None:
    """Remplace la boîte de choix ; `rang=None` simule un abandon."""

    def faux_choix(_parent, _titre, _libelle, items, _courant, _editable):
        demandes.append(list(items))
        if rang is None:
            return ("", False)
        return (items[rang], True)

    monkeypatch.setattr(QInputDialog, "getItem", staticmethod(faux_choix))


@pytest.fixture
def trace_a_deux_altitudes(window):
    """Trace importée avec ses altitudes, puis complétée par le service IGN."""
    track_id = window.db.create_track("Deux altitudes", points=IMPORTEE)
    window.db.set_service_elevations(track_id, IGN)
    window.tree_panel.refresh()
    return track_id


# --------------------------------------------- construction du fichier


def test_altitudes_disponibles_les_reconnait():
    assert altitudes_disponibles(IMPORTEE) == [ELE_FICHIER]
    assert altitudes_disponibles(DESSINEE) == []

    deux = [
        Point(p.lat, p.lon, p.ele, None, ign) for p, ign in zip(IMPORTEE, IGN)
    ]
    assert altitudes_disponibles(deux) == [ELE_FICHIER, ELE_IGN]


@pytest.mark.parametrize(
    "source, attendu",
    [
        (ELE_FICHIER, [10.0, 20.0, 30.0]),
        (ELE_IGN, [70.0, 72.0, 75.0]),
        (ELE_AUTO, [10.0, 20.0, 30.0]),
    ],
)
def test_le_fichier_ecrit_l_altitude_demandee(source, attendu, tmp_path):
    points = [
        Point(p.lat, p.lon, p.ele, None, ign) for p, ign in zip(IMPORTEE, IGN)
    ]

    racine = build_gpx("Trace", points, elevation=source).getroot()

    valeurs = [
        float(e.text)
        for e in racine.findall("gpx:trk/gpx:trkseg/gpx:trkpt/gpx:ele", NS)
    ]
    assert valeurs == attendu


# ------------------------------------------------ choix à l'exportation


def test_deux_altitudes_font_poser_la_question(
    window, tmp_path, monkeypatch, trace_a_deux_altitudes
):
    """Les deux origines sont proposées, dans un ordre stable."""
    demandes: list = []
    choix_fige(monkeypatch, 0, demandes)   # altitude d'origine
    cible = tmp_path / "origine.gpx"

    window.export_track(trace_a_deux_altitudes, str(cible))

    assert demandes == [
        [LIBELLES_ELEVATION[ELE_FICHIER], LIBELLES_ELEVATION[ELE_IGN]]
    ]
    assert altitudes_du_fichier(cible) == [10.0, 20.0, 30.0]


def test_le_choix_de_l_altitude_ign_est_respecte(
    window, tmp_path, monkeypatch, trace_a_deux_altitudes
):
    demandes: list = []
    choix_fige(monkeypatch, 1, demandes)   # altitude IGN
    cible = tmp_path / "ign.gpx"

    window.export_track(trace_a_deux_altitudes, str(cible))

    assert altitudes_du_fichier(cible) == [70.0, 72.0, 75.0]


def test_renoncer_au_choix_annule_l_export(
    window, tmp_path, monkeypatch, trace_a_deux_altitudes
):
    """Abandonner la question abandonne l'export, sans écrire de fichier."""
    demandes: list = []
    choix_fige(monkeypatch, None, demandes)
    cible = tmp_path / "rien.gpx"

    assert window.export_track(trace_a_deux_altitudes, str(cible)) is None
    assert not cible.exists()


def test_le_choix_precede_l_enregistrement(
    window, monkeypatch, trace_a_deux_altitudes
):
    """L'altitude se choisit avant le fichier : le dernier geste est « Enregistrer »."""
    ordre: list[str] = []
    choix_fige(monkeypatch, 0, [])
    vrai_choix = QInputDialog.getItem

    def choix(*args, **kwargs):
        ordre.append("altitude")
        return vrai_choix(*args, **kwargs)

    from PyQt6.QtWidgets import QFileDialog

    def enregistrer_sous(*_args, **_kwargs):
        ordre.append("fichier")
        return ("", "")            # abandon : rien n'est écrit

    monkeypatch.setattr(QInputDialog, "getItem", staticmethod(choix))
    monkeypatch.setattr(
        QFileDialog, "getSaveFileName", staticmethod(enregistrer_sous)
    )

    assert window.export_track(trace_a_deux_altitudes) is None
    assert ordre == ["altitude", "fichier"]


def test_une_seule_altitude_ne_fait_rien_demander(
    window, tmp_path, monkeypatch
):
    """Sans choix à faire, l'export ne doit pas retenir l'utilisateur."""
    track_id = window.db.create_track("Importée", points=IMPORTEE)
    demandes: list = []
    choix_fige(monkeypatch, 0, demandes)
    cible = tmp_path / "sans-question.gpx"

    window.export_track(track_id, str(cible))

    assert demandes == []
    assert altitudes_du_fichier(cible) == [10.0, 20.0, 30.0]


def test_une_trace_dessinee_exporte_l_altitude_ign_sans_question(
    window, tmp_path, monkeypatch
):
    track_id = window.db.create_track("Dessinée", points=DESSINEE)
    window.db.set_service_elevations(track_id, IGN)
    demandes: list = []
    choix_fige(monkeypatch, 0, demandes)
    cible = tmp_path / "dessinee.gpx"

    window.export_track(track_id, str(cible))

    assert demandes == []
    assert altitudes_du_fichier(cible) == [70.0, 72.0, 75.0]


def test_une_trace_sans_altitude_n_ecrit_aucune_balise(
    window, tmp_path, monkeypatch
):
    track_id = window.db.create_track("Nue", points=DESSINEE)
    demandes: list = []
    choix_fige(monkeypatch, 0, demandes)
    cible = tmp_path / "nue.gpx"

    window.export_track(track_id, str(cible))

    assert demandes == []
    assert altitudes_du_fichier(cible) == []


def test_le_compte_rendu_precise_l_altitude_retenue(
    window, tmp_path, monkeypatch, trace_a_deux_altitudes
):
    choix_fige(monkeypatch, 1, [])

    window.export_track(trace_a_deux_altitudes, str(tmp_path / "x.gpx"))

    assert "ign" in window.status_label.text().lower()
