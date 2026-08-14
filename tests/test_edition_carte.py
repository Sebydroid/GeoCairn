"""Tests d'intégration du mode saisie sur carte (Jalon 3).

Ces tests pilotent une vraie carte Leaflet chargée hors écran : ils vérifient
que Python et l'affichage restent synchronisés à chaque clic et à chaque
annulation.
"""

from __future__ import annotations

import pytest

from geocairn.app import create_app
from geocairn.database import Database
from geocairn.ui.main_window import MainWindow
from tests.test_ui import run_js_sync, wait_for


@pytest.fixture(scope="session")
def qapp():
    app = create_app(["geocairn-tests"])
    yield app
    app.processEvents()


@pytest.fixture(scope="session")
def window(qapp, tmp_path_factory):
    """Fenêtre complète avec carte réellement chargée (partagée : coûteux)."""
    database = Database(tmp_path_factory.mktemp("edition") / "geocairn.db")
    win = MainWindow(db=database)
    win.show()
    assert wait_for(lambda: win.map_view.is_ready), "carte non chargée"
    yield win
    win.close()


@pytest.fixture(autouse=True)
def draft_vierge(window):
    """Chaque test démarre avec un brouillon vide et le mode saisie coupé."""
    window.set_edit_mode(False)
    window.clear_draft(confirm=False)
    assert sync_js_draft_count(window) == 0
    yield
    window.set_edit_mode(False)
    window.clear_draft(confirm=False)


# ------------------------------------------------------------------ outillage


def sync_js_draft_count(window) -> int:
    return run_js_sync(window.map_view, "geocairn.draftCount()")


def fire_map_click(window, lat: float, lon: float) -> None:
    """Simule un clic gauche sur la carte, comme le ferait l'utilisateur."""
    run_js_sync(
        window.map_view,
        f"map.fire('click', {{latlng: L.latLng({lat}, {lon})}}); true",
    )


def click_and_wait(window, lat: float, lon: float) -> None:
    """Clique et attend que le point soit enregistré côté Python."""
    before = len(window.draft)
    fire_map_click(window, lat, lon)
    assert wait_for(lambda: len(window.draft) == before + 1, timeout_ms=5000), (
        "le clic n'a pas ajouté de point au brouillon"
    )


# --------------------------------------------------------------- mode saisie


def test_mode_saisie_desactive_par_defaut(window):
    assert window.edit_mode is False
    assert run_js_sync(window.map_view, "geocairn.isEditMode()") is False


def test_bouton_creer_une_trace_active_le_mode_saisie(window):
    window.action_create.setChecked(True)

    assert window.edit_mode is True
    assert wait_for(
        lambda: run_js_sync(window.map_view, "geocairn.isEditMode()") is True,
        timeout_ms=3000,
    )
    assert "cliquez sur la carte" in window.status_label.text().lower()


def test_curseur_en_croix_en_mode_saisie(window):
    window.set_edit_mode(True)
    assert wait_for(
        lambda: run_js_sync(
            window.map_view,
            "map.getContainer().classList.contains('mode-edition')",
        )
        is True,
        timeout_ms=3000,
    )

    window.set_edit_mode(False)
    assert wait_for(
        lambda: run_js_sync(
            window.map_view,
            "map.getContainer().classList.contains('mode-edition')",
        )
        is False,
        timeout_ms=3000,
    )


def test_clic_hors_mode_saisie_n_ajoute_aucun_point(window):
    fire_map_click(window, 48.93, 1.44)

    # Laisse le temps à un éventuel ajout de se produire.
    wait_for(lambda: len(window.draft) > 0, timeout_ms=1500)

    assert len(window.draft) == 0
    assert sync_js_draft_count(window) == 0


# --------------------------------------------------------- création de trace


def test_chaque_clic_ajoute_un_point(window):
    window.set_edit_mode(True)

    click_and_wait(window, 48.930, 1.440)
    click_and_wait(window, 48.931, 1.442)
    click_and_wait(window, 48.932, 1.441)

    assert len(window.draft) == 3
    assert [p.as_tuple() for p in window.draft.points] == [
        (48.930, 1.440),
        (48.931, 1.442),
        (48.932, 1.441),
    ]


def test_la_polyligne_suit_les_points_saisis(window):
    window.set_edit_mode(True)
    click_and_wait(window, 48.930, 1.440)
    click_and_wait(window, 48.931, 1.442)

    assert wait_for(lambda: sync_js_draft_count(window) == 2, timeout_ms=3000)
    coords = run_js_sync(window.map_view, "draft.line.getLatLngs().map(function(p){return [p.lat, p.lng];})")
    assert coords == [[48.930, 1.440], [48.931, 1.442]]

    # Un repère est dessiné pour chaque point saisi.
    assert run_js_sync(window.map_view, "draft.vertices.getLayers().length") == 2


def test_longueur_affichee_dans_la_barre_d_etat(window):
    window.set_edit_mode(True)
    click_and_wait(window, 45.0, 3.0)
    click_and_wait(window, 46.0, 3.0)

    assert window.draft.length_m == pytest.approx(111_195, rel=0.001)
    assert window.draft_label.text().startswith("Brouillon : 2 points — 111,")


# ------------------------------------------------------------- annulation Z


def test_annulation_retire_le_point_des_deux_cotes(window):
    window.set_edit_mode(True)
    click_and_wait(window, 48.930, 1.440)
    click_and_wait(window, 48.931, 1.442)

    window.undo_last_point()

    assert len(window.draft) == 1
    assert wait_for(lambda: sync_js_draft_count(window) == 1, timeout_ms=3000)
    assert run_js_sync(window.map_view, "draft.vertices.getLayers().length") == 1


def test_ctrl_z_depuis_la_carte(window):
    """Le raccourci doit fonctionner même quand la carte a le focus clavier."""
    window.set_edit_mode(True)
    click_and_wait(window, 48.930, 1.440)
    click_and_wait(window, 48.931, 1.442)

    run_js_sync(
        window.map_view,
        "document.dispatchEvent(new KeyboardEvent('keydown',"
        " {key: 'z', ctrlKey: true, bubbles: true})); true",
    )

    assert wait_for(lambda: len(window.draft) == 1, timeout_ms=5000)
    assert wait_for(lambda: sync_js_draft_count(window) == 1, timeout_ms=3000)


def test_annulation_sur_brouillon_vide_ne_casse_rien(window):
    window.undo_last_point()

    assert len(window.draft) == 0
    assert window.status_label.text() == "Aucun point à annuler."


def test_annulation_puis_nouveau_point(window):
    window.set_edit_mode(True)
    click_and_wait(window, 48.930, 1.440)
    click_and_wait(window, 48.931, 1.442)
    window.undo_last_point()
    assert wait_for(lambda: sync_js_draft_count(window) == 1, timeout_ms=3000)

    click_and_wait(window, 48.935, 1.450)

    assert [p.as_tuple() for p in window.draft.points] == [
        (48.930, 1.440),
        (48.935, 1.450),
    ]
    assert wait_for(lambda: sync_js_draft_count(window) == 2, timeout_ms=3000)


# ------------------------------------------------------- brouillon en mémoire


def test_le_brouillon_survit_a_la_sortie_du_mode_saisie(window):
    """Le plan exige le maintien de la trace brouillon en mémoire."""
    window.set_edit_mode(True)
    click_and_wait(window, 48.930, 1.440)
    click_and_wait(window, 48.931, 1.442)

    window.set_edit_mode(False)

    assert len(window.draft) == 2
    assert sync_js_draft_count(window) == 2

    window.set_edit_mode(True)
    click_and_wait(window, 48.932, 1.443)
    assert len(window.draft) == 3


def test_effacement_du_brouillon(window):
    window.set_edit_mode(True)
    click_and_wait(window, 48.930, 1.440)
    click_and_wait(window, 48.931, 1.442)

    window.clear_draft(confirm=False)

    assert window.draft.is_empty
    assert wait_for(lambda: sync_js_draft_count(window) == 0, timeout_ms=3000)
    assert run_js_sync(window.map_view, "draft.line.getLatLngs()") == []


def test_actions_grisees_quand_le_brouillon_est_vide(window):
    assert window.action_undo.isEnabled() is False
    assert window.action_clear.isEnabled() is False

    window.set_edit_mode(True)
    click_and_wait(window, 48.930, 1.440)

    assert window.action_undo.isEnabled() is True
    assert window.action_clear.isEnabled() is True

    window.undo_last_point()

    assert window.action_undo.isEnabled() is False
    assert window.action_clear.isEnabled() is False
