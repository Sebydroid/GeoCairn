"""Affichage simultané de plusieurs traces, ampoules et couleurs."""

from __future__ import annotations

import pytest
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QColorDialog, QInputDialog, QMessageBox

from carto.app import create_app
from carto.database import Database
from carto.models import Point
from carto.ui.icons import BULB_OFF, BULB_ON, BULB_PARTIAL, BULB_WIDTH
from carto.ui.main_window import MainWindow
from carto.ui.tree_panel import (
    COL_NAME,
    KIND_FOLDER,
    KIND_ROOT,
    KIND_TRACK,
    TRANSPARENCE_MAX,
    track_ids_under,
)
from tests.test_ui import run_js_sync, wait_for

TROIS = [Point(48.930, 1.440), Point(48.931, 1.442), Point(48.932, 1.441)]
LOIN = [Point(45.8326, 6.8652), Point(45.8400, 6.8700), Point(45.8500, 6.8800)]


@pytest.fixture(scope="session")
def qapp():
    app = create_app(["carto-tests"])
    yield app
    app.processEvents()


@pytest.fixture(scope="session")
def window(qapp, tmp_path_factory):
    database = Database(tmp_path_factory.mktemp("multi") / "carto.db")
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
    yield


def js_shown_ids(window) -> list[int]:
    return sorted(run_js_sync(window.map_view, "carto.shownTrackIds()") or [])


def bulb_state(window, kind, ident) -> str:
    item = (
        window.tree_panel.tree.topLevelItem(0)
        if kind == KIND_ROOT
        else window.tree_panel.find_item(kind, ident)
    )
    if kind == KIND_TRACK:
        return BULB_ON if int(ident) in window.visible_tracks else BULB_OFF
    return window.tree_panel.folder_state(item)


def deux_traces(window):
    a = window.db.create_track("Aller", points=TROIS)
    b = window.db.create_track("Retour", points=TROIS)
    window.tree_panel.refresh()
    return a, b


# ------------------------------------------------- plusieurs traces à la fois


def test_deux_traces_affichees_simultanement(window):
    a, b = deux_traces(window)

    window.show_track(a)
    window.show_track(b)

    assert window.visible_tracks == {a, b}
    assert wait_for(lambda: js_shown_ids(window) == sorted([a, b]), timeout_ms=5000)


def test_masquer_une_trace_laisse_les_autres(window):
    a, b = deux_traces(window)
    window.show_track(a)
    window.show_track(b)

    assert window.hide_track(a) is True

    assert window.visible_tracks == {b}
    assert wait_for(lambda: js_shown_ids(window) == [b], timeout_ms=5000)


def test_masquer_une_trace_deja_masquee(window):
    a, _b = deux_traces(window)
    assert window.hide_track(a) is False


def test_chaque_trace_garde_sa_couleur(window):
    a, b = deux_traces(window)
    window.db.set_track_style(a, color="#ff8800", opacity=0.5)
    window.show_track(a)
    window.show_track(b)

    assert wait_for(lambda: js_shown_ids(window) == sorted([a, b]), timeout_ms=5000)
    assert run_js_sync(
        window.map_view, f"shownTracks[{a}].line.options.color"
    ) == "#ff8800"
    assert run_js_sync(
        window.map_view, f"shownTracks[{a}].line.options.opacity"
    ) == pytest.approx(0.5)
    assert run_js_sync(
        window.map_view, f"shownTracks[{b}].line.options.color"
    ) == "#1f5fbf"


# ------------------------------------------------- affichage mémorisé


def test_l_affichage_est_ecrit_en_base(window):
    a, b = deux_traces(window)

    window.show_track(a)

    assert window.db.get_track(a).visible is True
    assert window.db.get_track(b).visible is False


def test_le_masquage_est_ecrit_en_base(window):
    a, _b = deux_traces(window)
    window.show_track(a)

    window.hide_track(a)

    assert window.db.get_track(a).visible is False


def test_liste_des_traces_a_reafficher(window):
    a, b = deux_traces(window)
    window.show_track(a)
    window.show_track(b)
    window.hide_track(a)

    assert window.db.visible_track_ids() == [b]


def test_la_reprise_ne_perd_pas_la_memorisation(window):
    """La trace reprise sort de l'affichage simple mais reste mémorisée."""
    a, _b = deux_traces(window)
    window.show_track(a)

    window.resume_track(a)

    assert a not in window.visible_tracks
    assert window.db.get_track(a).visible is True

    window.draft.reset()
    window.set_edit_mode(False)
    window.map_view.clear_draft()


def test_une_trace_neuve_n_est_pas_affichee_par_defaut(window):
    a, _b = deux_traces(window)
    assert window.db.get_track(a).visible is False


# ------------------------------------------------------------- ampoules


def test_ampoule_eteinte_par_defaut(window):
    a, _b = deux_traces(window)
    assert bulb_state(window, KIND_TRACK, a) == BULB_OFF


def test_clic_sur_l_ampoule_affiche_puis_masque(window):
    a, _b = deux_traces(window)

    window.toggle_visibility(KIND_TRACK, a)
    assert a in window.visible_tracks
    assert bulb_state(window, KIND_TRACK, a) == BULB_ON

    window.toggle_visibility(KIND_TRACK, a)
    assert a not in window.visible_tracks
    assert bulb_state(window, KIND_TRACK, a) == BULB_OFF


def test_l_ampoule_est_accolee_au_nom(window):
    """L'arbre n'a qu'une colonne : l'ampoule précède le logo dans l'icône."""
    a, _b = deux_traces(window)
    window.show_track(a)

    tree = window.tree_panel.tree
    item = window.tree_panel.find_item(KIND_TRACK, a)

    assert tree.columnCount() == 1
    icone = item.icon(COL_NAME)
    assert not icone.isNull()
    # L'icône composite est plus large que haute : ampoule + logo.
    taille = icone.availableSizes()[0]
    assert taille.width() > taille.height()
    # La vue doit lui laisser toute sa largeur, sans quoi elle serait écrasée.
    assert tree.iconSize().width() >= taille.width()
    assert tree.iconSize().height() >= taille.height()


def test_l_ampoule_reste_cliquable_en_profondeur(window):
    """La zone cliquable suit l'indentation de l'élément."""
    dossier = window.db.create_folder("Rallye")
    sous = window.db.create_folder("2026", parent_id=dossier)
    profonde = window.db.create_track("Enfouie", folder_id=sous, points=TROIS)
    window.tree_panel.refresh()
    window.tree_panel.find_item(KIND_FOLDER, dossier).setExpanded(True)
    window.tree_panel.find_item(KIND_FOLDER, sous).setExpanded(True)

    tree = window.tree_panel.tree
    racine = tree.topLevelItem(0)
    item = window.tree_panel.find_item(KIND_TRACK, profonde)

    # Plus l'élément est profond, plus son icône est décalée vers la droite.
    assert tree.icon_left(item) > tree.icon_left(racine)
    assert tree.is_bulb_click(item, tree.icon_left(item) + 2) is True
    assert tree.is_bulb_click(item, tree.icon_left(item) + BULB_WIDTH + 8) is False
    # Un clic à l'emplacement de l'ampoule de la racine ne vise pas celle-ci.
    assert tree.is_bulb_click(item, tree.icon_left(racine) + 2) is False


def test_clic_sur_l_ampoule_bascule_l_affichage_pas_le_nom(window):
    a, _b = deux_traces(window)
    tree = window.tree_panel.tree
    item = window.tree_panel.find_item(KIND_TRACK, a)
    gauche = tree.icon_left(item)

    assert tree.is_bulb_click(item, gauche + 2) is True
    window.tree_panel._on_bulb_clicked(item)
    assert a in window.visible_tracks

    # Un clic sur le texte est loin à droite : ce n'est pas l'ampoule.
    assert tree.is_bulb_click(item, gauche + 120) is False


def test_ampoule_de_dossier_partielle(window):
    dossier = window.db.create_folder("Rallye")
    a = window.db.create_track("Aller", folder_id=dossier, points=TROIS)
    window.db.create_track("Retour", folder_id=dossier, points=TROIS)
    window.tree_panel.refresh()

    assert bulb_state(window, KIND_FOLDER, dossier) == BULB_OFF

    window.show_track(a)
    assert bulb_state(window, KIND_FOLDER, dossier) == BULB_PARTIAL

    window.show_items(KIND_FOLDER, dossier)
    assert bulb_state(window, KIND_FOLDER, dossier) == BULB_ON


def test_ampoule_de_dossier_affiche_tout_le_contenu(window):
    dossier = window.db.create_folder("Rallye")
    sous = window.db.create_folder("2026", parent_id=dossier)
    a = window.db.create_track("Aller", folder_id=dossier, points=TROIS)
    b = window.db.create_track("Retour", folder_id=sous, points=TROIS)
    window.tree_panel.refresh()

    window.toggle_visibility(KIND_FOLDER, dossier)

    assert window.visible_tracks == {a, b}
    assert wait_for(lambda: js_shown_ids(window) == sorted([a, b]), timeout_ms=5000)


def test_ampoule_de_dossier_masque_tout(window):
    dossier = window.db.create_folder("Rallye")
    a = window.db.create_track("Aller", folder_id=dossier, points=TROIS)
    b = window.db.create_track("Retour", folder_id=dossier, points=TROIS)
    window.tree_panel.refresh()
    window.show_items(KIND_FOLDER, dossier)

    window.toggle_visibility(KIND_FOLDER, dossier)

    assert window.visible_tracks == set()
    assert a not in window.visible_tracks and b not in window.visible_tracks


def test_ampoule_de_dossier_partiel_affiche_le_reste(window):
    """Sur un dossier à moitié affiché, le clic complète plutôt qu'il ne masque."""
    dossier = window.db.create_folder("Rallye")
    a = window.db.create_track("Aller", folder_id=dossier, points=TROIS)
    b = window.db.create_track("Retour", folder_id=dossier, points=TROIS)
    window.tree_panel.refresh()
    window.show_track(a)

    window.toggle_visibility(KIND_FOLDER, dossier)

    assert window.visible_tracks == {a, b}


# --------------------------------------------------- menu contextuel


def test_afficher_depuis_le_menu(window):
    a, _b = deux_traces(window)

    window.show_items(KIND_TRACK, a)

    assert a in window.visible_tracks


def test_afficher_seulement_ceci(window):
    a, b = deux_traces(window)
    window.show_track(a)
    window.show_track(b)

    window.show_only(KIND_TRACK, a)

    assert window.visible_tracks == {a}
    assert wait_for(lambda: js_shown_ids(window) == [a], timeout_ms=5000)


def test_afficher_seulement_un_dossier(window):
    dossier = window.db.create_folder("Rallye")
    a = window.db.create_track("Aller", folder_id=dossier, points=TROIS)
    b = window.db.create_track("Retour", folder_id=dossier, points=TROIS)
    hors = window.db.create_track("Ailleurs", points=TROIS)
    window.tree_panel.refresh()
    window.show_track(hors)

    window.show_only(KIND_FOLDER, dossier)

    assert window.visible_tracks == {a, b}


def test_masquer_depuis_le_menu(window):
    a, b = deux_traces(window)
    window.show_track(a)
    window.show_track(b)

    window.hide_items(KIND_TRACK, b)

    assert window.visible_tracks == {a}


def test_afficher_et_masquer_tout_depuis_la_racine(window):
    a, b = deux_traces(window)

    window.show_items(KIND_ROOT, None)
    assert window.visible_tracks == {a, b}

    window.hide_items(KIND_ROOT, None)
    assert window.visible_tracks == set()


def test_zoom_sur_la_trace(window):
    window.db.create_track("Ici", points=TROIS)
    loin_id = window.db.create_track("Chamonix", points=LOIN)
    window.tree_panel.refresh()
    window.map_view.set_view(48.93, 1.44, 13)
    wait_for(lambda: False, timeout_ms=300)

    assert window.zoom_to_items(KIND_TRACK, loin_id) is True

    # Délai large : l'affichage puis le recadrage font deux allers-retours vers
    # le JavaScript, que la charge de la suite complète peut ralentir.
    assert wait_for(
        lambda: 45.0 < run_js_sync(window.map_view, "map.getCenter().lat") < 46.0,
        timeout_ms=15000,
    )


def test_le_zoom_affiche_la_trace_si_besoin(window):
    """Zoomer sur une trace masquée n'aurait rien montré."""
    loin_id = window.db.create_track("Chamonix", points=LOIN)
    window.tree_panel.refresh()

    window.zoom_to_items(KIND_TRACK, loin_id)

    assert loin_id in window.visible_tracks


def test_zoom_sur_un_dossier_englobe_ses_traces(window):
    dossier = window.db.create_folder("Rallye")
    window.db.create_track("Ici", folder_id=dossier, points=TROIS)
    window.db.create_track("Chamonix", folder_id=dossier, points=LOIN)
    window.tree_panel.refresh()

    assert window.zoom_to_items(KIND_FOLDER, dossier) is True

    # Le cadrage doit couvrir les deux traces : le centre tombe entre elles.
    assert wait_for(
        lambda: 45.0 < run_js_sync(window.map_view, "map.getCenter().lat") < 49.0,
        timeout_ms=5000,
    )
    assert run_js_sync(window.map_view, "map.getZoom()") < 10


def test_zoom_sur_un_dossier_vide(window):
    dossier = window.db.create_folder("Vide")
    window.tree_panel.refresh()

    assert window.zoom_to_items(KIND_FOLDER, dossier) is False


def test_traces_d_un_item(window):
    dossier = window.db.create_folder("Rallye")
    a = window.db.create_track("Aller", folder_id=dossier, points=TROIS)
    b = window.db.create_track("Retour", points=TROIS)
    window.tree_panel.refresh()

    assert window.tracks_of(KIND_TRACK, a) == [a]
    assert window.tracks_of(KIND_FOLDER, dossier) == [a]
    assert sorted(window.tracks_of(KIND_ROOT, None)) == sorted([a, b])


# ------------------------------------------------------------- couleur


def test_couleur_predefinie(window):
    a, _b = deux_traces(window)
    window.show_track(a)

    assert window.tree_panel.set_track_color(a, "#e6194b") is True

    assert window.db.get_track(a).color == "#e6194b"
    assert wait_for(
        lambda: run_js_sync(
            window.map_view, f"shownTracks[{a}].line.options.color"
        ) == "#e6194b",
        timeout_ms=5000,
    )


def test_la_couleur_teinte_le_nom_dans_l_arborescence(window):
    a, _b = deux_traces(window)

    window.tree_panel.set_track_color(a, "#e6194b")

    item = window.tree_panel.find_item(KIND_TRACK, a)
    assert item.foreground(COL_NAME).color().name() == "#e6194b"


def test_couleur_personnalisee(window, monkeypatch):
    a, _b = deux_traces(window)
    window.show_track(a)
    monkeypatch.setattr(
        QColorDialog, "getColor", staticmethod(lambda *a, **k: QColor("#8b2fc9"))
    )

    assert window.tree_panel.choose_track_color(a) is True

    assert window.db.get_track(a).color == "#8b2fc9"
    assert wait_for(
        lambda: run_js_sync(
            window.map_view, f"shownTracks[{a}].line.options.color"
        ) == "#8b2fc9",
        timeout_ms=5000,
    )


# ------------------------------------------------- transparence en %


@pytest.mark.parametrize(
    "pourcentage, opacite", [(0, 1.0), (25, 0.75), (50, 0.5), (75, 0.25)]
)
def test_transparence_en_pourcentage(window, pourcentage, opacite):
    a, _b = deux_traces(window)

    assert window.tree_panel.set_track_transparency(a, pourcentage) is True

    assert window.db.get_track(a).opacity == pytest.approx(opacite)


def test_la_transparence_s_applique_sur_la_carte(window):
    a, _b = deux_traces(window)
    window.show_track(a)

    window.tree_panel.set_track_transparency(a, 60)

    assert wait_for(
        lambda: run_js_sync(
            window.map_view, f"shownTracks[{a}].line.options.opacity"
        ) == pytest.approx(0.4, abs=0.01),
        timeout_ms=5000,
    )


def test_transparence_bornee_pour_rester_visible(window):
    a, _b = deux_traces(window)

    window.tree_panel.set_track_transparency(a, 100)

    # 100 % rendrait la trace introuvable : la valeur est ramenée au maximum.
    assert window.db.get_track(a).opacity == pytest.approx(1 - TRANSPARENCE_MAX / 100)


def test_transparence_saisie_par_l_utilisateur(window, monkeypatch):
    a, _b = deux_traces(window)
    monkeypatch.setattr(
        QInputDialog, "getInt", staticmethod(lambda *a, **k: (30, True))
    )

    assert window.tree_panel.choose_track_transparency(a) is True
    assert window.db.get_track(a).opacity == pytest.approx(0.7)


def test_annulation_de_la_saisie_de_transparence(window, monkeypatch):
    a, _b = deux_traces(window)
    monkeypatch.setattr(
        QInputDialog, "getInt", staticmethod(lambda *a, **k: (30, False))
    )

    assert window.tree_panel.choose_track_transparency(a) is False
    assert window.db.get_track(a).opacity == pytest.approx(0.9)


def test_annulation_du_selecteur_de_couleur(window, monkeypatch):
    a, _b = deux_traces(window)
    monkeypatch.setattr(
        QColorDialog, "getColor", staticmethod(lambda *a, **k: QColor())
    )

    assert window.tree_panel.choose_track_color(a) is False
    assert window.db.get_track(a).color == "#1f5fbf"


def test_la_couleur_survit_au_reaffichage(window):
    a, _b = deux_traces(window)
    window.tree_panel.set_track_color(a, "#f08c00")

    window.show_track(a)

    assert wait_for(
        lambda: run_js_sync(
            window.map_view, f"shownTracks[{a}].line.options.color"
        ) == "#f08c00",
        timeout_ms=5000,
    )


# --------------------------------------------------------- cohérence


def test_une_trace_supprimee_quitte_la_carte(window):
    a, b = deux_traces(window)
    window.show_track(a)
    window.show_track(b)
    window.tree_panel.select_track(a)

    window.tree_panel.delete_selected(confirm=False)

    assert window.visible_tracks == {b}
    assert wait_for(lambda: js_shown_ids(window) == [b], timeout_ms=5000)


def test_un_dossier_supprime_retire_ses_traces_de_la_carte(window):
    dossier = window.db.create_folder("Rallye")
    a = window.db.create_track("Aller", folder_id=dossier, points=TROIS)
    hors = window.db.create_track("Ailleurs", points=TROIS)
    window.tree_panel.refresh()
    window.show_track(a)
    window.show_track(hors)
    window.tree_panel.select_folder(dossier)

    window.tree_panel.delete_selected(confirm=False)

    assert window.visible_tracks == {hors}


def test_la_reprise_retire_la_trace_de_l_affichage_simple(window):
    """Sinon le tracé bleu et le brouillon rouge se superposeraient."""
    a, _b = deux_traces(window)
    window.show_track(a)

    window.resume_track(a)

    assert a not in window.visible_tracks
    assert wait_for(lambda: js_shown_ids(window) == [], timeout_ms=5000)

    window.draft.reset()
    window.set_edit_mode(False)
    window.map_view.clear_draft()


def test_les_ampoules_suivent_l_affichage(window):
    a, b = deux_traces(window)

    window.show_track(a)

    assert bulb_state(window, KIND_TRACK, a) == BULB_ON
    assert bulb_state(window, KIND_TRACK, b) == BULB_OFF
    assert bulb_state(window, KIND_ROOT, None) == BULB_PARTIAL


def test_traces_sous_un_item_en_profondeur(window):
    dossier = window.db.create_folder("Rallye")
    sous = window.db.create_folder("2026", parent_id=dossier)
    a = window.db.create_track("Aller", folder_id=dossier, points=TROIS)
    b = window.db.create_track("Retour", folder_id=sous, points=TROIS)
    window.tree_panel.refresh()

    item = window.tree_panel.find_item(KIND_FOLDER, dossier)

    assert sorted(track_ids_under(item)) == sorted([a, b])
