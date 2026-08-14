"""Tests de la trace brouillon maintenue en mémoire (Jalon 3)."""

from __future__ import annotations

import pytest

from geocairn.editor import DraftTrack
from geocairn.geo import total_length
from geocairn.models import Point


def test_brouillon_vide_au_depart():
    draft = DraftTrack()
    assert draft.is_empty
    assert len(draft) == 0
    assert draft.points == []
    assert draft.length_m == 0.0
    assert draft.summary() == "Brouillon vide"


def test_ajout_de_points_dans_l_ordre():
    draft = DraftTrack()
    draft.add_point(48.930, 1.440)
    draft.add_point(48.931, 1.442)
    draft.add_point(48.932, 1.441)

    assert len(draft) == 3
    assert not draft.is_empty
    assert [p.as_tuple() for p in draft.points] == [
        (48.930, 1.440),
        (48.931, 1.442),
        (48.932, 1.441),
    ]


def test_ajout_retourne_le_point_cree():
    draft = DraftTrack()
    point = draft.add_point(48.93, 1.44, ele=75.0)
    assert point == Point(48.93, 1.44, 75.0)


def test_annulation_retire_le_dernier_point():
    draft = DraftTrack()
    draft.add_point(48.930, 1.440)
    draft.add_point(48.931, 1.442)

    removed = draft.undo_last()

    assert removed.as_tuple() == (48.931, 1.442)
    assert len(draft) == 1
    assert draft.points[0].as_tuple() == (48.930, 1.440)


def test_annulations_successives_jusqu_au_vide():
    draft = DraftTrack()
    for i in range(3):
        draft.add_point(48.93 + i / 1000, 1.44)

    for _ in range(3):
        assert draft.undo_last() is not None

    assert draft.is_empty
    assert draft.undo_last() is None  # ne lève pas sur un brouillon vide


def test_annulation_puis_reprise():
    """Régression : après annulation, l'ajout repart de la bonne position."""
    draft = DraftTrack()
    draft.add_point(48.930, 1.440)
    draft.add_point(48.931, 1.442)
    draft.undo_last()
    draft.add_point(48.935, 1.450)

    assert [p.as_tuple() for p in draft.points] == [
        (48.930, 1.440),
        (48.935, 1.450),
    ]


def test_effacement_complet():
    draft = DraftTrack()
    draft.add_point(48.930, 1.440)
    draft.add_point(48.931, 1.442)

    draft.clear()

    assert draft.is_empty
    assert draft.points == []


def test_les_points_exposes_sont_une_copie():
    """Modifier la liste retournée ne doit pas corrompre le brouillon."""
    draft = DraftTrack()
    draft.add_point(48.930, 1.440)

    draft.points.append(Point(0.0, 0.0))

    assert len(draft) == 1


def test_longueur_du_brouillon():
    draft = DraftTrack()
    draft.add_point(45.0, 3.0)
    draft.add_point(46.0, 3.0)

    assert draft.length_m == pytest.approx(111_195, rel=0.001)
    assert draft.length_m == pytest.approx(total_length(draft.points))


def test_resume_affichable():
    draft = DraftTrack()
    draft.add_point(45.0, 3.0)
    assert draft.summary() == "Brouillon : 1 point — 0 m"

    draft.add_point(46.0, 3.0)
    assert draft.summary().startswith("Brouillon : 2 points — 111,")


def test_remplacement_des_points():
    draft = DraftTrack()
    draft.add_point(48.930, 1.440)

    draft.set_points([Point(45.0, 3.0), Point(46.0, 3.0)])

    assert len(draft) == 2
    assert draft.points[0].as_tuple() == (45.0, 3.0)
