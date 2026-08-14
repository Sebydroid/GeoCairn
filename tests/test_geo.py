"""Tests des calculs géographiques."""

from __future__ import annotations

import pytest

from geocairn.geo import bounds, distance, format_length, total_length
from geocairn.models import Point


def test_distance_nulle():
    p = Point(48.9, 1.44)
    assert distance(p, p) == pytest.approx(0.0)


def test_distance_connue_paris_marseille():
    paris = Point(48.8566, 2.3522)
    marseille = Point(43.2965, 5.3698)
    # Distance orthodromique de référence : ~660 km.
    assert distance(paris, marseille) == pytest.approx(660_000, rel=0.01)


def test_distance_un_degre_de_latitude():
    """Un degré de latitude vaut environ 111,2 km partout sur le globe."""
    assert distance(Point(45.0, 3.0), Point(46.0, 3.0)) == pytest.approx(
        111_195, rel=0.001
    )


def test_distance_symetrique():
    a, b = Point(48.93, 1.44), Point(48.94, 1.45)
    assert distance(a, b) == pytest.approx(distance(b, a))


def test_longueur_totale_cumule_les_segments():
    points = [Point(45.0, 3.0), Point(46.0, 3.0), Point(47.0, 3.0)]
    attendu = distance(points[0], points[1]) + distance(points[1], points[2])
    assert total_length(points) == pytest.approx(attendu)


def test_longueur_totale_cas_limites():
    assert total_length([]) == 0.0
    assert total_length([Point(48.0, 1.0)]) == 0.0


def test_rectangle_englobant():
    points = [Point(48.5, 1.0), Point(49.0, 2.5), Point(48.2, 1.8)]
    assert bounds(points) == ((48.2, 1.0), (49.0, 2.5))


def test_rectangle_englobant_vide():
    assert bounds([]) is None


def test_formatage_des_longueurs():
    assert format_length(0) == "0 m"
    assert format_length(850) == "850 m"
    assert format_length(999) == "999 m"
    assert format_length(1000) == "1,00 km"
    assert format_length(12_340) == "12,34 km"
