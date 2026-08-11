"""Intégration de l'édition avancée : carte, panneau de points, base (Jalon 6)."""

from __future__ import annotations

import pytest
from PyQt6.QtWidgets import QMenu, QMessageBox

from carto.app import create_app
from carto.database import Database
from carto.models import Point
from carto.ui.main_window import MainWindow
from tests.test_ui import run_js_sync, wait_for

QUATRE_POINTS = [
    Point(48.930, 1.440),
    Point(48.931, 1.442),
    Point(48.932, 1.441),
    Point(48.933, 1.439),
]


@pytest.fixture(scope="session")
def qapp():
    app = create_app(["carto-tests"])
    yield app
    app.processEvents()


@pytest.fixture(scope="session")
def window(qapp, tmp_path_factory):
    database = Database(tmp_path_factory.mktemp("edition6") / "carto.db")
    win = MainWindow(db=database)
    win.show()
    assert wait_for(lambda: win.map_view.is_ready), "carte non chargée"
    yield win
    win.close()


@pytest.fixture(autouse=True)
def etat_vierge(window, monkeypatch):
    """Bibliothèque vide, brouillon vide, dialogues neutralisés."""
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
    window.draft.reset()
    window.set_edit_mode(False)
    window.map_view.clear_draft()
    window.map_view.clear_tracks()
    window.visible_tracks.clear()
    window.tree_panel.refresh()
    window._update_draft_actions()
    yield


def js_draft(window) -> int:
    return run_js_sync(window.map_view, "carto.draftCount()")


def js_coords(window):
    return run_js_sync(
        window.map_view,
        "draft.line.getLatLngs().map(function(p){return [p.lat, p.lng];})",
    )


def trace_enregistree(window, nom="Rallye", points=None) -> int:
    return window.db.create_track(nom, points=points or QUATRE_POINTS)


# ----------------------------------------------- reprise d'une trace (a)


def test_reprise_charge_les_points_dans_le_brouillon(window):
    track_id = trace_enregistree(window)
    window.tree_panel.refresh()

    assert window.resume_track(track_id) is True

    assert window.draft.track_id == track_id
    assert len(window.draft) == 4
    assert wait_for(lambda: js_draft(window) == 4, timeout_ms=5000)


def test_la_reprise_recadre_la_carte_sur_la_trace(window):
    """Sans recadrage, la trace reprise reste hors du champ visible."""
    loin = [Point(45.8326, 6.8652), Point(45.8400, 6.8700), Point(45.8500, 6.8800)]
    track_id = window.db.create_track("Chamonix", points=loin)
    window.map_view.set_view(48.93, 1.44, 13)
    wait_for(lambda: False, timeout_ms=300)

    window.resume_track(track_id)

    assert wait_for(
        lambda: 45.0 < run_js_sync(window.map_view, "map.getCenter().lat") < 46.0,
        timeout_ms=5000,
    )


def test_reprise_active_le_mode_saisie(window):
    track_id = trace_enregistree(window)
    window.resume_track(track_id)

    assert window.edit_mode is True


def test_prolongement_d_une_trace_reprise(window):
    track_id = trace_enregistree(window)
    window.resume_track(track_id)

    window.add_draft_point(48.935, 1.437)

    assert len(window.draft) == 5
    assert wait_for(lambda: js_draft(window) == 5, timeout_ms=5000)


def test_enregistrement_met_a_jour_la_trace_reprise(window):
    """Reprendre puis enregistrer ne doit pas créer un doublon."""
    track_id = trace_enregistree(window, "Rallye")
    window.resume_track(track_id)
    window.add_draft_point(48.935, 1.437)

    resultat = window.save_draft("Rallye")

    assert resultat == track_id
    assert len(window._all_tracks()) == 1
    assert window.db.count_points(track_id) == 5


def test_l_enregistrement_d_une_modification_ne_demande_rien(window, monkeypatch):
    """« Enregistrer les modifications » écrit directement, sans boîte de nom."""
    from PyQt6.QtWidgets import QInputDialog

    def refuser(*args, **kwargs):
        raise AssertionError("aucune boîte de dialogue ne doit s'ouvrir")

    track_id = trace_enregistree(window, "Rallye")
    window.resume_track(track_id)
    window.add_draft_point(48.935, 1.437)
    monkeypatch.setattr(QInputDialog, "getText", staticmethod(refuser))

    assert window.save_draft() == track_id

    assert window.db.get_track(track_id).name == "Rallye"   # nom inchangé
    assert window.db.count_points(track_id) == 5


def test_le_bouton_change_de_libelle_en_modification(window):
    track_id = trace_enregistree(window, "Rallye")

    assert window.action_save.text() == "Enregistrer la trace"

    window.resume_track(track_id)
    assert window.action_save.text() == "Enregistrer les modifications"

    window.save_draft()
    assert window.action_save.text() == "Enregistrer la trace"


def test_le_brouillon_se_detache_apres_enregistrement(window):
    track_id = trace_enregistree(window)
    window.resume_track(track_id)
    window.save_draft("Rallye")

    assert window.draft.is_existing is False
    assert window.draft.is_empty


def test_reprise_d_une_trace_vide_refusee(window):
    track_id = window.db.create_track("Vide", points=[])
    assert window.resume_track(track_id) is False


# ------------------------------------------------ fermeture en boucle (b)


def test_fermeture_de_la_boucle_sur_la_carte(window):
    window.set_edit_mode(True)
    for point in QUATRE_POINTS:
        window.add_draft_point(point.lat, point.lon)

    assert window.close_draft_loop() is True

    assert len(window.draft) == 5
    assert window.draft.is_loop is True
    assert wait_for(lambda: js_draft(window) == 5, timeout_ms=5000)
    coords = js_coords(window)
    assert coords[0] == coords[-1]


def test_action_fermer_la_boucle_grisee_a_bon_escient(window):
    assert window.action_close_loop.isEnabled() is False

    window.set_edit_mode(True)
    window.add_draft_point(48.930, 1.440)
    window.add_draft_point(48.931, 1.442)
    assert window.action_close_loop.isEnabled() is False  # deux points

    window.add_draft_point(48.932, 1.441)
    assert window.action_close_loop.isEnabled() is True

    window.close_draft_loop()
    assert window.action_close_loop.isEnabled() is False  # déjà fermée


def test_boucle_conservee_a_l_enregistrement(window):
    window.set_edit_mode(True)
    for point in QUATRE_POINTS:
        window.add_draft_point(point.lat, point.lon)
    window.close_draft_loop()

    track_id = window.save_draft("Boucle")

    assert window.db.get_track(track_id).is_loop is True


# ------------------------------------------- déplacement d'un point (c)


def test_deplacement_d_un_point_depuis_la_carte(window):
    track_id = trace_enregistree(window)
    window.resume_track(track_id)

    assert window.move_draft_point(1, 48.9999, 1.4999) is True

    assert window.draft.points[1].as_tuple() == (48.9999, 1.4999)
    assert wait_for(
        lambda: js_coords(window)[1] == [48.9999, 1.4999], timeout_ms=5000
    )


def test_glisser_un_point_sur_la_carte(window):
    """Simule le glissement réel : mousedown sur le repère, puis mouseup."""
    track_id = trace_enregistree(window)
    window.resume_track(track_id)
    assert wait_for(lambda: js_draft(window) == 4, timeout_ms=5000)

    run_js_sync(
        window.map_view,
        "var m = draft.vertices.getLayers()[2];"
        " m.fire('mousedown', {originalEvent: {}});"
        " map.fire('mousemove', {latlng: L.latLng(48.9500, 1.4500)});"
        " map.fire('mouseup', {latlng: L.latLng(48.9500, 1.4500)}); true",
    )

    assert wait_for(
        lambda: window.draft.points[2].as_tuple() == (48.95, 1.45),
        timeout_ms=5000,
    )


def test_le_glissement_ne_pose_pas_de_point_supplementaire(window):
    """Régression : le clic qui suit un glisser ne doit rien ajouter."""
    track_id = trace_enregistree(window)
    window.resume_track(track_id)
    assert wait_for(lambda: js_draft(window) == 4, timeout_ms=5000)

    run_js_sync(
        window.map_view,
        "var m = draft.vertices.getLayers()[1];"
        " m.fire('mousedown', {originalEvent: {}});"
        " map.fire('mousemove', {latlng: L.latLng(48.9400, 1.4400)});"
        " map.fire('mouseup', {latlng: L.latLng(48.9400, 1.4400)});"
        " map.fire('click', {latlng: L.latLng(48.9400, 1.4400)}); true",
    )
    wait_for(lambda: False, timeout_ms=600)

    assert len(window.draft) == 4


def test_deplacement_hors_bornes_sans_effet(window):
    window.set_edit_mode(True)
    window.add_draft_point(48.930, 1.440)

    assert window.move_draft_point(9, 48.0, 1.0) is False
    assert len(window.draft) == 1


# --------------------------------------------- suppression de points (d)


def test_suppression_d_un_point_par_clic_droit(window):
    track_id = trace_enregistree(window)
    window.resume_track(track_id)

    assert window.remove_draft_point(1) is True

    assert len(window.draft) == 3
    assert window.draft.points[1].as_tuple() == (48.932, 1.441)
    assert wait_for(lambda: js_draft(window) == 3, timeout_ms=5000)


def test_clic_droit_sur_un_repere_ouvre_le_menu(window, monkeypatch):
    """Le clic droit propose « Supprimer », il ne supprime plus directement."""
    track_id = trace_enregistree(window)
    window.resume_track(track_id)
    assert wait_for(lambda: js_draft(window) == 4, timeout_ms=5000)

    proposees = []

    def faux_exec(self, *args, **kwargs):
        proposees.extend(a.text() for a in self.actions())
        return None

    monkeypatch.setattr(QMenu, "exec", faux_exec)

    run_js_sync(
        window.map_view,
        "draft.vertices.getLayers()[1].fire('contextmenu',"
        " {originalEvent: {}, latlng: draft.line.getLatLngs()[1]}); true",
    )

    assert wait_for(lambda: bool(proposees), timeout_ms=5000)
    assert any("Supprimer le point 2" in texte for texte in proposees)
    assert any("Découper" in texte for texte in proposees)
    assert len(window.draft) == 4  # rien n'a encore été supprimé


def test_l_option_supprimer_retire_bien_le_point(window, monkeypatch):
    track_id = trace_enregistree(window)
    window.resume_track(track_id)

    declenchees = []

    def faux_exec(self, *args, **kwargs):
        # Déclenche l'option « Supprimer », comme le ferait l'utilisateur.
        for action in self.actions():
            if action.text().startswith("Supprimer"):
                declenchees.append(action.text())
                action.trigger()
        return None

    monkeypatch.setattr(QMenu, "exec", faux_exec)
    window.show_point_menu(1, 10, 10)

    assert declenchees
    assert len(window.draft) == 3
    assert window.draft.points[1].as_tuple() == (48.932, 1.441)


def test_le_menu_du_point_selectionne_le_point(window, monkeypatch):
    track_id = trace_enregistree(window)
    window.resume_track(track_id)
    monkeypatch.setattr(QMenu, "exec", lambda self, *a, **k: None)

    window.show_point_menu(2, 10, 10)

    assert window.points_panel.selected_indexes() == [2]


def test_suppression_d_une_selection_de_points(window):
    track_id = trace_enregistree(window)
    window.resume_track(track_id)

    assert window.remove_draft_points([0, 2]) is True

    assert [p.as_tuple() for p in window.draft.points] == [
        (48.931, 1.442), (48.933, 1.439),
    ]
    assert wait_for(lambda: js_draft(window) == 2, timeout_ms=5000)


def test_suppression_depuis_le_panneau_de_points(window):
    track_id = trace_enregistree(window)
    window.resume_track(track_id)
    panel = window.points_panel

    panel.list.item(0).setSelected(True)
    panel.list.item(1).setSelected(True)
    panel._request_delete()

    assert len(window.draft) == 2


# ------------------------------------------------ panneau de points (d)


def test_le_panneau_reflete_le_brouillon(window):
    window.set_edit_mode(True)
    for point in QUATRE_POINTS:
        window.add_draft_point(point.lat, point.lon)

    assert window.points_panel.list.count() == 4
    assert "48.93000" in window.points_panel.list.item(0).text()
    assert "Brouillon — 4 points" in window.points_panel.title.text()


def test_le_panneau_nomme_la_trace_reprise(window):
    track_id = trace_enregistree(window, "Rallye V1")
    window.resume_track(track_id)

    assert "« Rallye V1 » — 4 points" in window.points_panel.title.text()


def test_selection_dans_le_panneau_met_le_point_en_evidence(window):
    """Cliquer une ligne du panneau met le point en évidence sur la carte."""
    track_id = trace_enregistree(window)
    window.resume_track(track_id)

    window.points_panel.list.setCurrentRow(2)

    assert wait_for(
        lambda: run_js_sync(window.map_view, "carto.selectedPoint()") == 2,
        timeout_ms=5000,
    )


def test_clic_sur_un_point_de_la_carte_le_designe_dans_le_panneau(window):
    """Trajet inverse : un simple clic sur un repère sélectionne la ligne."""
    track_id = trace_enregistree(window)
    window.resume_track(track_id)
    assert wait_for(lambda: js_draft(window) == 4, timeout_ms=5000)

    run_js_sync(
        window.map_view,
        "var m = draft.vertices.getLayers()[2];"
        " m.fire('mousedown', {originalEvent: {}});"
        " map.fire('mouseup', {latlng: L.latLng(48.932, 1.441)}); true",
    )

    assert wait_for(
        lambda: window.points_panel.selected_indexes() == [2], timeout_ms=5000
    )
    assert len(window.draft) == 4  # un clic ne déplace ni n'ajoute rien


def test_boutons_du_panneau_grises_sans_selection(window):
    track_id = trace_enregistree(window)
    window.resume_track(track_id)
    panel = window.points_panel

    panel.list.clearSelection()
    panel._update_buttons()
    assert panel.delete_button.isEnabled() is False
    assert panel.split_button.isEnabled() is False

    panel.select_index(1)
    assert panel.delete_button.isEnabled() is True
    assert panel.split_button.isEnabled() is True


def test_decoupage_impossible_aux_extremites(window):
    track_id = trace_enregistree(window)
    window.resume_track(track_id)
    panel = window.points_panel

    panel.select_index(0)
    assert panel.split_button.isEnabled() is False

    panel.select_index(3)
    assert panel.split_button.isEnabled() is False


# ------------------------------- insertion d'un point sur un segment


def test_insertion_d_un_point_sur_un_segment(window):
    track_id = trace_enregistree(window)
    window.resume_track(track_id)

    assert window.insert_draft_point(2, 48.9315, 1.4415) is True

    assert len(window.draft) == 5
    assert window.draft.points[2].as_tuple() == (48.9315, 1.4415)
    assert window.draft.points[3].as_tuple() == (48.932, 1.441)  # décalé
    assert wait_for(lambda: js_draft(window) == 5, timeout_ms=5000)


def test_clic_sur_la_ligne_insere_un_point(window):
    """Un clic gauche sur un segment ajoute un point à cet endroit."""
    track_id = trace_enregistree(window)
    window.resume_track(track_id)
    assert wait_for(lambda: js_draft(window) == 4, timeout_ms=5000)

    # Point situé au milieu du segment entre le 1er et le 2e point.
    run_js_sync(
        window.map_view,
        "draft.line.fire('click', {latlng: L.latLng(48.9305, 1.441),"
        " originalEvent: {}}); true",
    )

    assert wait_for(lambda: len(window.draft) == 5, timeout_ms=5000)
    assert window.draft.points[1].as_tuple() == (48.9305, 1.441)


def test_le_clic_sur_la_ligne_n_ajoute_pas_a_la_fin(window):
    """Régression : le clic était aussi relayé à la carte, ajoutant un point."""
    track_id = trace_enregistree(window)
    window.resume_track(track_id)
    assert wait_for(lambda: js_draft(window) == 4, timeout_ms=5000)

    run_js_sync(
        window.map_view,
        "draft.line.fire('click', {latlng: L.latLng(48.9305, 1.441),"
        " originalEvent: {}});"
        " map.fire('click', {latlng: L.latLng(48.9305, 1.441)}); true",
    )
    wait_for(lambda: False, timeout_ms=700)

    assert len(window.draft) == 5
    assert window.draft.points[-1].as_tuple() == (48.933, 1.439)


def test_le_point_insere_est_selectionne(window):
    track_id = trace_enregistree(window)
    window.resume_track(track_id)

    window.insert_draft_point(2, 48.9315, 1.4415)

    assert window.points_panel.selected_indexes() == [2]


def test_insertion_hors_bornes_refusee(window):
    track_id = trace_enregistree(window)
    window.resume_track(track_id)

    assert window.insert_draft_point(99, 48.0, 1.0) is False
    assert len(window.draft) == 4


# ------------------------------------------------- altitude dans la liste


def test_altitude_affichee_dans_la_liste(window):
    points = [Point(48.930, 1.440, 70.0), Point(48.931, 1.442, 72.4),
              Point(48.932, 1.441)]
    track_id = window.db.create_track("Avec altitude", points=points)
    window.tree_panel.refresh()

    window.resume_track(track_id)

    lignes = [
        window.points_panel.list.item(i).text()
        for i in range(window.points_panel.list.count())
    ]
    assert "70 m" in lignes[0]
    assert "72 m" in lignes[1]
    assert "—" in lignes[2]  # altitude absente du fichier


def test_l_altitude_survit_au_deplacement_du_point(window):
    points = [Point(48.930, 1.440, 70.0), Point(48.931, 1.442, 72.4)]
    track_id = window.db.create_track("Avec altitude", points=points)
    window.tree_panel.refresh()
    window.resume_track(track_id)

    window.move_draft_point(0, 48.95, 1.45)

    assert "70 m" in window.points_panel.list.item(0).text()


# ------------------------------------------------------- découpage (e)


def test_decoupage_d_une_trace_reprise(window):
    track_id = trace_enregistree(window, "Longue")
    window.resume_track(track_id)

    resultat = window.split_draft(1)

    assert resultat is not None
    premier, second = resultat
    assert premier == track_id
    assert window.db.count_points(premier) == 2
    assert window.db.count_points(second) == 3
    assert window.db.get_track(second).name == "Longue (suite)"


def test_le_decoupage_prend_en_compte_les_modifications(window):
    """Les points ajoutés avant le découpage doivent être pris en compte."""
    track_id = trace_enregistree(window, "Longue")
    window.resume_track(track_id)
    window.add_draft_point(48.934, 1.437)  # 5e point

    _premier, second = window.split_draft(3)

    assert window.db.count_points(second) == 2
    assert window.db.get_points(second)[-1].as_tuple() == (48.934, 1.437)


def test_le_decoupage_termine_la_session_d_edition(window):
    track_id = trace_enregistree(window, "Longue")
    window.resume_track(track_id)

    window.split_draft(1)

    assert window.draft.is_empty
    assert window.draft.is_existing is False
    assert window.edit_mode is False


def test_decoupage_refuse_sur_un_brouillon_non_enregistre(window):
    window.set_edit_mode(True)
    for point in QUATRE_POINTS:
        window.add_draft_point(point.lat, point.lon)

    assert window.split_draft(1) is None
    assert len(window.draft) == 4  # rien n'a bougé


def test_decoupage_refuse_a_une_extremite(window):
    track_id = trace_enregistree(window, "Longue")
    window.resume_track(track_id)

    assert window.split_draft(0) is None
    assert window.db.count_points(track_id) == 4


# ---------------------------------------------------------- fusion (f)


def test_fusion_de_deux_traces(window):
    a = window.db.create_track("Aller", points=QUATRE_POINTS[:2])
    b = window.db.create_track("Retour", points=QUATRE_POINTS[2:])
    window.tree_panel.refresh()

    fusion = window.merge_track(a, b)

    assert fusion is not None
    assert window.db.count_points(fusion) == 4
    assert window.db.get_track(fusion).name == "Aller + Retour"
    assert window.db.get_track(a) is None
    assert window.db.get_track(b) is None


def test_la_trace_fusionnee_est_affichee(window):
    a = window.db.create_track("Aller", points=QUATRE_POINTS[:2])
    b = window.db.create_track("Retour", points=QUATRE_POINTS[2:])
    window.tree_panel.refresh()

    fusion = window.merge_track(a, b)

    assert window.visible_tracks == {fusion}
    assert wait_for(
        lambda: run_js_sync(window.map_view, f"carto.shownCount({fusion})") == 4,
        timeout_ms=5000,
    )


def test_fusion_impossible_sans_seconde_trace(window):
    seule = window.db.create_track("Seule", points=QUATRE_POINTS)
    window.tree_panel.refresh()

    assert window.merge_track(seule) is None
    assert window.db.get_track(seule) is not None


def test_les_traces_des_sous_dossiers_sont_candidates(window):
    """La fusion doit pouvoir viser une trace rangée ailleurs."""
    dossier = window.db.create_folder("Alpes")
    a = window.db.create_track("Aller", points=QUATRE_POINTS[:2])
    b = window.db.create_track("Retour", folder_id=dossier, points=QUATRE_POINTS[2:])
    window.tree_panel.refresh()

    fusion = window.merge_track(a, b)

    assert fusion is not None
    assert window.db.count_points(fusion) == 4


# ----------------------------------------------------- duplication (g)


def test_duplication_d_une_trace(window):
    track_id = trace_enregistree(window, "Rallye V1")
    window.tree_panel.refresh()

    copie = window.duplicate_track(track_id)

    assert copie is not None
    assert window.db.get_track(copie).name == "Rallye V1 (copie)"
    assert window.db.count_points(copie) == 4
    assert window.db.get_track(track_id) is not None  # l'original reste


def test_la_copie_est_selectionnee_dans_l_arborescence(window):
    from carto.ui.tree_panel import KIND_TRACK

    track_id = trace_enregistree(window, "Rallye")
    window.tree_panel.refresh()

    copie = window.duplicate_track(track_id)

    assert window.tree_panel.current_selection() == (KIND_TRACK, copie)


def test_duplication_dans_le_meme_dossier(window):
    dossier = window.db.create_folder("Alpes")
    track_id = window.db.create_track("Trace", folder_id=dossier,
                                      points=QUATRE_POINTS)
    window.tree_panel.refresh()

    copie = window.duplicate_track(track_id)

    assert window.db.get_track(copie).folder_id == dossier
