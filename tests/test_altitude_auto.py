"""Altitude récupérée au fil de la saisie, et robustesse aux pannes réseau."""

from __future__ import annotations

import json
import urllib.parse

import pytest
from PyQt6.QtWidgets import QMessageBox

from geocairn.app import create_app
from geocairn.database import Database
from geocairn.models import Point
from geocairn.ui.elevation_fetcher import ECHECS_AVANT_VEILLE, ElevationFetcher
from geocairn.ui.main_window import MainWindow
from tests.test_ui import wait_for


@pytest.fixture(scope="session")
def qapp():
    app = create_app(["geocairn-tests"])
    yield app
    app.processEvents()


def reponse(valeurs):
    """Faux service renvoyant les altitudes données, dans l'ordre des demandes.

    Le nombre d'altitudes doit correspondre au nombre de points demandés : le
    service réel est interrogé point par point pendant la saisie.
    """
    restant = list(valeurs)

    def fetch(url):
        attendus = len(urllib.parse.parse_qs(
            urllib.parse.urlparse(url).query
        )["lon"][0].split("|"))
        lot = [restant.pop(0) if restant else 0.0 for _ in range(attendus)]
        return json.dumps({"elevations": lot}).encode()

    return fetch


def panne(message="réseau coupé"):
    def fetch(_url):
        raise OSError(message)
    return fetch


# --------------------------------------------------- récupérateur seul


def test_altitude_recuperee_en_arriere_plan(qapp):
    fetcher = ElevationFetcher(fetch=reponse([63.2]))
    recus = []
    fetcher.resolved.connect(recus.append)

    assert fetcher.request([(0, 48.93, 1.44)]) is True
    assert wait_for(lambda: bool(recus), timeout_ms=5000)

    assert recus[0] == [(0, 48.93, 1.44, 63.2)]


def test_plusieurs_points_en_une_fois(qapp):
    fetcher = ElevationFetcher(fetch=reponse([10.0, 20.0]))
    recus = []
    fetcher.resolved.connect(recus.append)

    fetcher.request([(0, 48.9, 1.4), (1, 48.91, 1.41)])
    assert wait_for(lambda: bool(recus), timeout_ms=5000)

    assert [r[3] for r in recus[0]] == [10.0, 20.0]


def test_absence_de_reseau_signalee_sans_exception(qapp):
    """Une coupure ne doit jamais remonter jusqu'à interrompre l'application."""
    fetcher = ElevationFetcher(fetch=panne())
    echecs = []
    fetcher.failed.connect(echecs.append)

    fetcher.request([(0, 48.93, 1.44)])

    assert wait_for(lambda: bool(echecs), timeout_ms=5000)
    assert "injoignable" in echecs[0]


def test_reponse_incoherente_signalee(qapp):
    def fetch(_url):
        return b"ceci n'est pas du json"

    fetcher = ElevationFetcher(fetch=fetch)
    echecs = []
    fetcher.failed.connect(echecs.append)

    fetcher.request([(0, 48.93, 1.44)])

    assert wait_for(lambda: bool(echecs), timeout_ms=5000)


def test_mise_en_veille_apres_plusieurs_echecs(qapp):
    """Inutile de harceler un service absent à chaque point posé."""
    fetcher = ElevationFetcher(fetch=panne())
    veilles = []
    fetcher.suspended.connect(veilles.append)

    for _ in range(ECHECS_AVANT_VEILLE):
        fetcher.request([(0, 48.93, 1.44)])
        fetcher.wait(5000)
        qapp.processEvents()

    assert wait_for(lambda: bool(veilles), timeout_ms=5000)
    assert fetcher.enabled is False
    assert fetcher.request([(1, 48.93, 1.44)]) is False


def test_reveil_apres_veille(qapp):
    fetcher = ElevationFetcher(fetch=panne())
    fetcher.enabled = False

    fetcher.reset()

    assert fetcher.enabled is True
    assert fetcher.echecs == 0


def test_un_succes_remet_le_compteur_a_zero(qapp):
    fetcher = ElevationFetcher(fetch=panne())
    fetcher.request([(0, 48.9, 1.4)])
    fetcher.wait(5000)
    qapp.processEvents()
    assert fetcher.echecs == 1

    fetcher._fetch = reponse([63.2])
    recus = []
    fetcher.resolved.connect(recus.append)
    fetcher.request([(0, 48.9, 1.4)])

    assert wait_for(lambda: bool(recus), timeout_ms=5000)
    assert fetcher.echecs == 0


def test_le_resultat_survit_au_ramasse_miettes(qapp):
    """Le porte-signaux ne doit pas disparaître avant la remise du résultat.

    Qt détruit le QRunnable dès la fin de son exécution ; si l'objet Python
    partait avec lui, l'altitude calculée n'arriverait jamais jusqu'à la
    fenêtre, sans le moindre message.
    """
    import gc

    fetcher = ElevationFetcher(fetch=reponse([63.2]))
    recus = []
    fetcher.resolved.connect(recus.append)

    fetcher.request([(0, 48.93, 1.44)])
    fetcher.wait(5000)      # le travail de fond est terminé…
    gc.collect()            # …et rien ne doit avoir été libéré entre-temps

    assert wait_for(lambda: bool(recus), timeout_ms=5000)
    assert recus[0] == [(0, 48.93, 1.44, 63.2)]


def test_les_requetes_terminees_sont_oubliees(qapp):
    """La mémoire ne doit pas enfler d'une requête à l'autre."""
    fetcher = ElevationFetcher(fetch=reponse([63.2, 64.0, 65.0]))
    recus = []
    fetcher.resolved.connect(recus.append)

    for i in range(3):
        fetcher.request([(i, 48.93, 1.44)])

    assert wait_for(lambda: len(recus) == 3, timeout_ms=5000)
    assert wait_for(lambda: not fetcher._en_vol, timeout_ms=5000)


# ------------------------------------------------ intégration fenêtre


@pytest.fixture
def window(qapp, tmp_path, monkeypatch):
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: None))
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: None))
    database = Database(tmp_path / "geocairn.db")
    win = MainWindow(db=database)
    yield win
    win.close()


def test_un_point_dessine_recoit_son_altitude(window):
    window.elevation_fetcher._fetch = reponse([63.2])
    window.set_edit_mode(True)

    window.add_draft_point(48.93, 1.44)

    assert wait_for(
        lambda: window.draft.points[0].ele_service is not None, timeout_ms=5000
    )
    assert window.draft.points[0].ele_service == pytest.approx(63.2)


def test_le_deplacement_met_l_altitude_a_jour(window):
    window.elevation_fetcher._fetch = reponse([63.2])
    window.set_edit_mode(True)
    window.add_draft_point(48.93, 1.44)
    assert wait_for(
        lambda: window.draft.points[0].ele_service is not None, timeout_ms=5000
    )

    window.elevation_fetcher._fetch = reponse([128.0])
    window.move_draft_point(0, 45.83, 6.86)

    assert wait_for(
        lambda: window.draft.points[0].ele_service == pytest.approx(128.0),
        timeout_ms=5000,
    )


def test_l_altitude_perimee_est_effacee_pendant_l_attente(window):
    window.elevation_fetcher._fetch = reponse([63.2])
    window.set_edit_mode(True)
    window.add_draft_point(48.93, 1.44)
    wait_for(lambda: window.draft.points[0].ele_service is not None, timeout_ms=5000)

    # Sans réseau, l'ancienne altitude ne doit pas rester attachée au nouveau
    # point : elle ne vaut plus rien là-bas.
    window.elevation_fetcher._fetch = panne()
    window.move_draft_point(0, 45.83, 6.86)

    assert window.draft.points[0].ele_service is None


def test_une_panne_n_interrompt_pas_le_dessin(window):
    """Sans connexion, on doit pouvoir continuer à dessiner normalement."""
    window.elevation_fetcher._fetch = panne()
    window.set_edit_mode(True)

    for lat, lon in [(48.930, 1.440), (48.931, 1.442), (48.932, 1.441)]:
        window.add_draft_point(lat, lon)
    window.elevation_fetcher.wait(5000)
    qapp = window.map_view.parent()
    del qapp

    assert len(window.draft) == 3
    assert all(p.ele_service is None for p in window.draft.points)


def test_altitude_ignoree_si_le_point_a_bouge(window):
    """La réponse arrive après coup : elle ne doit pas s'appliquer à tort."""
    window.set_edit_mode(True)
    window.add_draft_point(48.93, 1.44)

    # Réponse pour un point qui n'est plus là où il était.
    window._on_elevations_resolved([(0, 48.99, 1.99, 500.0)])

    assert window.draft.points[0].ele_service is None


def test_altitude_ignoree_si_le_point_a_disparu(window):
    window.set_edit_mode(True)
    window.add_draft_point(48.93, 1.44)
    window.draft.clear()

    window._on_elevations_resolved([(0, 48.93, 1.44, 63.2)])   # ne doit rien lever

    assert window.draft.is_empty


def test_le_profil_se_remplit_avec_l_altitude_recue(window):
    from geocairn.ui.profile_panel import SOURCE_ELE_SERVICE

    window.elevation_fetcher._fetch = reponse([63.2, 68.0, 74.0])
    window.set_edit_mode(True)
    for lat, lon in [(48.930, 1.440), (48.931, 1.442), (48.932, 1.441)]:
        window.add_draft_point(lat, lon)

    assert wait_for(
        lambda: all(p.ele_service is not None for p in window.draft.points),
        timeout_ms=8000,
    )

    window.profile_panel.set_source(SOURCE_ELE_SERVICE)
    assert window.profile_panel.view.has_data is True


def test_l_altitude_recue_est_enregistree_avec_la_trace(window):
    window.elevation_fetcher._fetch = reponse([63.2, 68.0])
    window.set_edit_mode(True)
    window.add_draft_point(48.930, 1.440)
    window.add_draft_point(48.931, 1.442)
    assert wait_for(
        lambda: all(p.ele_service is not None for p in window.draft.points),
        timeout_ms=8000,
    )

    track_id = window.save_draft("Dessinée")

    points = window.db.get_points(track_id)
    assert [p.ele_service for p in points] == [pytest.approx(63.2), pytest.approx(68.0)]
