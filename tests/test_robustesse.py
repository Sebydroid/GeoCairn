"""Tests de régression sur les pannes repérées à la relecture du code.

Chaque test reproduit une situation qui, avant correction, laissait l'outil dans
un état incohérent — voire interrompait le programme au beau milieu d'un signal
Qt, ce qui, sous PyQt, fait tomber toute l'application.
"""

from __future__ import annotations

import math
import os
import sqlite3
import stat
import time
from pathlib import Path

import pytest
from PyQt6.QtWidgets import QMessageBox

from carto.app import create_app
from carto.database import Database
from carto.geo import distance, total_length
from carto.gpx import ELE_AUTO, coordonnee_valide, parse_gpx, safe_filename
from carto.models import Point
from carto.ui.icons import BULB_OFF, BULB_ON, bulb_with
from carto.ui.main_window import MainWindow
from carto.ui.toolbar_icons import toolbar_icon
from carto.ui.tree_panel import KIND_FOLDER

DEUX = [Point(48.930, 1.440), Point(48.931, 1.442)]
TROIS = DEUX + [Point(48.932, 1.441)]
QUATRE = TROIS + [Point(48.933, 1.439)]


@pytest.fixture(scope="session")
def qapp():
    app = create_app(["carto-tests"])
    yield app
    app.processEvents()


@pytest.fixture(scope="module")
def _fenetre(qapp, tmp_path_factory):
    """Fenêtre partagée par tout le fichier.

    Chaque fenêtre embarque un moteur web complet : en construire une par test
    épuise les ressources de QtWebEngine, et la suite entière finit par mourir
    plusieurs fichiers plus loin, sans le moindre rapport avec le test fautif.
    """
    database = Database(tmp_path_factory.mktemp("robustesse") / "carto.db")
    win = MainWindow(db=database)
    yield win
    # Fermer pour de bon : une fenêtre laissée vivante retient le moteur web,
    # et l'interpréteur ne rend jamais la main.
    win.close()


@pytest.fixture
def window(_fenetre, monkeypatch):
    """Bibliothèque vide, brouillon vide, dialogues neutralisés."""
    monkeypatch.setattr(
        QMessageBox, "question",
        staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes),
    )
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: None))
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: None))
    monkeypatch.setattr(QMessageBox, "critical", staticmethod(lambda *a, **k: None))

    for track in _fenetre.db.list_tracks(None):
        _fenetre.db.delete_track(track.id)
    for folder in _fenetre.db.list_folders(None):
        _fenetre.db.delete_folder(folder.id)
    _fenetre.draft.reset()
    _fenetre.set_edit_mode(False)
    _fenetre.map_view.clear_draft()
    _fenetre.map_view.clear_tracks()
    _fenetre.visible_tracks.clear()
    _fenetre.tree_panel.refresh()
    _fenetre._update_draft_actions()
    yield _fenetre


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


# ------------------------------------------- coordonnées aberrantes


TETE_GPX = (
    '<gpx version="1.1" xmlns="http://www.topografix.com/GPX/1/1">'
    "<trk><name>Poison</name><trkseg>"
)
PIED_GPX = "</trkseg></trk></gpx>"


def gpx_avec(tmp_path, points_xml: str, nom: str = "poison.gpx"):
    chemin = tmp_path / nom
    chemin.write_text(TETE_GPX + points_xml + PIED_GPX, encoding="utf-8")
    return chemin


@pytest.mark.parametrize(
    "valeur", ["NaN", "nan", "1e999", "-1e999", "195.0", "-91.5"]
)
def test_les_coordonnees_aberrantes_sont_ecartees(tmp_path, valeur):
    """« NaN » empêchait l'enregistrement, « 1e999 » le calcul de distance."""
    chemin = gpx_avec(
        tmp_path,
        f'<trkpt lat="{valeur}" lon="1.4"/>'
        '<trkpt lat="48.930" lon="1.440"/>'
        '<trkpt lat="48.931" lon="1.442"/>',
    )

    trace = parse_gpx(chemin)[0]

    assert len(trace.points) == 2
    assert trace.ignores == 1


def test_les_coordonnees_valides_passent(tmp_path):
    chemin = gpx_avec(
        tmp_path,
        '<trkpt lat="48.930" lon="1.440"/><trkpt lat="-89.9" lon="179.9"/>',
    )

    trace = parse_gpx(chemin)[0]

    assert len(trace.points) == 2
    assert trace.ignores == 0


def test_coordonnee_valide():
    assert coordonnee_valide(48.93, 1.44) is True
    assert coordonnee_valide(90.0, -180.0) is True
    assert coordonnee_valide(float("nan"), 1.44) is False
    assert coordonnee_valide(float("inf"), 1.44) is False
    assert coordonnee_valide(90.1, 1.44) is False
    assert coordonnee_valide(48.93, 180.1) is False


def test_importer_un_gpx_aberrant_ne_fait_pas_tomber_l_application(
    window, tmp_path
):
    """Régression : l'import d'une coordonnée infinie avortait le programme."""
    chemin = gpx_avec(
        tmp_path,
        '<trkpt lat="1e999" lon="1.4"/>'
        '<trkpt lat="48.930" lon="1.440"/>'
        '<trkpt lat="48.931" lon="1.442"/>',
    )

    crees = window.import_gpx([str(chemin)])

    assert len(crees) == 1
    assert window.db.get_track(crees[0]).point_count == 2


def test_une_base_deja_empoisonnee_reste_affichable(window):
    """Une trace importée par une version antérieure ne doit rien casser."""
    track_id = window.db.create_track("Ancienne", points=DEUX)
    with window.db.conn:
        window.db.conn.execute(
            "UPDATE points SET lat = 9e999 WHERE track_id = ? AND seq = 0",
            (track_id,),
        )
    window.tree_panel.refresh()

    # Aucune de ces opérations ne doit lever : elles ont toutes lieu dans des
    # signaux Qt, où la moindre exception emporte l'application.
    assert window.show_track(track_id) is True
    window.profile_panel.set_points(
        window.db.get_points(track_id), "Ancienne"
    )
    window.profile_panel.summary()


@pytest.mark.parametrize(
    "coords",
    [
        ((float("inf"), 1.4), (48.9, 1.41)),
        ((float("nan"), 1.4), (48.9, 1.41)),
        ((195.0, 999.4), (48.9, 1.41)),
        ((91.0, 0.0), (-91.0, 180.0)),
    ],
)
def test_la_distance_ne_leve_jamais(coords):
    a, b = coords
    valeur = distance(Point(*a), Point(*b))
    assert valeur >= 0.0
    assert total_length([Point(*a), Point(*b)]) >= 0.0


# ------------------------------------------------- traces très denses


def trace_dense(n: int = 20000) -> list[Point]:
    """Un enregistrement GPS d'une journée, à un point par seconde."""
    points = []
    lat, lon = 48.90, 1.40
    for i in range(n):
        lat += 2e-5 * math.sin(i / 97.0)
        lon += 2e-5 * math.cos(i / 89.0)
        points.append(Point(lat, lon, 100 + 20 * math.sin(i / 300.0)))
    return points


def test_deplacer_un_point_reste_immediat_sur_une_trace_dense(window):
    """Régression : la liste des points était reconstruite ligne à ligne.

    Sur vingt mille points, déplacer un seul repère figeait l'interface plus de
    deux secondes. Le seuil est large à dessein : il n'est pas là pour mesurer
    la machine, mais pour signaler le retour d'un ajout ligne par ligne.
    """
    track_id = window.db.create_track("Dense", points=trace_dense())
    window.tree_panel.refresh()
    window.resume_track(track_id)

    debut = time.perf_counter()
    assert window.move_draft_point(10, 48.95, 1.45) is True
    ecoule = time.perf_counter() - debut

    assert ecoule < 1.2, f"déplacement d'un point : {ecoule:.2f} s"


def test_la_liste_des_points_reste_complete_et_ordonnee(window):
    """Le remplissage groupé doit donner exactement les mêmes lignes."""
    points = trace_dense(50)
    window.points_panel.show_points(points, "Dense")

    assert window.points_panel.list.count() == 50
    premiere = window.points_panel.list.item(0).text()
    derniere = window.points_panel.list.item(49).text()
    assert premiere.split()[0] == "1"
    assert derniere.split()[0] == "50"
    assert f"{points[0].lat:.5f}" in premiere
    assert f"{points[49].lat:.5f}" in derniere


# --------------------------------------- bibliothèque bien remplie


def test_afficher_un_dossier_ne_redessine_les_ampoules_qu_une_fois(
    window, monkeypatch
):
    """Régression : redessiner l'arbre à chaque trace coûtait son carré.

    « Afficher tout » sur trois cents traces figeait l'interface près de quatre
    secondes, pour un travail utile de quelques centièmes.
    """
    dossier = window.db.create_folder("Alpes")
    for i in range(20):
        window.db.create_track(f"Trace {i}", folder_id=dossier, points=DEUX)
    window.tree_panel.refresh()

    appels = []
    vraie = window.tree_panel.refresh_bulbs
    monkeypatch.setattr(
        window.tree_panel,
        "refresh_bulbs",
        lambda: (appels.append(None), vraie()) and None,
    )

    assert window.show_items(KIND_FOLDER, dossier) == 20

    assert len(appels) <= 2, f"{len(appels)} redessins pour 20 traces"
    item = window.tree_panel.find_item(KIND_FOLDER, dossier)
    assert window.tree_panel.folder_state(item) == BULB_ON


def test_masquer_un_dossier_laisse_les_ampoules_justes(window):
    dossier = window.db.create_folder("Alpes")
    for i in range(5):
        window.db.create_track(f"Trace {i}", folder_id=dossier, points=DEUX)
    window.tree_panel.refresh()
    window.show_items(KIND_FOLDER, dossier)

    assert window.hide_items(KIND_FOLDER, dossier) == 5

    item = window.tree_panel.find_item(KIND_FOLDER, dossier)
    assert window.tree_panel.folder_state(item) == BULB_OFF
    assert window.visible_tracks == set()


# ------------------------------------------------- fidélité de l'export


def test_l_altitude_ign_survit_a_l_export(window, tmp_path):
    """Régression : une trace dessinée ressortait sans la moindre altitude.

    Le calcul d'altitude est une fonction affichée du logiciel ; l'export
    l'oubliait en chemin, parce que seule l'altitude venue du fichier d'origine
    était écrite.
    """
    track_id = window.db.create_track("Dessinée", points=TROIS)
    window.db.set_service_elevations(track_id, [70.0, 72.5, 75.0])
    window.tree_panel.refresh()

    chemin = window.export_track(track_id, path=str(tmp_path / "sortie.gpx"))

    relue = parse_gpx(chemin)[0]
    assert [p.ele for p in relue.points] == [70.0, 72.5, 75.0]


def test_l_altitude_du_fichier_reste_prioritaire(window, tmp_path):
    """Sans choix explicite, celle du fichier d'origine fait foi."""
    points = [Point(48.930, 1.440, 10.0), Point(48.931, 1.442, 20.0)]
    track_id = window.db.create_track("Importée", points=points)
    window.db.set_service_elevations(track_id, [999.0, 999.0])
    window.tree_panel.refresh()

    chemin = window.export_track(
        track_id, path=str(tmp_path / "sortie.gpx"), elevation=ELE_AUTO
    )

    relue = parse_gpx(chemin)[0]
    assert [p.ele for p in relue.points] == [10.0, 20.0]


def test_l_export_sans_aucune_altitude_reste_muet(window, tmp_path):
    """Aucune balise inventée quand l'altitude est inconnue."""
    track_id = window.db.create_track("Sans altitude", points=DEUX)
    window.tree_panel.refresh()

    chemin = window.export_track(track_id, path=str(tmp_path / "sortie.gpx"))

    assert "<ele>" not in Path(chemin).read_text(encoding="utf-8")


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


def test_une_base_en_lecture_seule_est_refusee_des_l_ouverture(tmp_path):
    """Régression : le refus d'écriture n'apparaissait qu'à la première trace.

    Une base restaurée d'une sauvegarde garde souvent l'attribut « lecture
    seule ». Tout se passait bien jusqu'au premier enregistrement, où
    l'exception, levée dans un signal Qt, emportait l'application.
    """
    chemin = tmp_path / "carto.db"
    Database(chemin).close()

    protegees = [
        p for p in tmp_path.iterdir() if p.name.startswith("carto.db")
    ]
    for fichier in protegees:
        os.chmod(fichier, stat.S_IREAD)
    try:
        with pytest.raises(sqlite3.OperationalError):
            Database(chemin)
    finally:
        for fichier in protegees:
            os.chmod(fichier, stat.S_IWRITE | stat.S_IREAD)


def test_l_ouverture_laisse_une_trace_datee(tmp_path):
    """L'écriture d'ouverture est ce qui révèle une base non inscriptible."""
    chemin = tmp_path / "carto.db"
    with Database(chemin) as db:
        ligne = db.conn.execute(
            "SELECT value FROM meta WHERE key = 'derniere_ouverture'"
        ).fetchone()

    assert ligne is not None and ligne["value"]


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
