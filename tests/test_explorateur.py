"""Arborescence façon explorateur, centrage sur un point, profil multiple."""

from __future__ import annotations

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QKeyEvent
from PyQt6.QtWidgets import QInputDialog, QMessageBox

from carto.app import create_app
from carto.database import Database
from carto.models import Point
from carto.ui.main_window import MainWindow
from carto.ui.profile_panel import (
    SOURCE_ELE_FICHIER,
    SOURCE_ELE_SERVICE,
    SOURCE_VITESSE,
)
from carto.ui.tree_panel import KIND_FOLDER, KIND_TRACK
from tests.test_ui import run_js_sync, wait_for

QUATRE = [
    Point(48.930, 1.440, 70.0, "2026-08-10T09:00:00Z"),
    Point(48.931, 1.442, 75.0, "2026-08-10T09:01:00Z"),
    Point(48.932, 1.441, 80.0, "2026-08-10T09:02:00Z"),
    Point(48.933, 1.439, 78.0, "2026-08-10T09:03:00Z"),
]


@pytest.fixture(scope="session")
def qapp():
    app = create_app(["carto-tests"])
    yield app
    app.processEvents()


@pytest.fixture(scope="session")
def window(qapp, tmp_path_factory):
    database = Database(tmp_path_factory.mktemp("explorateur") / "carto.db")
    win = MainWindow(db=database)
    win.show()
    assert wait_for(lambda: win.map_view.is_ready), "carte non chargée"
    yield win
    win.close()


@pytest.fixture(autouse=True)
def etat_vierge(window, monkeypatch):
    monkeypatch.setattr(
        QMessageBox, "question",
        staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes),
    )
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: None))
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: None))

    for track in window.db.list_tracks(None):
        window.db.delete_track(track.id)
    for folder in window.db.list_folders(None):
        window.db.delete_folder(folder.id)
    window.visible_tracks.clear()
    window.map_view.clear_tracks()
    window.map_view.clear_focus()
    window.draft.reset()
    window.set_edit_mode(False)
    window.map_view.clear_draft()
    window.tree_panel.refresh()
    window._update_draft_actions()
    yield


def enregistrer(window, nom="Rallye", points=None) -> int:
    track_id = window.db.create_track(nom, points=points or QUATRE)
    window.tree_panel.refresh()
    return track_id


def touche(widget, cle) -> None:
    widget.keyPressEvent(
        QKeyEvent(QKeyEvent.Type.KeyPress, cle, Qt.KeyboardModifier.NoModifier)
    )


# ------------------------------------------------- raccourcis clavier


def test_f2_renomme_l_element(window, monkeypatch):
    track_id = enregistrer(window, "Ancien")
    window.tree_panel.select_track(track_id)
    monkeypatch.setattr(
        QInputDialog, "getText", staticmethod(lambda *a, **k: ("Nouveau", True))
    )

    touche(window.tree_panel.tree, Qt.Key.Key_F2)

    assert window.db.get_track(track_id).name == "Nouveau"


def test_f2_sur_un_dossier(window, monkeypatch):
    folder_id = window.db.create_folder("Ancien")
    window.tree_panel.refresh()
    window.tree_panel.select_folder(folder_id)
    monkeypatch.setattr(
        QInputDialog, "getText", staticmethod(lambda *a, **k: ("Nouveau", True))
    )

    touche(window.tree_panel.tree, Qt.Key.Key_F2)

    assert window.db.get_folder(folder_id).name == "Nouveau"


def test_suppr_supprime_avec_confirmation(window, monkeypatch):
    track_id = enregistrer(window)
    window.tree_panel.select_track(track_id)
    demandes = []
    monkeypatch.setattr(
        QMessageBox, "question",
        staticmethod(
            lambda _p, titre, texte, *a, **k: (
                demandes.append(texte), QMessageBox.StandardButton.Yes
            )[1]
        ),
    )

    touche(window.tree_panel.tree, Qt.Key.Key_Delete)

    assert demandes, "la suppression doit demander confirmation"
    assert window.db.get_track(track_id) is None


def test_suppr_annulee_ne_supprime_rien(window, monkeypatch):
    track_id = enregistrer(window)
    window.tree_panel.select_track(track_id)
    monkeypatch.setattr(
        QMessageBox, "question",
        staticmethod(lambda *a, **k: QMessageBox.StandardButton.No),
    )

    touche(window.tree_panel.tree, Qt.Key.Key_Delete)

    assert window.db.get_track(track_id) is not None


# ------------------------------------------------- sélection multiple


def test_selection_multiple_possible(window):
    from PyQt6.QtWidgets import QAbstractItemView

    assert window.tree_panel.tree.selectionMode() == (
        QAbstractItemView.SelectionMode.ExtendedSelection
    )


def test_suppression_de_plusieurs_traces(window):
    a = enregistrer(window, "Aller")
    b = enregistrer(window, "Retour")
    c = enregistrer(window, "Gardée")
    panel = window.tree_panel
    panel.find_item(KIND_TRACK, a).setSelected(True)
    panel.find_item(KIND_TRACK, b).setSelected(True)

    assert panel.delete_selected(confirm=False) is True

    assert window.db.get_track(a) is None
    assert window.db.get_track(b) is None
    assert window.db.get_track(c) is not None


def test_suppression_melangeant_dossier_et_trace(window):
    dossier = window.db.create_folder("Rallye")
    dedans = window.db.create_track("Dedans", folder_id=dossier, points=QUATRE)
    dehors = window.db.create_track("Dehors", points=QUATRE)
    panel = window.tree_panel
    panel.refresh()
    panel.find_item(KIND_FOLDER, dossier).setSelected(True)
    panel.find_item(KIND_TRACK, dehors).setSelected(True)

    assert panel.delete_selected(confirm=False) is True

    assert window.db.get_folder(dossier) is None
    assert window.db.get_track(dedans) is None
    assert window.db.get_track(dehors) is None


def test_suppression_d_un_dossier_et_de_son_contenu_selectionne(window):
    """Sélectionner le dossier et une trace qu'il contient ne doit pas casser."""
    dossier = window.db.create_folder("Rallye")
    dedans = window.db.create_track("Dedans", folder_id=dossier, points=QUATRE)
    panel = window.tree_panel
    panel.refresh()
    panel.find_item(KIND_FOLDER, dossier).setExpanded(True)
    panel.find_item(KIND_FOLDER, dossier).setSelected(True)
    panel.find_item(KIND_TRACK, dedans).setSelected(True)

    assert panel.delete_selected(confirm=False) is True

    assert window.db.get_folder(dossier) is None
    assert window.db.get_track(dedans) is None


def test_les_traces_supprimees_en_lot_quittent_la_carte(window):
    a = enregistrer(window, "Aller")
    b = enregistrer(window, "Retour")
    window.show_track(a)
    window.show_track(b)
    panel = window.tree_panel
    panel.find_item(KIND_TRACK, a).setSelected(True)
    panel.find_item(KIND_TRACK, b).setSelected(True)

    panel.delete_selected(confirm=False)

    assert window.visible_tracks == set()
    assert wait_for(
        lambda: run_js_sync(window.map_view, "carto.shownTrackIds()") == [],
        timeout_ms=5000,
    )


def test_suppression_sans_selection(window):
    window.tree_panel.tree.clearSelection()
    assert window.tree_panel.delete_selected(confirm=False) is False


# --------------------------------- centrage sur le point sélectionné


def test_clic_sur_un_point_en_consultation_centre_la_carte(window):
    track_id = enregistrer(window)
    window.show_track(track_id)
    window.tree_panel.select_track(track_id)

    assert window.focus_point(2) is True

    assert wait_for(
        lambda: run_js_sync(window.map_view, "carto.hasFocus()") is True,
        timeout_ms=5000,
    )
    centre = run_js_sync(window.map_view, "map.getCenter().lat")
    assert centre == pytest.approx(48.932, abs=1e-3)


def test_le_panneau_de_points_centre_la_carte(window):
    """Cliquer une ligne de la liste doit centrer, même hors édition."""
    track_id = enregistrer(window)
    window.tree_panel.select_track(track_id)

    window.points_panel.list.setCurrentRow(1)

    assert wait_for(
        lambda: run_js_sync(window.map_view, "map.getCenter().lat")
        == pytest.approx(48.931, abs=1e-3),
        timeout_ms=5000,
    )


def test_clic_sur_le_profil_selectionne_et_centre(window):
    track_id = enregistrer(window)
    window.tree_panel.select_track(track_id)

    assert window.select_point(3) is True

    assert window.points_panel.selected_indexes() == [3]
    assert wait_for(
        lambda: run_js_sync(window.map_view, "map.getCenter().lat")
        == pytest.approx(48.933, abs=1e-3),
        timeout_ms=5000,
    )


def test_centrage_en_mode_edition(window):
    """En édition, c'est le repère du brouillon qui est mis en avant."""
    track_id = enregistrer(window)
    window.resume_track(track_id)

    assert window.select_point(2) is True

    assert wait_for(
        lambda: run_js_sync(window.map_view, "carto.selectedPoint()") == 2,
        timeout_ms=5000,
    )


def test_centrage_hors_bornes(window):
    track_id = enregistrer(window)
    window.tree_panel.select_track(track_id)

    assert window.focus_point(99) is False


def test_points_listes_selon_le_contexte(window):
    a = enregistrer(window, "Consultée")
    window.tree_panel.select_track(a)
    assert len(window.displayed_points()) == 4

    window.resume_track(a)
    window.add_draft_point(48.935, 1.437)
    assert len(window.displayed_points()) == 5   # le brouillon prime


# ------------------------------- plusieurs grandeurs dans le profil


def test_superposition_altitude_et_vitesse(window):
    track_id = enregistrer(window)
    window.tree_panel.select_track(track_id)

    window.profile_panel.add_source(SOURCE_VITESSE)

    assert set(window.profile_panel.active_sources) == {
        SOURCE_ELE_FICHIER, SOURCE_VITESSE
    }
    assert window.profile_panel.view.units == ["m", "km/h"]


def test_les_deux_altitudes_se_superposent(window, monkeypatch):
    track_id = enregistrer(window)
    monkeypatch.setattr(
        "carto.ui.main_window.fetch_elevations",
        lambda points, on_progress=None: [60.0, 65.0, 70.0, 68.0],
    )
    window.fetch_elevations_for(track_id)
    window.tree_panel.select_track(track_id)

    window.profile_panel.set_sources([SOURCE_ELE_FICHIER, SOURCE_ELE_SERVICE])

    assert len(window.profile_panel.view._series) == 2
    assert window.profile_panel.view.units == ["m"]
