"""Zoom du profil, sélection multiple et mise en page."""

from __future__ import annotations

import pytest
from PyQt6.QtCore import QPoint, QPointF, Qt
from PyQt6.QtGui import QWheelEvent
from PyQt6.QtWidgets import QMessageBox

from geocairn.app import create_app
from geocairn.database import Database
from geocairn.models import Point
from geocairn.ui.main_window import MainWindow
from geocairn.ui.profile_panel import SOURCE_ELE_FICHIER, ProfilePanel
from geocairn.ui.toolbar_icons import toolbar_icon
from tests.test_ui import run_js_sync, wait_for

DIX = [Point(48.90 + i / 100, 1.44, 100.0 + i * 10) for i in range(10)]


@pytest.fixture(scope="session")
def qapp():
    app = create_app(["geocairn-tests"])
    yield app
    app.processEvents()


@pytest.fixture
def panel(qapp):
    widget = ProfilePanel()
    widget.resize(600, 200)
    widget.set_points(DIX, "Test")
    return widget


def molette(vue, x: float, cran: int) -> None:
    vue.wheelEvent(
        QWheelEvent(
            QPointF(x, 60),
            QPointF(x, 60),
            QPoint(0, 0),
            QPoint(0, cran),
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier,
            Qt.ScrollPhase.NoScrollPhase,
            False,
        )
    )


# ---------------------------------------------------------------- zoom


def test_vue_complete_au_depart(panel):
    assert panel.view.view_range == (0.0, 1.0)


def test_la_molette_resserre_la_vue(panel):
    zone = panel.view._plot_rect()

    molette(panel.view, zone.center().x(), 120)

    debut, fin = panel.view.view_range
    assert fin - debut < 1.0
    assert debut > 0.0 and fin < 1.0   # resserré autour du centre


def test_la_molette_inverse_elargit(panel):
    zone = panel.view._plot_rect()
    molette(panel.view, zone.center().x(), 120)
    resserre = panel.view.view_range

    molette(panel.view, zone.center().x(), -120)

    largeur = panel.view.view_range[1] - panel.view.view_range[0]
    assert largeur > resserre[1] - resserre[0]


def test_le_zoom_reste_dans_les_bornes(panel):
    zone = panel.view._plot_rect()
    for _ in range(30):
        molette(panel.view, zone.left(), 120)

    debut, fin = panel.view.view_range
    assert debut >= 0.0 and fin <= 1.0
    assert fin > debut


def test_le_dezoom_ne_depasse_pas_la_trace(panel):
    zone = panel.view._plot_rect()
    for _ in range(20):
        molette(panel.view, zone.center().x(), -120)

    assert panel.view.view_range == (0.0, 1.0)


def test_le_zoom_se_fait_autour_du_curseur(panel):
    zone = panel.view._plot_rect()

    molette(panel.view, zone.left() + 2, 120)

    debut, _fin = panel.view.view_range
    assert debut < 0.1   # la vue reste calée à gauche


def test_double_clic_remet_la_vue_a_plat(panel):
    zone = panel.view._plot_rect()
    molette(panel.view, zone.center().x(), 120)

    panel.view.reset_zoom()

    assert panel.view.view_range == (0.0, 1.0)


def test_le_zoom_ne_touche_que_l_axe_des_abscisses(panel):
    """L'échelle verticale suit la partie visible, elle n'est pas figée."""
    zone = panel.view._plot_rect()
    molette(panel.view, zone.left() + 5, 120)

    visibles = panel.view.visible_indexes()

    assert len(visibles) < len(DIX)
    assert 0 in visibles   # le début de la trace reste affiché


def test_l_indice_sous_le_curseur_suit_le_zoom(panel):
    zone = panel.view._plot_rect()
    assert panel.view.index_at(zone.right()) == 9

    molette(panel.view, zone.left() + 2, 120)

    # Une fois zoomé au début, le bord droit ne montre plus la fin.
    assert panel.view.index_at(zone.right()) < 9


def test_changer_de_trace_remet_la_vue_a_plat(panel):
    zone = panel.view._plot_rect()
    molette(panel.view, zone.center().x(), 120)

    panel.set_points([Point(45.0, 3.0, 10.0), Point(46.0, 3.0, 20.0)], "Autre")

    assert panel.view.view_range == (0.0, 1.0)


def test_cocher_une_grandeur_ne_defait_pas_le_zoom(panel):
    zone = panel.view._plot_rect()
    molette(panel.view, zone.center().x(), 120)
    avant = panel.view.view_range

    panel.set_source(SOURCE_ELE_FICHIER)

    assert panel.view.view_range == avant


def test_le_trace_zoome_se_dessine(panel):
    zone = panel.view._plot_rect()
    molette(panel.view, zone.center().x(), 120)
    panel.view.grab()   # ne doit pas lever


# -------------------------------------------------- sélection multiple


def test_selection_multiple_dans_le_profil(panel):
    panel.select_indexes([1, 3, 5])

    assert panel.selected_indexes == [1, 3, 5]
    assert panel.selected == 1
    panel.view.grab()


def test_selection_simple_puis_multiple(panel):
    panel.select_index(2)
    assert panel.selected_indexes == [2]

    panel.select_indexes([4, 6])
    assert panel.selected_indexes == [4, 6]


def test_selection_vide(panel):
    panel.select_indexes([])
    assert panel.selected is None


# ------------------------------------------------------ mise en page


def test_le_resume_tient_sur_une_ligne(qapp):
    """Régression : le résumé prenait la moitié de la hauteur du panneau."""
    panel = ProfilePanel()
    panel.set_points(DIX, "Test")
    panel.resize(600, 400)
    panel.show()
    qapp.processEvents()

    hauteur_resume = panel.stats.height()
    hauteur_trace = panel.view.height()

    assert hauteur_resume < 40
    assert hauteur_trace > panel.height() * 0.6
    panel.close()


def test_le_trace_profite_de_l_agrandissement(qapp):
    panel = ProfilePanel()
    panel.set_points(DIX, "Test")
    panel.resize(600, 200)
    panel.show()
    qapp.processEvents()
    petit = panel.view.height()

    panel.resize(600, 500)
    qapp.processEvents()

    assert panel.view.height() > petit + 250
    panel.close()


# ---------------------------------------------------------- icônes


@pytest.mark.parametrize(
    "nom",
    ["import", "export", "creer", "modifier", "annuler", "boucle",
     "enregistrer", "effacer"],
)
def test_les_icones_de_la_barre_sont_dessinees(qapp, nom):
    icone = toolbar_icon(nom)

    assert not icone.isNull()
    image = icone.pixmap(22, 22).toImage()
    dessines = sum(
        1
        for y in range(image.height())
        for x in range(image.width())
        if image.pixelColor(x, y).alpha() > 0
    )
    assert dessines > 25, f"l'icône « {nom} » est presque vide"


def test_les_icones_se_distinguent(qapp):
    creer = toolbar_icon("creer").pixmap(22, 22).toImage()
    modifier = toolbar_icon("modifier").pixmap(22, 22).toImage()
    assert creer != modifier


def test_les_icones_sont_mises_en_cache(qapp):
    assert toolbar_icon("import") is toolbar_icon("import")


# ------------------------------------------- intégration trois vues


@pytest.fixture(scope="session")
def window(qapp, tmp_path_factory):
    database = Database(tmp_path_factory.mktemp("zoom") / "geocairn.db")
    win = MainWindow(db=database)
    win.show()
    assert wait_for(lambda: win.map_view.is_ready), "carte non chargée"
    yield win
    win.close()


@pytest.fixture(autouse=True)
def etat_vierge(window, monkeypatch):
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: None))
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: None))
    for track in window.db.list_tracks(None):
        window.db.delete_track(track.id)
    window.visible_tracks.clear()
    window.map_view.clear_tracks()
    window.map_view.clear_focus()
    window.draft.reset()
    window.set_edit_mode(False)
    window.map_view.clear_draft()
    window.tree_panel.refresh()
    yield


def test_plusieurs_points_selectionnes_dans_les_trois_vues(window):
    track_id = window.db.create_track("Trace", points=DIX)
    window.tree_panel.refresh()
    window.tree_panel.select_track(track_id)

    assert window.select_points([1, 3, 5]) == 3

    assert window.profile_panel.selected_indexes == [1, 3, 5]
    assert wait_for(
        lambda: run_js_sync(window.map_view, "geocairn.focusCount()") == 3,
        timeout_ms=5000,
    )


def test_selection_multiple_depuis_la_liste(window):
    track_id = window.db.create_track("Trace", points=DIX)
    window.tree_panel.refresh()
    window.tree_panel.select_track(track_id)

    for rang in (2, 4, 6):
        window.points_panel.list.item(rang).setSelected(True)

    assert window.profile_panel.selected_indexes == [2, 4, 6]


def test_selection_multiple_en_edition(window):
    track_id = window.db.create_track("Trace", points=DIX)
    window.tree_panel.refresh()
    window.resume_track(track_id)

    window.select_points([0, 2, 4])

    assert wait_for(
        lambda: run_js_sync(window.map_view, "geocairn.selectedPoints()") == [0, 2, 4],
        timeout_ms=5000,
    )
