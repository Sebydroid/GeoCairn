"""Sens de parcours, consultation hors édition et altimétrie (intégration)."""

from __future__ import annotations

import json

import pytest
from PyQt6.QtWidgets import QMessageBox

from geocairn.app import create_app
from geocairn.database import Database
from geocairn.models import Point
from geocairn.ui.main_window import MainWindow
from geocairn.ui.profile_panel import (
    SOURCE_ELE_FICHIER,
    SOURCE_ELE_SERVICE,
    SOURCE_VITESSE,
)
from geocairn.ui.tree_panel import KIND_FOLDER, KIND_ROOT, KIND_TRACK
from tests.test_ui import run_js_sync, wait_for

QUATRE = [
    Point(48.930, 1.440, 70.0, "2026-08-10T09:00:00Z"),
    Point(48.931, 1.442, 75.0, "2026-08-10T09:01:00Z"),
    Point(48.932, 1.441, 80.0, "2026-08-10T09:02:00Z"),
    Point(48.933, 1.439, 78.0, "2026-08-10T09:03:00Z"),
]

DESSINEE = [Point(48.930, 1.440), Point(48.931, 1.442), Point(48.932, 1.441)]


@pytest.fixture(scope="session")
def qapp():
    app = create_app(["geocairn-tests"])
    yield app
    app.processEvents()


@pytest.fixture(scope="session")
def window(qapp, tmp_path_factory):
    database = Database(tmp_path_factory.mktemp("profil") / "geocairn.db")
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


# ------------------------------------ liste des points hors édition


def test_selection_d_une_trace_liste_ses_points(window):
    track_id = enregistrer(window)

    window.tree_panel.select_track(track_id)

    assert window.points_panel.list.count() == 4
    assert "consultation" in window.points_panel.title.text()
    assert "Rallye" in window.points_panel.title.text()


def test_la_liste_hors_edition_n_est_pas_modifiable(window):
    track_id = enregistrer(window)
    window.tree_panel.select_track(track_id)

    window.points_panel.select_index(1)

    assert window.points_panel.delete_button.isEnabled() is False
    assert window.points_panel.split_button.isEnabled() is False


def test_la_liste_redevient_modifiable_en_edition(window):
    track_id = enregistrer(window)
    window.tree_panel.select_track(track_id)

    window.resume_track(track_id)
    window.points_panel.select_index(1)

    assert window.points_panel.delete_button.isEnabled() is True
    assert "consultation" not in window.points_panel.title.text()


def test_selectionner_un_dossier_vide_la_liste(window):
    track_id = enregistrer(window)
    dossier = window.db.create_folder("Rallye 2016")
    window.tree_panel.refresh()
    window.tree_panel.select_track(track_id)
    assert window.points_panel.list.count() == 4

    window.tree_panel.select_folder(dossier)

    assert window.points_panel.list.count() == 0


def test_l_edition_garde_la_main_sur_la_liste(window):
    """Sélectionner une autre trace ne doit pas écraser le brouillon listé."""
    a = enregistrer(window, "Reprise")
    b = enregistrer(window, "Autre", points=DESSINEE)
    window.resume_track(a)

    window.tree_panel.select_track(b)

    assert window.points_panel.list.count() == 4   # toujours la trace reprise
    assert "consultation" not in window.points_panel.title.text()


# ------------------------------------------------------- sens de parcours


def test_inversion_du_sens(window):
    track_id = enregistrer(window)

    assert window.reverse_track(track_id) is True

    points = window.db.get_points(track_id)
    assert [p.as_tuple() for p in points] == [
        (48.933, 1.439), (48.932, 1.441), (48.931, 1.442), (48.930, 1.440)
    ]


def test_l_inversion_conserve_altitudes_et_horodatages(window):
    track_id = enregistrer(window)

    window.reverse_track(track_id)

    points = window.db.get_points(track_id)
    assert points[0].ele == pytest.approx(78.0)
    assert points[0].time == "2026-08-10T09:03:00Z"


def test_inversion_d_une_trace_d_un_seul_point(window):
    track_id = window.db.create_track("Unique", points=[Point(48.9, 1.4)])
    window.tree_panel.refresh()

    assert window.reverse_track(track_id) is False


def test_le_sens_est_affiche_par_des_fleches(window):
    track_id = enregistrer(window, points=[
        Point(48.90 + i / 200, 1.44) for i in range(40)
    ])
    window.show_track(track_id)

    assert wait_for(
        lambda: run_js_sync(window.map_view, f"geocairn.arrowCount({track_id})") > 0,
        timeout_ms=5000,
    )


def test_les_fleches_changent_de_sens_avec_la_trace(window):
    """Vers le nord puis, après inversion, vers le sud."""
    montante = [Point(48.90 + i / 200, 1.44) for i in range(40)]
    track_id = enregistrer(window, points=montante)
    window.show_track(track_id)
    assert wait_for(
        lambda: run_js_sync(window.map_view, f"geocairn.arrowCount({track_id})") > 0,
        timeout_ms=5000,
    )

    avant = run_js_sync(window.map_view, f"geocairn.arrowAngles({track_id})")
    assert all(abs(a) < 20 for a in avant), "vers le nord : angle proche de 0°"

    window.reverse_track(track_id)

    assert wait_for(
        lambda: all(
            abs(abs(a) - 180) < 20
            for a in run_js_sync(window.map_view, f"geocairn.arrowAngles({track_id})")
        ),
        timeout_ms=5000,
    )


def test_les_fleches_disparaissent_avec_la_trace(window):
    track_id = enregistrer(window)
    window.show_track(track_id)
    wait_for(lambda: run_js_sync(window.map_view, f"geocairn.arrowCount({track_id})") > 0)

    window.hide_track(track_id)

    assert wait_for(
        lambda: run_js_sync(window.map_view, f"geocairn.arrowCount({track_id})") == 0,
        timeout_ms=5000,
    )


# ----------------------------------------------------------- profil


def test_le_profil_suit_la_trace_selectionnee(window):
    track_id = enregistrer(window)

    window.tree_panel.select_track(track_id)

    assert window.profile_panel.view.has_data is True
    assert "Rallye" in window.profile_panel.title.text()


def test_le_profil_suit_la_trace_en_edition(window):
    track_id = enregistrer(window)
    window.resume_track(track_id)

    window.add_draft_point(48.934, 1.437)

    assert window.profile_panel.view.has_data is True


def test_profil_de_vitesse(window):
    track_id = enregistrer(window)
    window.tree_panel.select_track(track_id)

    assert window.profile_panel.set_source(SOURCE_VITESSE) is True
    assert window.profile_panel.view.has_data is True

    window.profile_panel.set_source(SOURCE_ELE_FICHIER)


def test_profil_vide_pour_une_trace_dessinee(window):
    track_id = enregistrer(window, "Dessinée", points=DESSINEE)

    window.tree_panel.select_track(track_id)

    assert window.profile_panel.view.has_data is False


def test_clic_sur_le_profil_selectionne_le_point(window):
    track_id = enregistrer(window)
    window.tree_panel.select_track(track_id)

    window.profile_panel.point_clicked.emit(2)

    assert window.points_panel.selected_indexes() == [2]


# ------------------------------------------------- altitude IGN


def faux_service(valeurs):
    """Remplace le transport réseau du service altimétrique."""
    def fetch(_url):
        return json.dumps({"elevations": list(valeurs)}).encode()
    return fetch


def test_calcul_de_l_altitude(window, monkeypatch):
    track_id = enregistrer(window, "Dessinée", points=DESSINEE)
    monkeypatch.setattr(
        "geocairn.ui.main_window.fetch_elevations",
        lambda points, on_progress=None: [63.2, 68.0, 74.5],
    )

    renseignes = window.fetch_elevations_for(track_id)

    assert renseignes == 3
    points = window.db.get_points(track_id)
    assert [p.ele_service for p in points] == [63.2, 68.0, 74.5]


def test_l_altitude_calculee_alimente_le_profil(window, monkeypatch):
    track_id = enregistrer(window, "Dessinée", points=DESSINEE)
    monkeypatch.setattr(
        "geocairn.ui.main_window.fetch_elevations",
        lambda points, on_progress=None: [63.2, 68.0, 74.5],
    )
    window.tree_panel.select_track(track_id)
    assert window.profile_panel.view.has_data is False

    window.fetch_elevations_for(track_id)

    assert window.profile_panel.active_sources == [SOURCE_ELE_SERVICE]
    assert window.profile_panel.view.has_data is True


def test_l_altitude_du_fichier_n_est_pas_ecrasee(window, monkeypatch):
    track_id = enregistrer(window)
    monkeypatch.setattr(
        "geocairn.ui.main_window.fetch_elevations",
        lambda points, on_progress=None: [10.0, 20.0, 30.0, 40.0],
    )

    window.fetch_elevations_for(track_id)

    points = window.db.get_points(track_id)
    assert [p.ele for p in points] == [70.0, 75.0, 80.0, 78.0]
    assert [p.ele_service for p in points] == [10.0, 20.0, 30.0, 40.0]


def test_points_hors_couverture_laisses_vides(window, monkeypatch):
    track_id = enregistrer(window, "Dessinée", points=DESSINEE)
    monkeypatch.setattr(
        "geocairn.ui.main_window.fetch_elevations",
        lambda points, on_progress=None: [63.2, None, 74.5],
    )

    renseignes = window.fetch_elevations_for(track_id)

    assert renseignes == 2
    assert window.db.get_points(track_id)[1].ele_service is None


def test_service_indisponible_signale(window, monkeypatch):
    from geocairn.elevation import ElevationError

    track_id = enregistrer(window, "Dessinée", points=DESSINEE)

    def echec(points, on_progress=None):
        raise ElevationError("Service altimétrique injoignable")

    monkeypatch.setattr("geocairn.ui.main_window.fetch_elevations", echec)

    assert window.fetch_elevations_for(track_id) is None
    assert window.db.get_points(track_id)[0].ele_service is None


def test_l_altitude_calculee_survit_a_la_relecture(window, monkeypatch):
    """L'altitude du service doit être enregistrée, pas seulement affichée."""
    track_id = enregistrer(window, "Dessinée", points=DESSINEE)
    monkeypatch.setattr(
        "geocairn.ui.main_window.fetch_elevations",
        lambda points, on_progress=None: [63.2, 68.0, 74.5],
    )
    window.fetch_elevations_for(track_id)

    relue = window.db.get_track(track_id, with_points=True)

    assert relue.points[0].ele_service == pytest.approx(63.2)
