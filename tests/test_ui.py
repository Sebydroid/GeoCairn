"""Tests d'intégration de l'interface (Qt en mode offscreen).

Vérifie que la fenêtre se construit, que l'arborescence reflète la base, et que
la carte Leaflet se charge réellement et dialogue avec Python (QWebChannel).
"""

from __future__ import annotations

import pytest
from PyQt6.QtCore import QEventLoop, QTimer
from PyQt6.QtWidgets import QApplication, QToolBar

from carto.app import create_app
from carto.database import Database
from carto.ui.main_window import MainWindow
from carto.ui.map_view import LAYER_NAMES, MapView
from carto.ui.points_panel import PointsPanel
from carto.ui.profile_panel import ProfilePanel
from carto.ui.tree_panel import (
    COL_NAME,
    KIND_FOLDER,
    KIND_TRACK,
    ROLE_ID,
    ROLE_KIND,
    TreePanel,
)

MAP_LOAD_TIMEOUT_MS = 20000


@pytest.fixture(scope="session")
def qapp():
    app = create_app(["carto-tests"])
    yield app
    app.processEvents()


def wait_for(condition, timeout_ms=MAP_LOAD_TIMEOUT_MS) -> bool:
    """Fait tourner la boucle d'évènements Qt jusqu'à ce que `condition` soit vraie.

    Le minuteur est arrêté pendant l'évaluation de la condition. Sans cela, une
    condition qui ouvre elle-même une boucle — c'est le cas de run_js_sync, qui
    attend une réponse du JavaScript — verrait ce minuteur se redéclencher au
    milieu, empilant les boucles imbriquées : loop.quit() s'appliquait alors à
    une boucle qui n'était pas celle en cours, et l'attente échouait alors même
    que la condition était satisfaite.
    """
    loop = QEventLoop()
    elapsed = {"ms": 0}
    timer = QTimer()

    def tick():
        timer.stop()
        elapsed["ms"] += 50
        if condition() or elapsed["ms"] >= timeout_ms:
            loop.quit()
        else:
            timer.start(50)

    timer.timeout.connect(tick)
    if condition():
        return True
    timer.start(50)
    loop.exec()
    timer.stop()
    return condition()


def run_js_sync(view: MapView, script: str, timeout_ms=5000):
    """Exécute du JavaScript et retourne son résultat de façon synchrone."""
    result = {}

    def callback(value):
        result["value"] = value

    view.page().runJavaScript(script, callback)
    wait_for(lambda: "value" in result, timeout_ms)
    return result.get("value")


# ---------------------------------------------------------------- régression


def test_qapplication_recoit_toujours_un_argv0(qapp):
    """Régression : QtWebEngine tue le processus si argv[0] est absent.

    (« Argument list is empty, the program name is not passed to
    QCoreApplication. base::CommandLine cannot be properly initialized. »)
    """
    assert QApplication.instance() is qapp
    assert len(qapp.arguments()) >= 1
    assert qapp.arguments()[0]


# ------------------------------------------------------------------- fenêtre


def test_fenetre_principale_quatre_panneaux(qapp, db):
    """Bibliothèque et points à gauche ; carte et profil à droite."""
    window = MainWindow(db=db)
    splitter = window.centralWidget()
    gauche, droite = splitter.widget(0), splitter.widget(1)

    assert splitter.count() == 2
    assert gauche.count() == 2
    assert isinstance(gauche.widget(0), TreePanel)
    assert isinstance(gauche.widget(1), PointsPanel)
    assert droite.count() == 2
    assert isinstance(droite.widget(0), MapView)
    assert isinstance(droite.widget(1), ProfilePanel)
    assert "Carto" in window.windowTitle()

    window.close()


def test_barre_d_outils_sans_doublons(qapp, db):
    """Le fond de carte et « Nouveau dossier » ne sont plus dans la barre.

    Ils restent accessibles ailleurs : sélecteur de couches de la carte pour
    l'un, clic droit dans l'arborescence pour l'autre.
    """
    window = MainWindow(db=db)
    barre = window.findChildren(QToolBar)[0]
    libelles = [a.text() for a in barre.actions() if a.text()]

    assert libelles[:2] == ["Importer un GPX", "Exporter en GPX"]
    assert "Nouveau dossier" not in libelles
    assert not hasattr(window, "layer_combo")

    window.close()




# -------------------------------------------------------------- arborescence


def test_arborescence_reflete_la_base(qapp, db, sample_points):
    folder = db.create_folder("Alpes")
    sub = db.create_folder("2026", parent_id=folder)
    db.create_track("Trace du col", folder_id=sub, points=sample_points)
    db.create_track("Trace racine", points=sample_points)

    panel = TreePanel(db)
    root = panel.tree.topLevelItem(0)

    assert panel.tree.topLevelItemCount() == 1
    labels = [root.child(i).text(COL_NAME) for i in range(root.childCount())]
    assert labels == ["Alpes", "Trace racine"]

    alpes = root.child(0)
    assert alpes.child(0).text(COL_NAME) == "2026"
    assert alpes.child(0).child(0).text(COL_NAME) == "Trace du col"


def test_arborescence_sans_doublons_apres_rafraichissements(qapp, db, sample_points):
    db.create_folder("Alpes")
    db.create_track("Trace", points=sample_points)

    panel = TreePanel(db)
    for _ in range(3):
        panel.refresh()

    root = panel.tree.topLevelItem(0)
    labels = [root.child(i).text(COL_NAME) for i in range(root.childCount())]

    assert panel.tree.topLevelItemCount() == 1
    assert len(labels) == len(set(labels)) == 2


def test_double_clic_sur_trace_emet_le_signal(qapp, db, sample_points):
    track_id = db.create_track("Trace", points=sample_points)
    panel = TreePanel(db)
    received = []
    panel.track_activated.connect(received.append)

    root = panel.tree.topLevelItem(0)
    item = root.child(0)
    assert item.data(0, ROLE_KIND) == KIND_TRACK
    panel._on_double_click(item, 0)

    assert received == [track_id]


def test_dossier_courant_pour_creation(qapp, db, sample_points):
    folder = db.create_folder("Alpes")
    db.create_track("Trace", folder_id=folder, points=sample_points)
    panel = TreePanel(db)
    root = panel.tree.topLevelItem(0)

    panel.tree.setCurrentItem(root.child(0))  # le dossier
    assert panel.current_folder_id() == folder

    panel.tree.setCurrentItem(root.child(0).child(0))  # la trace dedans
    assert panel.current_folder_id() == folder

    panel.tree.setCurrentItem(root)
    assert panel.current_folder_id() is None


# ----------------------------------------------------------------- carte web


@pytest.fixture(scope="session")
def loaded_map(qapp):
    """Une carte réellement chargée, partagée par les tests (chargement lent)."""
    view = MapView()
    view.resize(800, 600)
    view.show()
    assert wait_for(lambda: view.is_ready), (
        "La carte n'a pas signalé sa disponibilité : Leaflet ou QWebChannel n'a pas "
        "pu être chargé."
    )
    yield view
    view.close()


def test_carte_chargee_et_pont_actif(loaded_map):
    assert loaded_map.is_ready is True
    assert run_js_sync(loaded_map, "typeof L") == "object"
    assert run_js_sync(loaded_map, "carto.isReady()") is True
    assert run_js_sync(loaded_map, "bridge !== null") is True


def test_couches_javascript_identiques_a_python(loaded_map):
    assert run_js_sync(loaded_map, "carto.layerNames()") == LAYER_NAMES


def test_le_selecteur_de_couches_reste_sur_la_carte(loaded_map):
    """Le fond de carte se choisit dans le contrôle Leaflet, pas dans la barre."""
    noms = run_js_sync(loaded_map, "carto.layerNames()")

    assert len(noms) == 5
    assert any("OpenStreetMap" in nom for nom in noms)
    assert any("Satellite" in nom for nom in noms)
    assert any("IGN" in nom for nom in noms)


def test_changement_de_couche(loaded_map):
    loaded_map.set_base_layer("IGN Carte topographique")
    ok = wait_for(
        lambda: run_js_sync(
            loaded_map, 'map.hasLayer(layers["IGN Carte topographique"])'
        )
        is True,
        timeout_ms=3000,
    )
    assert ok
    assert run_js_sync(loaded_map, 'map.hasLayer(layers["Plan (OpenStreetMap)"])') is False

    loaded_map.set_base_layer("Plan (OpenStreetMap)")
    wait_for(
        lambda: run_js_sync(loaded_map, 'map.hasLayer(layers["Plan (OpenStreetMap)"])')
        is True,
        timeout_ms=3000,
    )


def test_deplacement_de_la_vue_remonte_vers_python(loaded_map):
    received = []
    loaded_map.view_changed.connect(lambda la, lo, z: received.append((la, lo, z)))

    loaded_map.set_view(45.8326, 6.8652, 12)  # Chamonix

    assert wait_for(lambda: bool(received), timeout_ms=5000)
    lat, lon, zoom = received[-1]
    assert lat == pytest.approx(45.8326, abs=1e-3)
    assert lon == pytest.approx(6.8652, abs=1e-3)
    assert zoom == 12


def test_clic_carte_remonte_vers_python(loaded_map):
    received = []
    loaded_map.map_clicked.connect(lambda la, lo: received.append((la, lo)))

    run_js_sync(
        loaded_map,
        "map.fire('click', {latlng: L.latLng(48.5, 2.25)}); true",
    )

    assert wait_for(lambda: bool(received), timeout_ms=5000)
    assert received[-1][0] == pytest.approx(48.5, abs=1e-6)
    assert received[-1][1] == pytest.approx(2.25, abs=1e-6)
