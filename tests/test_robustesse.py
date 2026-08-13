"""Tests de régression sur les pannes repérées à la relecture du code.

Chaque test reproduit une situation qui, avant correction, laissait l'outil dans
un état incohérent — voire interrompait le programme au beau milieu d'un signal
Qt, ce qui, sous PyQt, fait tomber toute l'application.
"""

from __future__ import annotations

import sqlite3

import pytest
from PyQt6.QtWidgets import QMessageBox

from carto.app import create_app
from carto.database import Database
from carto.gpx import safe_filename
from carto.models import Point
from carto.ui.icons import BULB_ON, bulb_with
from carto.ui.main_window import MainWindow
from carto.ui.toolbar_icons import toolbar_icon

DEUX = [Point(48.930, 1.440), Point(48.931, 1.442)]
TROIS = DEUX + [Point(48.932, 1.441)]
QUATRE = TROIS + [Point(48.933, 1.439)]


@pytest.fixture(scope="session")
def qapp():
    app = create_app(["carto-tests"])
    yield app
    app.processEvents()


@pytest.fixture
def window(qapp, db, monkeypatch):
    """Fenêtre sur une base vierge, dialogues neutralisés."""
    monkeypatch.setattr(
        QMessageBox, "question",
        staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes),
    )
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: None))
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: None))
    monkeypatch.setattr(QMessageBox, "critical", staticmethod(lambda *a, **k: None))

    win = MainWindow(db=db)
    yield win
    win._closing = True


# ------------------------- trace supprimée pendant sa modification


def test_supprimer_la_trace_en_cours_de_modification_detache_le_brouillon(window):
    track_id = window.db.create_track("Rallye", points=TROIS)
    window.tree_panel.refresh()
    assert window.resume_track(track_id) is True

    window.db.delete_track(track_id)
    window.forget_tracks([track_id])

    # Le travail en cours est conservé, mais n'est plus rattaché à rien.
    assert window.draft.track_id is None
    assert len(window.draft) == 3


def test_enregistrer_apres_suppression_de_la_trace_reprise(window):
    """Ctrl+S après suppression ne doit pas interrompre le programme."""
    track_id = window.db.create_track("Rallye", points=TROIS)
    window.tree_panel.refresh()
    window.resume_track(track_id)

    window.db.delete_track(track_id)
    window.forget_tracks([track_id])

    nouveau = window.save_draft(name="Rallye repris")

    assert nouveau is not None and nouveau != track_id
    assert window.db.get_track(nouveau).point_count == 3


def test_enregistrer_survit_meme_sans_passage_par_forget_tracks(window):
    """Dernier garde-fou : la trace disparue est détectée à l'enregistrement."""
    track_id = window.db.create_track("Rallye", points=TROIS)
    window.tree_panel.refresh()
    window.resume_track(track_id)

    window.db.delete_track(track_id)   # sans prévenir la fenêtre

    assert window.save_draft(name="Rescapée") is not None


def test_decouper_apres_suppression_de_la_trace_reprise(window):
    track_id = window.db.create_track("Rallye", points=QUATRE)
    window.tree_panel.refresh()
    window.resume_track(track_id)

    window.db.delete_track(track_id)

    assert window.split_draft(1) is None   # refusé, mais sans casse


def test_supprimer_le_dossier_de_la_trace_en_cours_de_modification(window):
    dossier = window.db.create_folder("Alpes")
    track_id = window.db.create_track("Rallye", folder_id=dossier, points=TROIS)
    window.tree_panel.refresh()
    window.resume_track(track_id)

    window.tree_panel.select_folder(dossier)
    assert window.tree_panel.delete_selected(confirm=False) is True

    assert window.draft.track_id is None
    assert len(window.draft) == 3


# ------------------------------------------- fusion et traces affichées


def test_la_fusion_retire_les_sources_de_la_carte(window):
    premier = window.db.create_track("A", points=DEUX)
    second = window.db.create_track("B", points=DEUX)
    window.tree_panel.refresh()
    window.show_track(premier)
    window.show_track(second)

    fusion = window.merge_track(premier, second)

    assert window.visible_tracks == {fusion}


def test_la_fusion_detache_le_brouillon_de_la_trace_absorbee(window):
    premier = window.db.create_track("A", points=TROIS)
    second = window.db.create_track("B", points=TROIS)
    window.tree_panel.refresh()
    window.resume_track(premier)

    window.merge_track(premier, second)

    assert window.draft.track_id is None


# ------------------------------------------------ boucle et numérotation


def test_la_boucle_fermee_est_conservee_a_l_enregistrement(window):
    track_id = window.db.create_track("Boucle", points=TROIS)
    window.tree_panel.refresh()
    window.resume_track(track_id)

    assert window.close_draft_loop() is True
    window.save_draft()

    trace = window.db.get_track(track_id, with_points=True)
    assert trace.is_loop is True
    assert trace.points[0].as_tuple() == trace.points[-1].as_tuple()


def test_fermeture_de_boucle_avec_des_numeros_troues(db):
    """Une numérotation non consécutive ne doit pas écraser un point."""
    track_id = db.create_track("Trace", points=TROIS)
    with db.conn:
        db.conn.execute(
            "UPDATE points SET seq = seq + 10 WHERE track_id = ? AND seq = 2",
            (track_id,),
        )

    assert db.close_track(track_id) is True
    assert db.count_points(track_id) == 4


def test_altitudes_du_service_avec_des_numeros_troues(db):
    track_id = db.create_track("Trace", points=TROIS)
    with db.conn:
        db.conn.execute(
            "UPDATE points SET seq = seq + 10 WHERE track_id = ? AND seq = 2",
            (track_id,),
        )

    assert db.set_service_elevations(track_id, [10.0, 20.0, 30.0]) == 3
    assert [p.ele_service for p in db.get_points(track_id)] == [10.0, 20.0, 30.0]


# ---------------------------------------------------- noms de fichiers


@pytest.mark.parametrize("nom", ["CON", "nul", "Com1", "LPT9", "aux"])
def test_les_noms_reserves_de_windows_sont_ecartes(nom):
    """« CON.gpx » désigne la console, pas un fichier : l'export serait perdu."""
    obtenu = safe_filename(nom)
    assert obtenu.rsplit(".", 1)[0].upper() not in {
        "CON", "PRN", "AUX", "NUL", "COM1", "LPT9",
    }
    assert obtenu.endswith(".gpx")


def test_un_nom_ordinaire_reste_intact():
    assert safe_filename("Tour du lac") == "Tour du lac.gpx"


# --------------------------------------------------- icônes composites


def test_deux_icones_de_base_donnent_deux_icones_composites(qapp):
    """Le cache ne doit pas confondre deux icônes différentes."""
    trace = bulb_with(BULB_ON, toolbar_icon("trace"))
    crayon = bulb_with(BULB_ON, toolbar_icon("crayon"))

    assert trace.cacheKey() != crayon.cacheKey()


def test_le_cache_des_icones_reste_efficace(qapp):
    premier = bulb_with(BULB_ON, toolbar_icon("trace"))
    second = bulb_with(BULB_ON, toolbar_icon("trace"))

    assert premier is second


# ----------------------------------------------- renommage d'un absent


def test_renommer_un_element_disparu_ne_casse_rien(window):
    track_id = window.db.create_track("Rallye", points=DEUX)
    window.tree_panel.refresh()
    window.tree_panel.select_track(track_id)

    window.db.delete_track(track_id)   # l'arbre garde encore l'ancien item

    assert window.tree_panel.rename_selected(name="Autre") is False


def test_deplacer_une_trace_vers_un_dossier_disparu(window):
    track_id = window.db.create_track("Rallye", points=DEUX)
    dossier = window.db.create_folder("Alpes")
    window.tree_panel.refresh()
    window.db.delete_folder(dossier)

    # Le déplacement échoue proprement plutôt que d'interrompre le programme.
    from carto.database import NotFoundError

    with pytest.raises(NotFoundError):
        window.tree_panel.move_track(track_id, dossier)


# ------------------------------------------------- ouverture de la base


def test_une_base_illisible_ne_passe_pas_inapercue(tmp_path):
    """Un fichier abîmé doit donner une erreur claire, pas un plantage muet."""
    chemin = tmp_path / "abime.db"
    chemin.write_bytes(b"ceci n'est pas une base SQLite" * 10)

    with pytest.raises(sqlite3.DatabaseError):
        Database(chemin)


def test_le_lancement_explique_une_base_inaccessible(qapp, monkeypatch):
    """L'exécutable n'a pas de console : il doit le dire à l'écran."""
    import carto.app as app_module

    def base_cassee(*_args, **_kwargs):
        raise sqlite3.DatabaseError("fichier de base illisible")

    messages = []
    monkeypatch.setattr(app_module, "Database", base_cassee)
    monkeypatch.setattr(
        QMessageBox, "critical",
        staticmethod(lambda *args, **kwargs: messages.append(args)),
    )

    assert app_module.run(["carto"]) == 1
    assert messages, "aucune explication n'a été présentée à l'utilisateur"
