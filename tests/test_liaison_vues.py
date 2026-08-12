"""Statistiques du profil, distances cumulées, liaison des vues, presse-papiers."""

from __future__ import annotations

import pytest
from PyQt6.QtCore import QMimeData, QPointF, Qt
from PyQt6.QtGui import QDropEvent
from PyQt6.QtWidgets import QMessageBox

from carto.app import create_app
from carto.database import Database
from carto.geo import elevation_gain, format_speed, speed_stats
from carto.models import Point
from carto.ui.main_window import MainWindow
from carto.ui.tree_panel import KIND_FOLDER, KIND_TRACK
from tests.test_ui import run_js_sync, wait_for

# Un degré de latitude en une heure : environ 111 km/h.
RAPIDE = [
    Point(45.0, 3.0, 100.0, "2026-08-10T09:00:00Z"),
    Point(46.0, 3.0, 150.0, "2026-08-10T10:00:00Z"),
    Point(47.0, 3.0, 120.0, "2026-08-10T12:00:00Z"),
]

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
    database = Database(tmp_path_factory.mktemp("liaison") / "carto.db")
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
    window.tree_panel._clipboard = ("copier", [])
    window.tree_panel.refresh()
    window._update_draft_actions()
    yield


def enregistrer(window, nom="Rallye", points=None) -> int:
    track_id = window.db.create_track(nom, points=points or QUATRE)
    window.tree_panel.refresh()
    return track_id


# ------------------------------------------------------ dénivelés


def test_denivele_cumule():
    montee, descente = elevation_gain([100.0, 150.0, 120.0, 130.0])

    assert montee == pytest.approx(60.0)    # +50 puis +10
    assert descente == pytest.approx(30.0)  # −30


def test_denivele_ignore_les_trous():
    montee, descente = elevation_gain([100.0, None, 150.0])

    assert montee == pytest.approx(50.0)
    assert descente == pytest.approx(0.0)


def test_denivele_sans_donnee():
    assert elevation_gain([]) == (0.0, 0.0)
    assert elevation_gain([None, None]) == (0.0, 0.0)


# ------------------------------------------------------- vitesses


def test_vitesse_max_et_moyenne():
    maximale, moyenne = speed_stats(RAPIDE)

    assert maximale == pytest.approx(111.2, rel=0.01)
    # 2 degrés en 3 heures : environ 74 km/h de moyenne.
    assert moyenne == pytest.approx(74.1, rel=0.02)


def test_la_moyenne_tient_compte_des_arrets():
    """Moyenne = distance / temps total, pas moyenne des vitesses."""
    points = [
        Point(45.0, 3.0, time="2026-08-10T09:00:00Z"),
        Point(45.1, 3.0, time="2026-08-10T09:10:00Z"),
        Point(45.1, 3.0, time="2026-08-10T10:10:00Z"),   # une heure d'arrêt
    ]

    maximale, moyenne = speed_stats(points)

    assert maximale > moyenne * 2


def test_vitesses_sans_horodatage():
    assert speed_stats([Point(48.9, 1.4), Point(48.91, 1.41)]) == (None, None)


def test_formatage_des_vitesses():
    assert format_speed(12.34) == "12,3 km/h"
    assert format_speed(None) == "—"


# --------------------------------------- résumé affiché sous le profil


def test_le_profil_affiche_les_chiffres_cles(window):
    track_id = enregistrer(window, "Rallye", RAPIDE)

    window.tree_panel.select_track(track_id)

    resume = window.profile_panel.stats.text()
    assert "Distance" in resume
    assert "Dénivelé" in resume and "+50" in resume and "−30" in resume
    assert "Vitesse max" in resume and "111" in resume
    assert "moyenne" in resume


def test_le_resume_omet_la_vitesse_sans_horodatage(window):
    dessinee = [Point(48.930, 1.440), Point(48.931, 1.442), Point(48.932, 1.441)]
    track_id = enregistrer(window, "Dessinée", dessinee)

    window.tree_panel.select_track(track_id)

    resume = window.profile_panel.stats.text()
    assert "Distance" in resume
    assert "Vitesse" not in resume


def test_le_resume_utilise_l_altitude_ign_a_defaut(window, monkeypatch):
    dessinee = [Point(48.930, 1.440), Point(48.931, 1.442), Point(48.932, 1.441)]
    track_id = enregistrer(window, "Dessinée", dessinee)
    monkeypatch.setattr(
        "carto.ui.main_window.fetch_elevations",
        lambda points, on_progress=None: [60.0, 90.0, 70.0],
    )
    window.fetch_elevations_for(track_id)

    window.tree_panel.select_track(track_id)

    resume = window.profile_panel.stats.text()
    assert "Dénivelé (IGN)" in resume
    assert "+30" in resume and "−20" in resume


# ------------------------------------- distance cumulée dans la liste


def test_distance_cumulee_dans_la_liste(window):
    track_id = enregistrer(window)

    window.tree_panel.select_track(track_id)

    lignes = [
        window.points_panel.list.item(i).text()
        for i in range(window.points_panel.list.count())
    ]
    assert lignes[0].endswith("0 m")
    # La distance ne peut que croître le long de la trace.
    assert "m" in lignes[-1]
    assert "distance" in window.points_panel.header.text()


# --------------------------------------------- liaison des trois vues


def test_le_profil_suit_la_selection_de_la_liste(window):
    track_id = enregistrer(window)
    window.tree_panel.select_track(track_id)

    window.points_panel.list.setCurrentRow(2)

    assert window.profile_panel.selected == 2


def test_la_liste_et_le_profil_suivent_un_clic_sur_la_carte(window):
    track_id = enregistrer(window)
    window.resume_track(track_id)

    window.map_view.point_selected.emit(1)

    assert window.points_panel.selected_indexes() == [1]
    assert window.profile_panel.selected == 1


def test_le_profil_et_la_liste_suivent_un_clic_sur_le_profil(window):
    track_id = enregistrer(window)
    window.tree_panel.select_track(track_id)

    window.profile_panel.point_clicked.emit(3)

    assert window.points_panel.selected_indexes() == [3]
    assert window.profile_panel.selected == 3
    assert wait_for(
        lambda: run_js_sync(window.map_view, "carto.hasFocus()") is True,
        timeout_ms=5000,
    )


def test_selection_hors_bornes_sans_effet(window):
    track_id = enregistrer(window)
    window.tree_panel.select_track(track_id)

    assert window.select_point(99) is False


# ------------------------------------------ altitude IGN masquable


def test_l_altitude_ign_peut_etre_decochee(window, monkeypatch):
    from carto.ui.profile_panel import SOURCE_ELE_FICHIER, SOURCE_ELE_SERVICE

    track_id = enregistrer(window)
    monkeypatch.setattr(
        "carto.ui.main_window.fetch_elevations",
        lambda points, on_progress=None: [60.0, 65.0, 70.0, 68.0],
    )
    window.fetch_elevations_for(track_id)
    window.tree_panel.select_track(track_id)
    window.profile_panel.set_sources([SOURCE_ELE_FICHIER, SOURCE_ELE_SERVICE])
    assert len(window.profile_panel.view._series) == 2

    window.profile_panel.checks[SOURCE_ELE_SERVICE].setChecked(False)

    assert window.profile_panel.active_sources == [SOURCE_ELE_FICHIER]
    assert len(window.profile_panel.view._series) == 1


# ------------------------------- glisser-déposer de plusieurs éléments


def deposer(panel, sources, cible) -> QDropEvent:
    panel.tree.clearSelection()
    # setCurrentItem d'abord : appelé après, il ramènerait la sélection au seul
    # élément courant.
    panel.tree.setCurrentItem(sources[0])
    for item in sources:
        item.setSelected(True)
    event = QDropEvent(
        QPointF(panel.tree.visualItemRect(cible).center()),
        Qt.DropAction.MoveAction,
        QMimeData(),
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    panel.tree.dropEvent(event)
    return event


def test_glisser_deposer_de_plusieurs_traces(window):
    dossier = window.db.create_folder("Rallye")
    a = window.db.create_track("Aller", points=QUATRE)
    b = window.db.create_track("Retour", points=QUATRE)
    panel = window.tree_panel
    panel.refresh()

    deposer(
        panel,
        [panel.find_item(KIND_TRACK, a), panel.find_item(KIND_TRACK, b)],
        panel.find_item(KIND_FOLDER, dossier),
    )

    assert window.db.get_track(a).folder_id == dossier
    assert window.db.get_track(b).folder_id == dossier


def test_glisser_deposer_melangeant_dossier_et_trace(window):
    cible = window.db.create_folder("Cible")
    autre = window.db.create_folder("Autre")
    trace = window.db.create_track("Trace", points=QUATRE)
    panel = window.tree_panel
    panel.refresh()

    deposer(
        panel,
        [panel.find_item(KIND_FOLDER, autre), panel.find_item(KIND_TRACK, trace)],
        panel.find_item(KIND_FOLDER, cible),
    )

    assert window.db.get_folder(autre).parent_id == cible
    assert window.db.get_track(trace).folder_id == cible


def test_un_element_deja_emporte_par_son_dossier_est_ignore(window):
    """Sélectionner un dossier et son contenu ne doit pas sortir la trace."""
    cible = window.db.create_folder("Cible")
    source = window.db.create_folder("Source")
    dedans = window.db.create_track("Dedans", folder_id=source, points=QUATRE)
    panel = window.tree_panel
    panel.refresh()
    panel.find_item(KIND_FOLDER, source).setExpanded(True)

    deposer(
        panel,
        [panel.find_item(KIND_FOLDER, source), panel.find_item(KIND_TRACK, dedans)],
        panel.find_item(KIND_FOLDER, cible),
    )

    assert window.db.get_folder(source).parent_id == cible
    assert window.db.get_track(dedans).folder_id == source   # resté dedans


# ----------------------------------------- copier, couper, coller


def test_copier_coller_une_trace(window):
    dossier = window.db.create_folder("Cible")
    track_id = enregistrer(window, "Rallye")
    panel = window.tree_panel
    panel.refresh()
    panel.select_track(track_id)

    assert panel.copy_selection() == 1
    panel.select_folder(dossier)
    assert panel.paste() == 1

    copies = window.db.list_tracks(dossier)
    assert [t.name for t in copies] == ["Rallye-copie"]
    assert window.db.get_track(track_id) is not None   # l'original reste


def test_couper_coller_une_trace(window):
    dossier = window.db.create_folder("Cible")
    track_id = enregistrer(window, "Rallye")
    panel = window.tree_panel
    panel.refresh()
    panel.select_track(track_id)

    assert panel.cut_selection() == 1
    panel.select_folder(dossier)
    assert panel.paste() == 1

    assert window.db.get_track(track_id).folder_id == dossier
    assert len(window.db.list_tracks(None)) == 0


def test_coller_plusieurs_elements(window):
    dossier = window.db.create_folder("Cible")
    a = window.db.create_track("Aller", points=QUATRE)
    b = window.db.create_track("Retour", points=QUATRE)
    panel = window.tree_panel
    panel.refresh()
    panel.find_item(KIND_TRACK, a).setSelected(True)
    panel.find_item(KIND_TRACK, b).setSelected(True)

    assert panel.copy_selection() == 2
    panel.select_folder(dossier)
    assert panel.paste() == 2

    assert len(window.db.list_tracks(dossier)) == 2


def test_copier_coller_un_dossier_avec_son_contenu(window):
    source = window.db.create_folder("Source")
    sous = window.db.create_folder("2026", parent_id=source)
    window.db.create_track("Dedans", folder_id=sous, points=QUATRE)
    cible = window.db.create_folder("Cible")
    panel = window.tree_panel
    panel.refresh()
    panel.select_folder(source)

    panel.copy_selection()
    panel.select_folder(cible)
    assert panel.paste() == 1

    copie = window.db.list_folders(cible)[0]
    assert copie.name == "Source"
    sous_copie = window.db.list_folders(copie.id)[0]
    assert sous_copie.name == "2026"
    assert [t.name for t in window.db.list_tracks(sous_copie.id)] == ["Dedans"]


def test_coller_un_dossier_a_cote_de_lui_meme_le_renomme(window):
    source = window.db.create_folder("Source")
    window.db.create_track("Dedans", folder_id=source, points=QUATRE)
    panel = window.tree_panel
    panel.refresh()
    panel.select_folder(source)

    panel.copy_selection()
    panel.select_folder(None)   # coller à la racine, où « Source » existe déjà
    assert panel.paste() == 1

    noms = sorted(f.name for f in window.db.list_folders(None))
    assert noms == ["Source", "Source 2"]


def test_coller_sans_rien_dans_le_presse_papiers(window):
    assert window.tree_panel.paste() == 0


def test_le_couper_coller_vide_le_presse_papiers(window):
    dossier = window.db.create_folder("Cible")
    track_id = enregistrer(window, "Rallye")
    panel = window.tree_panel
    panel.refresh()
    panel.select_track(track_id)
    panel.cut_selection()
    panel.select_folder(dossier)
    panel.paste()

    assert panel.paste() == 0   # un deuxième collage ne duplique rien


def test_copier_un_dossier_dans_son_propre_sous_dossier_refuse(window):
    source = window.db.create_folder("Source")
    sous = window.db.create_folder("2026", parent_id=source)
    panel = window.tree_panel
    panel.refresh()
    panel.select_folder(source)

    panel.copy_selection()
    panel.select_folder(sous)

    assert panel.paste() == 0
    assert window.db.list_folders(sous) == []
