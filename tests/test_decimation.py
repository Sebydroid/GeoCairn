"""Décimation d'une trace : algorithme et intégration."""

from __future__ import annotations

import math
import time

import pytest
from PyQt6.QtWidgets import QInputDialog, QMessageBox

from geocairn.app import create_app
from geocairn.database import Database
from geocairn.geo import total_length
from geocairn.models import Point
from geocairn.simplify import (
    _distance_au_segment,
    _projeter,
    douglas_peucker,
    simplify_to,
)
from geocairn.ui.main_window import MainWindow


def ligne_droite(n: int) -> list[Point]:
    """Points parfaitement alignés : tous les intermédiaires sont superflus."""
    return [Point(48.0 + i / 1000, 1.0 + i / 1000) for i in range(n)]


def zigzag(n: int) -> list[Point]:
    """Points en dents de scie : aucun n'est superflu."""
    return [
        Point(48.0 + i / 1000, 1.0 + (0.001 if i % 2 else 0.0))
        for i in range(n)
    ]


def bruitee(n: int) -> list[Point]:
    """Ligne droite parsemée de micro-écarts, comme un relevé GPS."""
    points = []
    for i in range(n):
        ecart = 0.000004 * (1 if i % 3 else -1)
        points.append(Point(48.0 + i / 2000 + ecart, 1.0 + ecart))
    return points


@pytest.fixture(scope="session")
def qapp():
    app = create_app(["geocairn-tests"])
    yield app
    app.processEvents()


# --------------------------------------------------- Douglas-Peucker


def test_une_ligne_droite_se_reduit_a_ses_extremites():
    resultat = douglas_peucker(ligne_droite(50), tolerance=1.0)

    assert len(resultat) == 2
    assert resultat[0].as_tuple() == (48.0, 1.0)


def test_les_extremites_sont_toujours_conservees():
    points = zigzag(21)
    resultat = douglas_peucker(points, tolerance=5.0)

    assert resultat[0].as_tuple() == points[0].as_tuple()
    assert resultat[-1].as_tuple() == points[-1].as_tuple()


def test_une_tolerance_nulle_ne_retire_rien():
    points = zigzag(11)
    assert len(douglas_peucker(points, tolerance=0.0)) == len(points)


def test_les_virages_resistent_mieux_que_les_lignes_droites():
    """C'est tout l'intérêt : ne pas raboter la forme du tracé."""
    droite = douglas_peucker(ligne_droite(51), tolerance=2.0)
    dents = douglas_peucker(zigzag(51), tolerance=2.0)

    assert len(droite) < len(dents)


def test_trace_trop_courte():
    points = [Point(48.0, 1.0), Point(48.1, 1.1)]
    assert douglas_peucker(points, tolerance=10.0) == points


# ------------------------------------------------ réduction à une cible


def test_reduction_a_un_nombre_voulu():
    resultat = simplify_to(bruitee(400), 50)

    # Le compte est approché, jamais dépassé de beaucoup.
    assert 30 <= len(resultat) <= 60


def test_la_reduction_conserve_le_depart_et_l_arrivee():
    points = bruitee(300)
    resultat = simplify_to(points, 40)

    assert resultat[0].as_tuple() == points[0].as_tuple()
    assert resultat[-1].as_tuple() == points[-1].as_tuple()


def test_la_reduction_conserve_l_ordre():
    resultat = simplify_to(bruitee(300), 40)
    latitudes = [p.lat for p in resultat]
    assert latitudes == sorted(latitudes)


def test_la_longueur_reste_proche():
    """Alléger la trace ne doit pas la raccourcir sensiblement."""
    points = bruitee(400)
    resultat = simplify_to(points, 60)

    assert total_length(resultat) == pytest.approx(total_length(points), rel=0.05)


def test_cible_superieure_au_nombre_de_points():
    points = bruitee(20)
    assert simplify_to(points, 100) == points


def test_cible_minimale():
    resultat = simplify_to(bruitee(200), 1)
    assert len(resultat) >= 2


def test_altitude_et_horodatage_suivent():
    points = [
        Point(48.0, 1.0, 70.0, "2026-08-10T09:00:00Z"),
        Point(48.001, 1.0005, 71.0, "2026-08-10T09:01:00Z"),
        Point(48.002, 1.001, 72.0, "2026-08-10T09:02:00Z"),
        Point(48.010, 1.020, 90.0, "2026-08-10T09:10:00Z"),
    ]
    resultat = simplify_to(points, 2)

    assert resultat[0].ele == pytest.approx(70.0)
    assert resultat[0].time == "2026-08-10T09:00:00Z"


# ------------------------------------- classement des points par poids


def test_le_compte_demande_est_exact():
    """Le classement par poids donne le nombre voulu, pas une approximation."""
    points = bruitee(500)

    for cible in (2, 10, 137, 499):
        assert len(simplify_to(points, cible)) == cible


def test_une_cible_plus_grande_contient_la_plus_petite():
    """Les points retenus s'emboîtent : c'est ce qui rend le classement juste."""
    points = bruitee(300)

    petite = {p.as_tuple() for p in simplify_to(points, 20)}
    grande = {p.as_tuple() for p in simplify_to(points, 60)}

    assert petite <= grande


def ecart_maximal(origine, allegee) -> float:
    """Distance maximale entre les points d'origine et le tracé allégé, en m."""
    plans_origine = _projeter(origine)
    plans_allegee = _projeter(allegee)
    pire = 0.0
    for point in plans_origine:
        proche = min(
            _distance_au_segment(point, plans_allegee[i], plans_allegee[i + 1])
            for i in range(len(plans_allegee) - 1)
        )
        pire = max(pire, proche)
    return pire


def test_la_forme_est_preservee():
    """Alléger ne doit pas déplacer le tracé : c'est tout l'enjeu.

    Les virages d'une trace de mille points doivent rester reconnaissables une
    fois ramenée au dixième.
    """
    points = [
        Point(48.0 + 0.01 * math.sin(i / 50), 1.0 + i / 5000) for i in range(1000)
    ]

    allegee = simplify_to(points, 100)

    # Le tracé s'étend sur plusieurs kilomètres : quelques mètres d'écart ne se
    # voient pas à l'écran.
    assert ecart_maximal(points, allegee) < 10.0


def test_une_trace_tres_longue_ne_deborde_pas_la_pile():
    """Régression : le découpage récursif pouvait dépasser la profondeur permise."""
    points = ligne_droite(20000)

    resultat = douglas_peucker(points, tolerance=0.5)

    assert len(resultat) == 2


def test_la_decimation_d_une_trace_dense_reste_rapide():
    """Régression : quarante passes de l'algorithme figeaient l'interface.

    Décimer vingt mille points demandait une quinzaine de secondes, sans
    indication ni moyen d'interrompre. Le seuil est large : il ne mesure pas la
    machine, il signale le retour de la recherche par essais successifs.
    """
    points = bruitee(20000)

    debut = time.perf_counter()
    resultat = simplify_to(points, 2000)
    ecoule = time.perf_counter() - debut

    assert len(resultat) == 2000
    assert ecoule < 3.0, f"décimation de 20 000 points : {ecoule:.1f} s"


# ----------------------------------------------------- en base


def test_decimation_cree_une_copie(db):
    original = db.create_track("Relevé GPS", points=bruitee(400))

    copie = db.decimate_track(original, 50)

    assert copie is not None and copie != original
    assert db.get_track(copie).name == "Relevé GPS-décimé"
    assert db.count_points(original) == 400        # l'original est intact
    assert 30 <= db.count_points(copie) <= 60


def test_la_copie_reste_dans_le_meme_dossier(db):
    dossier = db.create_folder("Sorties")
    original = db.create_track("Relevé", folder_id=dossier, points=bruitee(200))

    copie = db.decimate_track(original, 30)

    assert db.get_track(copie).folder_id == dossier


def test_le_style_suit_la_decimation(db):
    original = db.create_track("Relevé", points=bruitee(200))
    db.set_track_style(original, color="#f08c00", opacity=0.5)

    copie = db.decimate_track(original, 30)

    assert db.get_track(copie).color == "#f08c00"
    assert db.get_track(copie).opacity == pytest.approx(0.5)


def test_decimation_inutile(db):
    original = db.create_track("Courte", points=bruitee(10))
    assert db.decimate_track(original, 50) is None


def test_noms_successifs(db):
    original = db.create_track("Relevé", points=bruitee(200))

    db.decimate_track(original, 40)
    db.decimate_track(original, 20)

    noms = sorted(t.name for t in db.list_tracks(None))
    assert noms == ["Relevé", "Relevé-décimé", "Relevé-décimé 2"]


# ----------------------------------------------------- interface


@pytest.fixture
def window(qapp, db, monkeypatch):
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: None))
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: None))
    win = MainWindow(db=db)
    yield win
    win.close()


def test_decimation_depuis_l_interface(window):
    original = window.db.create_track("Relevé GPS", points=bruitee(400))
    window.tree_panel.refresh()

    copie = window.decimate_track(original, 50)

    assert copie is not None
    assert 30 <= window.db.count_points(copie) <= 60
    assert "décimée" in window.status_label.text()


def test_le_nombre_de_points_est_propose(window, monkeypatch):
    """La boîte doit rappeler le nombre actuel et proposer une cible."""
    original = window.db.create_track("Relevé GPS", points=bruitee(400))
    window.tree_panel.refresh()
    vus = {}

    def faux_getint(_parent, titre, libelle, valeur, mini, maxi, pas):
        vus.update(titre=titre, libelle=libelle, valeur=valeur, maxi=maxi)
        return (60, True)

    monkeypatch.setattr(QInputDialog, "getInt", staticmethod(faux_getint))
    window.decimate_track(original)

    assert "400 points" in vus["libelle"]
    assert "Relevé GPS" in vus["titre"]
    assert vus["maxi"] == 399


def test_annulation_de_la_decimation(window, monkeypatch):
    original = window.db.create_track("Relevé", points=bruitee(200))
    window.tree_panel.refresh()
    monkeypatch.setattr(
        QInputDialog, "getInt", staticmethod(lambda *a, **k: (50, False))
    )

    assert window.decimate_track(original) is None
    assert len(window.db.list_tracks(None)) == 1


def test_decimation_d_une_trace_trop_courte(window):
    original = window.db.create_track("Deux points", points=bruitee(2))
    window.tree_panel.refresh()

    assert window.decimate_track(original, 1) is None


def test_la_copie_decimee_est_affichee(window):
    original = window.db.create_track("Relevé", points=bruitee(300))
    window.tree_panel.refresh()

    copie = window.decimate_track(original, 40)

    assert copie in window.visible_tracks
