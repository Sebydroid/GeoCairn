"""Import de GPX dans l'application et affichage sur la carte (Jalon 5)."""

from __future__ import annotations

from pathlib import Path

import pytest
from PyQt6.QtWidgets import QMessageBox

from carto.app import create_app
from carto.gpx import write_gpx
from carto.models import DEFAULT_TRACK_COLOR, Point
from carto.ui.main_window import MainWindow
from carto.ui.tree_panel import KIND_TRACK
from tests.test_ui import run_js_sync, wait_for

EXEMPLES = Path(__file__).resolve().parent.parent / "GPX exemples"


@pytest.fixture(scope="session")
def qapp():
    app = create_app(["carto-tests"])
    yield app
    app.processEvents()


@pytest.fixture(scope="session")
def window(qapp, tmp_path_factory):
    """Fenêtre complète avec carte réellement chargée (partagée : coûteux)."""
    from carto.database import Database

    database = Database(tmp_path_factory.mktemp("import") / "carto.db")
    win = MainWindow(db=database)
    win.show()
    assert wait_for(lambda: win.map_view.is_ready), "carte non chargée"
    yield win
    win.close()


@pytest.fixture(autouse=True)
def base_vierge(window):
    """Chaque test démarre sur une bibliothèque vide et une carte nette."""
    for track in window.db.list_tracks(None):
        window.db.delete_track(track.id)
    for folder in window.db.list_folders(None):
        window.db.delete_folder(folder.id)
    window.displayed_track_id = None
    window.map_view.clear_track()
    window.tree_panel.refresh()
    yield


@pytest.fixture
def silence_dialogs(monkeypatch):
    shown: list[tuple[str, str]] = []

    def handler(_parent, title, text, *args, **kwargs):
        shown.append((title, text))
        return QMessageBox.StandardButton.Yes

    for name in ("warning", "information", "critical", "question"):
        monkeypatch.setattr(QMessageBox, name, staticmethod(handler))
    return shown


def fichier_gpx(tmp_path: Path, nom: str, points: list[Point]) -> str:
    return str(write_gpx(tmp_path / f"{nom}.gpx", nom, points))


TROIS_POINTS = [Point(48.930, 1.440, 70.0), Point(48.931, 1.442), Point(48.932, 1.441)]


# ------------------------------------------------------------------ import


def test_import_d_un_fichier(window, tmp_path):
    chemin = fichier_gpx(tmp_path, "Rallye V1", TROIS_POINTS)

    created = window.import_gpx([chemin])

    assert len(created) == 1
    track = window.db.get_track(created[0], with_points=True)
    assert track.name == "Rallye V1"
    assert len(track.points) == 3
    assert track.points[0].ele == pytest.approx(70.0)


def test_trace_importee_apparait_dans_l_arborescence(window, tmp_path):
    chemin = fichier_gpx(tmp_path, "Boucle", TROIS_POINTS)

    created = window.import_gpx([chemin])

    root = window.tree_panel.tree.topLevelItem(0)
    labels = [root.child(i).text(0) for i in range(root.childCount())]
    assert labels == ["Boucle  (3 pts)"]
    assert window.tree_panel.current_selection() == (KIND_TRACK, created[0])


def test_import_dans_le_dossier_selectionne(window, tmp_path):
    folder_id = window.tree_panel.create_folder("Rallyes")
    chemin = fichier_gpx(tmp_path, "Trace", TROIS_POINTS)

    created = window.import_gpx([chemin])

    assert window.db.get_track(created[0]).folder_id == folder_id


def test_import_de_plusieurs_fichiers(window, tmp_path):
    chemins = [
        fichier_gpx(tmp_path, "Aller", TROIS_POINTS),
        fichier_gpx(tmp_path, "Retour", TROIS_POINTS),
    ]

    created = window.import_gpx(chemins)

    assert len(created) == 2
    assert sorted(t.name for t in window.db.list_tracks(None)) == ["Aller", "Retour"]


def test_fichier_illisible_signale_sans_bloquer_les_autres(
    window, tmp_path, silence_dialogs
):
    casse = tmp_path / "casse.gpx"
    casse.write_text("<gpx><trk>pas fermé", encoding="utf-8")
    bon = fichier_gpx(tmp_path, "Bonne trace", TROIS_POINTS)

    created = window.import_gpx([str(casse), bon])

    assert len(created) == 1
    assert window.db.get_track(created[0]).name == "Bonne trace"
    assert any("casse.gpx" in text for _titre, text in silence_dialogs)


def test_fichier_de_points_d_interet_explique(window, tmp_path, silence_dialogs):
    """Un fichier de <wpt> seuls doit dire pourquoi rien n'est importé."""
    chemin = tmp_path / "reperes.gpx"
    chemin.write_text(
        '<?xml version="1.0"?><gpx version="1.1" '
        'xmlns="http://www.topografix.com/GPX/1/1">'
        '<wpt lat="48.5" lon="1.5"><name>Belvédère</name></wpt>'
        '<wpt lat="48.6" lon="1.6"><name>Apiculteur</name></wpt></gpx>',
        encoding="utf-8",
    )

    assert window.import_gpx([str(chemin)]) == []
    assert any(
        "2 points d'intérêt" in text for _titre, text in silence_dialogs
    )


@pytest.mark.skipif(not EXEMPLES.is_dir(), reason="dossier d'exemples absent")
def test_import_des_parcours_reels(window):
    """Import des vrais fichiers fournis avec le projet."""
    fichiers = [str(f) for f in sorted(EXEMPLES.glob("Parcours*.gpx"))]

    created = window.import_gpx(fichiers)

    assert len(created) == len(fichiers)
    for track_id in created:
        assert window.db.get_track(track_id).point_count > 10


# --------------------------------------------------------------- affichage


def test_double_clic_affiche_la_trace_sur_la_carte(window, tmp_path):
    created = window.import_gpx([fichier_gpx(tmp_path, "Trace", TROIS_POINTS)])
    window.map_view.clear_track()

    assert window.display_track(created[0]) is True

    assert wait_for(
        lambda: run_js_sync(window.map_view, "carto.shownCount()") == 3,
        timeout_ms=5000,
    )
    coords = run_js_sync(
        window.map_view,
        "shown.line.getLatLngs().map(function(p){return [p.lat, p.lng];})",
    )
    assert coords == [[48.930, 1.440], [48.931, 1.442], [48.932, 1.441]]


def test_reperes_de_depart_et_d_arrivee(window, tmp_path):
    created = window.import_gpx([fichier_gpx(tmp_path, "Trace", TROIS_POINTS)])
    window.display_track(created[0])

    assert wait_for(
        lambda: run_js_sync(window.map_view, "shown.ends.getLayers().length") == 2,
        timeout_ms=5000,
    )


def test_la_carte_se_recadre_sur_la_trace(window, tmp_path):
    """Le plan demande un zoom automatique au double-clic."""
    loin = [Point(45.8326, 6.8652), Point(45.8400, 6.8700), Point(45.8500, 6.8800)]
    created = window.import_gpx([fichier_gpx(tmp_path, "Chamonix", loin)])
    window.map_view.set_view(48.93, 1.44, 13)
    wait_for(lambda: False, timeout_ms=300)

    window.display_track(created[0])

    assert wait_for(
        lambda: run_js_sync(window.map_view, "map.getCenter().lat") > 45.0
        and run_js_sync(window.map_view, "map.getCenter().lat") < 46.0,
        timeout_ms=5000,
    )


def test_double_clic_dans_l_arborescence_declenche_l_affichage(window, tmp_path):
    created = window.import_gpx([fichier_gpx(tmp_path, "Trace", TROIS_POINTS)])
    window.displayed_track_id = None

    item = window.tree_panel.find_item(KIND_TRACK, created[0])
    window.tree_panel._on_double_click(item, 0)

    assert window.displayed_track_id == created[0]


def test_affichage_d_une_autre_trace_remplace_la_precedente(window, tmp_path):
    a = window.import_gpx([fichier_gpx(tmp_path, "Courte", TROIS_POINTS)])[0]
    b = window.import_gpx(
        [fichier_gpx(tmp_path, "Longue", TROIS_POINTS + [Point(48.933, 1.445)])]
    )[0]

    window.display_track(a)
    assert wait_for(
        lambda: run_js_sync(window.map_view, "carto.shownCount()") == 3,
        timeout_ms=5000,
    )

    window.display_track(b)
    assert wait_for(
        lambda: run_js_sync(window.map_view, "carto.shownCount()") == 4,
        timeout_ms=5000,
    )


def test_longueur_affichee_dans_la_barre_d_etat(window, tmp_path):
    points = [Point(45.0, 3.0), Point(46.0, 3.0)]
    created = window.import_gpx([fichier_gpx(tmp_path, "Un degré", points)])

    window.display_track(created[0])

    texte = window.status_label.text()
    assert "Un degré" in texte
    assert "2 points" in texte
    assert "111," in texte  # ~111,2 km


def test_trace_sans_point_refusee(window):
    track_id = window.db.create_track("Vide", points=[])

    assert window.display_track(track_id) is False
    assert "aucun point" in window.status_label.text()


def test_la_trace_affichee_et_le_brouillon_coexistent(window, tmp_path):
    """Consulter une trace enregistrée ne doit pas effacer la saisie en cours."""
    created = window.import_gpx([fichier_gpx(tmp_path, "Trace", TROIS_POINTS)])
    window.set_edit_mode(True)
    window.add_draft_point(48.95, 1.46)
    window.add_draft_point(48.96, 1.47)

    window.display_track(created[0])

    assert len(window.draft) == 2
    assert wait_for(
        lambda: run_js_sync(window.map_view, "carto.draftCount()") == 2,
        timeout_ms=5000,
    )
    assert run_js_sync(window.map_view, "carto.shownCount()") == 3

    # Les deux tracés doivent rester distinguables à l'œil.
    couleur_trace = run_js_sync(window.map_view, "shown.line.options.color")
    couleur_brouillon = run_js_sync(window.map_view, "draft.line.options.color")
    assert couleur_trace == DEFAULT_TRACK_COLOR
    assert couleur_trace != couleur_brouillon

    window.set_edit_mode(False)
    window.clear_draft(confirm=False)
