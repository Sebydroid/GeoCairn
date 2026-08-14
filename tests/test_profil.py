"""Tests du profil : séries, vitesses et rendu."""

from __future__ import annotations

import pytest

from geocairn.app import create_app
from geocairn.geo import cumulative_distances, has_times, speeds
from geocairn.models import Point
from geocairn.ui.profile_panel import (
    SOURCE_ELE_FICHIER,
    SOURCE_ELE_SERVICE,
    SOURCE_VITESSE,
    ProfilePanel,
    series_for,
    source_available,
)


@pytest.fixture(scope="session")
def qapp():
    app = create_app(["geocairn-tests"])
    yield app
    app.processEvents()


AVEC_TOUT = [
    Point(48.930, 1.440, 70.0, "2026-08-10T09:00:00Z", 63.2),
    Point(48.931, 1.442, 75.0, "2026-08-10T09:01:00Z", 68.0),
    Point(48.932, 1.441, 80.0, "2026-08-10T09:02:00Z", 74.5),
]

DESSINEE = [Point(48.930, 1.440), Point(48.931, 1.442), Point(48.932, 1.441)]


# ------------------------------------------------------ distances cumulées


def test_distances_cumulees():
    distances = cumulative_distances(AVEC_TOUT)

    assert len(distances) == 3
    assert distances[0] == 0.0
    assert distances[1] < distances[2]


def test_distances_cumulees_cas_limites():
    assert cumulative_distances([]) == []
    assert cumulative_distances([Point(48.0, 1.0)]) == [0.0]


# ------------------------------------------------------------- vitesses


def test_vitesse_calculee_a_partir_des_horodatages():
    """Un degré de latitude en une heure, soit environ 111 km/h."""
    points = [
        Point(45.0, 3.0, time="2026-08-10T09:00:00Z"),
        Point(46.0, 3.0, time="2026-08-10T10:00:00Z"),
    ]

    resultat = speeds(points)

    assert resultat[1] == pytest.approx(111.2, rel=0.01)


def test_le_premier_point_herite_du_second():
    points = [
        Point(45.0, 3.0, time="2026-08-10T09:00:00Z"),
        Point(45.1, 3.0, time="2026-08-10T09:10:00Z"),
    ]
    resultat = speeds(points)

    assert resultat[0] == resultat[1]


def test_sans_horodatage_aucune_vitesse():
    assert speeds(DESSINEE) == [None, None, None]
    assert has_times(DESSINEE) is False


def test_horodatage_partiel():
    points = [
        Point(45.0, 3.0, time="2026-08-10T09:00:00Z"),
        Point(45.1, 3.0),
        Point(45.2, 3.0, time="2026-08-10T09:20:00Z"),
    ]

    resultat = speeds(points)

    assert resultat[1] is None
    assert resultat[2] is None   # le point précédent n'a pas d'heure


def test_horodatage_immobile():
    """Deux points à la même seconde ne donnent pas une vitesse infinie."""
    points = [
        Point(45.0, 3.0, time="2026-08-10T09:00:00Z"),
        Point(45.1, 3.0, time="2026-08-10T09:00:00Z"),
    ]

    assert speeds(points)[1] is None


def test_horodatage_illisible():
    points = [
        Point(45.0, 3.0, time="pas une date"),
        Point(45.1, 3.0, time="2026-08-10T09:10:00Z"),
    ]

    assert speeds(points)[1] is None
    assert has_times(points) is False


def test_vitesses_cas_limites():
    assert speeds([]) == []
    assert speeds([Point(48.0, 1.0)]) == [None]


# --------------------------------------------------------------- séries


def test_serie_altitude_du_fichier():
    assert series_for(AVEC_TOUT, SOURCE_ELE_FICHIER) == [70.0, 75.0, 80.0]


def test_serie_altitude_du_service():
    assert series_for(AVEC_TOUT, SOURCE_ELE_SERVICE) == [63.2, 68.0, 74.5]


def test_serie_vitesse():
    valeurs = series_for(AVEC_TOUT, SOURCE_VITESSE)
    assert all(v is not None for v in valeurs)


def test_disponibilite_des_sources():
    assert source_available(AVEC_TOUT, SOURCE_ELE_FICHIER) is True
    assert source_available(AVEC_TOUT, SOURCE_ELE_SERVICE) is True
    assert source_available(AVEC_TOUT, SOURCE_VITESSE) is True

    assert source_available(DESSINEE, SOURCE_ELE_FICHIER) is False
    assert source_available(DESSINEE, SOURCE_ELE_SERVICE) is False
    assert source_available(DESSINEE, SOURCE_VITESSE) is False


def test_une_seule_valeur_ne_suffit_pas():
    points = [Point(48.9, 1.4, 70.0), Point(48.91, 1.41)]
    assert source_available(points, SOURCE_ELE_FICHIER) is False


# ------------------------------------------------------------- panneau


def test_le_panneau_propose_les_trois_sources(qapp):
    panel = ProfilePanel()

    libelles = [case.text() for case in panel.checks.values()]

    assert libelles == ["Altitude du fichier", "Altitude IGN", "Vitesse"]


def test_le_panneau_trace_l_altitude(qapp):
    panel = ProfilePanel()
    panel.set_points(AVEC_TOUT, "Rallye")

    assert panel.active_sources == [SOURCE_ELE_FICHIER]
    assert panel.view.has_data is True
    assert "Rallye" in panel.title.text()


def test_changement_de_source(qapp):
    panel = ProfilePanel()
    panel.set_points(AVEC_TOUT, "Rallye")

    assert panel.set_source(SOURCE_VITESSE) is True
    assert panel.active_sources == [SOURCE_VITESSE]
    assert panel.view.has_data is True


# ------------------------------------------------- plusieurs grandeurs


def test_superposition_de_plusieurs_grandeurs(qapp):
    panel = ProfilePanel()
    panel.set_points(AVEC_TOUT, "Rallye")

    panel.add_source(SOURCE_ELE_SERVICE)
    panel.add_source(SOURCE_VITESSE)

    assert set(panel.active_sources) == {
        SOURCE_ELE_FICHIER, SOURCE_ELE_SERVICE, SOURCE_VITESSE
    }
    assert len(panel.view._series) == 3
    assert panel.view.has_data is True


def test_deux_echelles_pour_deux_unites(qapp):
    """Mètres et km/h ne peuvent pas partager la même graduation."""
    panel = ProfilePanel()
    panel.set_points(AVEC_TOUT, "Rallye")
    panel.set_sources([SOURCE_ELE_FICHIER, SOURCE_VITESSE])

    assert panel.view.units == ["m", "km/h"]


def test_une_seule_echelle_pour_les_deux_altitudes(qapp):
    panel = ProfilePanel()
    panel.set_points(AVEC_TOUT, "Rallye")
    panel.set_sources([SOURCE_ELE_FICHIER, SOURCE_ELE_SERVICE])

    assert panel.view.units == ["m"]
    # Les deux altitudes doivent tenir sur la même graduation.
    bas, haut = panel.view._bornes("m")
    assert bas < 63.2 and haut > 80.0


def test_les_grandeurs_sans_donnee_sont_ignorees(qapp):
    """Cocher une grandeur absente ne doit pas casser le tracé."""
    panel = ProfilePanel()
    panel.set_points(AVEC_TOUT, "Rallye")
    panel.set_sources([SOURCE_ELE_FICHIER, SOURCE_ELE_SERVICE])
    panel.set_points(DESSINEE, "Dessinée")

    assert panel.view.has_data is False
    panel.view.resize(400, 120)
    panel.view.grab()   # ne doit pas lever


def test_aucune_grandeur_cochee(qapp):
    panel = ProfilePanel()
    panel.set_points(AVEC_TOUT, "Rallye")

    panel.set_sources([])

    assert panel.view.has_data is False
    assert "Cochez" in panel.view._message


def test_le_trace_multiple_se_dessine(qapp):
    panel = ProfilePanel()
    panel.set_points(AVEC_TOUT, "Rallye")
    panel.set_sources([SOURCE_ELE_FICHIER, SOURCE_ELE_SERVICE, SOURCE_VITESSE])
    panel.view.resize(600, 140)

    panel.view.grab()   # légende, deux axes et trois courbes


def test_source_indisponible_expliquee(qapp):
    """Une trace dessinée à la main n'a ni altitude ni vitesse."""
    panel = ProfilePanel()
    panel.set_points(DESSINEE, "Dessinée")

    assert panel.view.has_data is False

    panel.set_source(SOURCE_ELE_SERVICE)
    assert "Calculer l'altitude" in panel.view._message

    panel.set_source(SOURCE_VITESSE)
    assert "horodatage" in panel.view._message


def test_les_sources_absentes_sont_signalees(qapp):
    """Le manque est expliqué en infobulle, la case reste utilisable."""
    panel = ProfilePanel()
    panel.set_points(DESSINEE, "Dessinée")

    assert "horodatage" in panel.checks[SOURCE_VITESSE].toolTip()
    assert "altitude" in panel.checks[SOURCE_ELE_FICHIER].toolTip().lower()

    panel.set_points(AVEC_TOUT, "Complète")
    assert panel.checks[SOURCE_ELE_FICHIER].toolTip() == ""
    assert panel.checks[SOURCE_VITESSE].toolTip() == ""


def test_une_case_reste_decochable_sans_donnee(qapp):
    """Régression : une case grisée alors qu'elle était cochée restait bloquée.

    En passant d'une trace pourvue d'altitude IGN à une trace qui n'en a pas,
    la case restait cochée et grisée, donc impossible à décocher.
    """
    panel = ProfilePanel()
    panel.set_points(AVEC_TOUT, "Complète")
    panel.set_sources([SOURCE_ELE_FICHIER, SOURCE_ELE_SERVICE])

    panel.set_points(DESSINEE, "Sans altitude IGN")

    assert panel.checks[SOURCE_ELE_SERVICE].isChecked() is True
    assert panel.checks[SOURCE_ELE_SERVICE].isEnabled() is True

    panel.checks[SOURCE_ELE_SERVICE].setChecked(False)
    assert SOURCE_ELE_SERVICE not in panel.active_sources


def test_panneau_vide(qapp):
    panel = ProfilePanel()
    panel.set_points([], "")

    assert panel.view.has_data is False
    assert "Sélectionnez une trace" in panel.view._message


def test_clic_sur_le_profil_designe_un_point(qapp):
    panel = ProfilePanel()
    panel.set_points(AVEC_TOUT, "Rallye")
    panel.view.resize(400, 120)
    recus = []
    panel.point_clicked.connect(recus.append)

    zone = panel.view._plot_rect()
    panel.view.point_clicked.emit(panel.view.index_at(zone.right()))

    assert recus == [2]   # extrémité droite : dernier point


def test_indice_sous_une_abscisse(qapp):
    panel = ProfilePanel()
    panel.set_points(AVEC_TOUT, "Rallye")
    panel.view.resize(400, 120)
    zone = panel.view._plot_rect()

    assert panel.view.index_at(zone.left()) == 0
    assert panel.view.index_at(zone.right()) == 2


def test_un_titre_long_n_elargit_pas_les_panneaux(qapp, db):
    """Régression : le nom de la trace imposait sa longueur au panneau.

    Une QLabel ordinaire réclame la largeur de son texte ; le panneau de gauche
    occupait alors la moitié de la fenêtre.
    """
    from geocairn.ui.main_window import MainWindow

    nom = "OR-7128277--Pacy-sur-Eure:Parcours 20km Samedi Moyens W-E Jeunes"
    track_id = db.create_track(nom, points=AVEC_TOUT)
    window = MainWindow(db=db)
    window.resize(1180, 680)
    window.show()
    qapp.processEvents()
    window.tree_panel.refresh()
    window.tree_panel.select_track(track_id)

    # Le texte complet reste disponible, seul l'affichage est abrégé.
    assert nom in window.points_panel.title.text()
    assert nom in window.points_panel.title.toolTip()

    # Largeur réellement attribuée : le panneau de gauche doit rester étroit.
    gauche, droite = window.centralWidget().sizes()
    assert gauche <= 400, "le panneau de gauche mange la fenêtre"
    assert droite > gauche

    window.close()


def test_le_trace_supporte_les_trous(qapp):
    """Des altitudes manquantes au milieu ne doivent pas casser le rendu."""
    points = [
        Point(48.930, 1.440, 70.0),
        Point(48.931, 1.442),
        Point(48.932, 1.441, 80.0),
        Point(48.933, 1.439, 85.0),
    ]
    panel = ProfilePanel()
    panel.set_points(points, "Trouée")
    panel.view.resize(400, 120)

    assert panel.view.has_data is True
    panel.view.grab()   # ne doit pas lever
