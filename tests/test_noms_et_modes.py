"""Unicité des noms de traces, icônes de l'arborescence et modes d'édition."""

from __future__ import annotations

import sqlite3

import pytest
from PyQt6.QtWidgets import QMessageBox

from carto.app import create_app
from carto.database import Database, DuplicateNameError
from carto.models import Point
from carto.ui.main_window import MainWindow
from carto.ui.toolbar_icons import toolbar_icon
from carto.ui.tree_panel import COL_NAME, KIND_FOLDER, KIND_TRACK

DEUX = [Point(48.930, 1.440), Point(48.931, 1.442)]
TROIS = DEUX + [Point(48.932, 1.441)]


@pytest.fixture(scope="session")
def qapp():
    app = create_app(["carto-tests"])
    yield app
    app.processEvents()


# ------------------------------------------- unicité des noms de traces


def test_deux_traces_du_meme_nom_sont_departagees(db):
    premier = db.create_track("Rallye", points=DEUX)
    second = db.create_track("Rallye", points=DEUX)

    assert db.get_track(premier).name == "Rallye"
    assert db.get_track(second).name == "Rallye 2"


def test_le_meme_nom_reste_permis_dans_deux_dossiers(db):
    a = db.create_folder("Alpes")
    b = db.create_folder("Jura")

    db.create_track("Rallye", folder_id=a, points=DEUX)
    autre = db.create_track("Rallye", folder_id=b, points=DEUX)

    assert db.get_track(autre).name == "Rallye"


def test_suffixes_successifs(db):
    for _ in range(4):
        db.create_track("Rallye", points=DEUX)

    noms = sorted(t.name for t in db.list_tracks(None))
    assert noms == ["Rallye", "Rallye 2", "Rallye 3", "Rallye 4"]


def test_renommage_en_doublon_refuse(db):
    db.create_track("Rallye", points=DEUX)
    autre = db.create_track("Balade", points=DEUX)

    with pytest.raises(DuplicateNameError):
        db.rename_track(autre, "Rallye")
    assert db.get_track(autre).name == "Balade"


def test_renommer_une_trace_avec_son_propre_nom(db):
    track_id = db.create_track("Rallye", points=DEUX)
    db.rename_track(track_id, "Rallye")   # ne doit pas lever
    assert db.get_track(track_id).name == "Rallye"


def test_deplacement_vers_un_dossier_occupe(db):
    dossier = db.create_folder("Alpes")
    db.create_track("Rallye", folder_id=dossier, points=DEUX)
    voyageuse = db.create_track("Rallye", points=DEUX)   # devient « Rallye 2 »
    db.rename_track(voyageuse, "Rallye bis")

    db.move_track(voyageuse, dossier)

    noms = sorted(t.name for t in db.list_tracks(dossier))
    assert noms == ["Rallye", "Rallye bis"]


def test_deplacement_conservant_le_nom_quand_il_est_libre(db):
    dossier = db.create_folder("Alpes")
    track_id = db.create_track("Rallye", points=DEUX)

    db.move_track(track_id, dossier)

    assert db.get_track(track_id).name == "Rallye"


def test_la_base_refuse_les_doublons(db):
    """Un index unique garde la cohérence même si un chemin l'oubliait."""
    db.create_track("Rallye", points=DEUX)

    with pytest.raises(sqlite3.IntegrityError):
        db.conn.execute(
            "INSERT INTO tracks(name, folder_id) VALUES ('Rallye', NULL)"
        )


def test_migration_departage_les_doublons_existants(tmp_path):
    """Une base d'avant la règle peut contenir des homonymes."""
    chemin = tmp_path / "ancienne.db"
    with Database(chemin) as db:
        db.conn.execute("DROP INDEX IF EXISTS idx_tracks_unique")
        db.conn.executemany(
            "INSERT INTO tracks(name, folder_id) VALUES (?, NULL)",
            [("Rallye",), ("Rallye",), ("Rallye",)],
        )
        db.conn.commit()

    with Database(chemin) as relue:
        noms = sorted(t.name for t in relue.list_tracks(None))
        assert noms == ["Rallye", "Rallye 2", "Rallye 3"]


# ------------------------------------------------ copie par le presse-papiers


@pytest.fixture
def window(qapp, db, monkeypatch):
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: None))
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: None))
    monkeypatch.setattr(
        QMessageBox, "question",
        staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes),
    )
    win = MainWindow(db=db)
    yield win
    win.close()


def test_copier_coller_dans_le_meme_dossier_suffixe(window):
    """Régression : Ctrl+C puis Ctrl+V ne posait pas le suffixe « -copie »."""
    track_id = window.db.create_track("Rallye", points=DEUX)
    panel = window.tree_panel
    panel.refresh()
    panel.select_track(track_id)

    panel.copy_selection()
    panel.select_folder(None)
    assert panel.paste() == 1

    noms = sorted(t.name for t in window.db.list_tracks(None))
    assert noms == ["Rallye", "Rallye-copie"]


def test_copier_coller_deux_fois(window):
    track_id = window.db.create_track("Rallye", points=DEUX)
    panel = window.tree_panel
    panel.refresh()
    panel.select_track(track_id)
    panel.copy_selection()

    panel.select_folder(None)
    panel.paste()
    panel.select_folder(None)
    panel.paste()

    noms = sorted(t.name for t in window.db.list_tracks(None))
    assert noms == ["Rallye", "Rallye-copie", "Rallye-copie 2"]


def test_copier_coller_vers_un_autre_dossier(window):
    dossier = window.db.create_folder("Cible")
    track_id = window.db.create_track("Rallye", points=DEUX)
    panel = window.tree_panel
    panel.refresh()
    panel.select_track(track_id)

    panel.copy_selection()
    panel.select_folder(dossier)
    panel.paste()

    assert [t.name for t in window.db.list_tracks(dossier)] == ["Rallye-copie"]


def test_l_import_departage_les_homonymes(window, tmp_path):
    """Un fichier GPX peut contenir plusieurs traces du même nom."""
    from carto.gpx import write_gpx

    chemin = write_gpx(tmp_path / "double.gpx", "Parcours", DEUX)
    window.import_gpx([str(chemin), str(chemin)])

    noms = sorted(t.name for t in window.db.list_tracks(None))
    assert noms == ["Parcours", "Parcours 2"]


# ------------------------------------------------ icônes de l'arborescence


def test_les_traces_ont_une_icone(window):
    track_id = window.db.create_track("Rallye", points=DEUX)
    window.tree_panel.refresh()

    item = window.tree_panel.find_item(KIND_TRACK, track_id)

    assert not item.icon(COL_NAME).isNull()
    image = item.icon(COL_NAME).pixmap(40, 16).toImage()
    dessines = sum(
        1
        for y in range(image.height())
        for x in range(image.width())
        if image.pixelColor(x, y).alpha() > 0
    )
    assert dessines > 40, "l'icône de la trace est vide"


def test_les_dossiers_gardent_leur_icone(window):
    folder_id = window.db.create_folder("Alpes")
    window.tree_panel.refresh()

    item = window.tree_panel.find_item(KIND_FOLDER, folder_id)
    assert not item.icon(COL_NAME).isNull()


def test_la_trace_en_modification_porte_un_crayon(window):
    track_id = window.db.create_track("Rallye", points=TROIS)
    autre = window.db.create_track("Balade", points=TROIS)
    window.tree_panel.refresh()

    window.resume_track(track_id)

    assert window.tree_panel.editing_track_id == track_id
    modifiee = window.tree_panel.find_item(KIND_TRACK, track_id)
    normale = window.tree_panel.find_item(KIND_TRACK, autre)
    assert (
        modifiee.icon(COL_NAME).pixmap(40, 16).toImage()
        != normale.icon(COL_NAME).pixmap(40, 16).toImage()
    )


def test_le_crayon_disparait_apres_enregistrement(window):
    track_id = window.db.create_track("Rallye", points=TROIS)
    window.tree_panel.refresh()
    window.resume_track(track_id)

    window.save_draft()

    assert window.tree_panel.editing_track_id is None


def test_l_icone_crayon_se_dessine(qapp):
    icone = toolbar_icon("crayon")
    image = icone.pixmap(22, 22).toImage()
    dessines = sum(
        1
        for y in range(image.height())
        for x in range(image.width())
        if image.pixelColor(x, y).alpha() > 0
    )
    assert dessines > 30


# ------------------------------------------------------------ modes


def test_modifier_enfonce_son_propre_bouton(window):
    track_id = window.db.create_track("Rallye", points=TROIS)
    window.tree_panel.refresh()

    window.resume_track(track_id)

    assert window.action_resume.isChecked() is True
    assert window.action_create.isChecked() is False


def test_creer_enfonce_son_propre_bouton(window):
    window.set_edit_mode(True)

    assert window.action_create.isChecked() is True
    assert window.action_resume.isChecked() is False


def test_relever_le_bouton_modifier_quitte_l_edition(window):
    track_id = window.db.create_track("Rallye", points=TROIS)
    window.tree_panel.refresh()
    window.resume_track(track_id)

    window.action_resume.setChecked(False)

    assert window.edit_mode is False
    assert window.draft.is_empty
    assert window.tree_panel.editing_track_id is None


def test_l_enregistrement_quitte_les_deux_modes(window):
    track_id = window.db.create_track("Rallye", points=TROIS)
    window.tree_panel.refresh()
    window.resume_track(track_id)

    window.save_draft()

    assert window.edit_mode is False
    assert window.action_create.isChecked() is False
    assert window.action_resume.isChecked() is False


def test_le_bouton_enregistrer_s_appelle_enregistrer(window):
    assert window.action_save.text() == "Enregistrer"


# ------------------------------------- insertion sans recentrage


def test_l_insertion_ne_recentre_pas(window, monkeypatch):
    """Régression : la vue sautait sur le point qu'on venait de poser."""
    track_id = window.db.create_track("Rallye", points=TROIS)
    window.tree_panel.refresh()
    window.resume_track(track_id)

    appels = []
    monkeypatch.setattr(
        window.map_view,
        "select_draft_point",
        lambda index, pan=True: appels.append((index, pan)),
    )

    window.insert_draft_point(1, 48.9305, 1.441)

    assert appels == [(1, False)]


def test_la_selection_depuis_la_liste_recentre_toujours(window, monkeypatch):
    track_id = window.db.create_track("Rallye", points=TROIS)
    window.tree_panel.refresh()
    window.resume_track(track_id)

    appels = []
    monkeypatch.setattr(
        window.map_view,
        "select_draft_point",
        lambda index, pan=True: appels.append((index, pan)),
    )

    window.select_point(2)

    assert appels == [(2, True)]
