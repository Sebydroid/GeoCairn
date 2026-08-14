"""Fermeture de la fenêtre pendant le chargement de la carte."""

from __future__ import annotations

import gc

import pytest

from geocairn.app import create_app
from geocairn.database import Database
from geocairn.ui.main_window import MainWindow
from geocairn.ui.map_view import MapView
from tests.test_ui import wait_for


@pytest.fixture(scope="session")
def qapp():
    app = create_app(["geocairn-tests"])
    yield app
    app.processEvents()


def test_fermeture_avant_la_fin_du_chargement(qapp, tmp_path):
    """Régression : le processus avortait à la fin du chargement.

    La carte signale sa disponibilité de façon asynchrone. Si la fenêtre est
    fermée entre-temps, le traitement interrogeait une base déjà close ; comme
    l'exception survient dans un slot Qt, PyQt interrompt tout le programme.
    """
    database = Database(tmp_path / "geocairn.db")
    fenetre = MainWindow(db=database)
    fenetre.show()
    fenetre.close()   # avant que la carte n'ait fini de charger

    # La carte poursuit son chargement et émet son signal : cela ne doit rien
    # déclencher qui touche à la base.
    wait_for(lambda: False, timeout_ms=1500)

    assert fenetre._closing is True


def test_une_carte_survit_a_la_destruction_d_une_fenetre(qapp, tmp_path):
    database = Database(tmp_path / "geocairn.db")
    fenetre = MainWindow(db=database)
    fenetre.show()
    fenetre.close()
    del fenetre
    gc.collect()

    vue = MapView()
    vue.show()
    assert wait_for(lambda: vue.is_ready), "la carte n'a pas pu se charger"
    vue.close()


def test_les_traces_visibles_sont_rechargees_apres_fermeture(qapp, tmp_path):
    """La fermeture ne doit pas perdre la liste des traces affichées."""
    from geocairn.models import Point

    chemin = tmp_path / "geocairn.db"
    database = Database(chemin)
    track_id = database.create_track(
        "Trace", points=[Point(48.9, 1.4), Point(48.91, 1.41)]
    )
    fenetre = MainWindow(db=database)
    fenetre.show()
    assert wait_for(lambda: fenetre.map_view.is_ready)
    fenetre.show_track(track_id)
    fenetre.close()

    with Database(chemin) as relue:
        assert relue.visible_track_ids() == [track_id]
