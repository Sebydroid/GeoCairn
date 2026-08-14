"""Tests du modèle d'édition avancée : brouillon et base (Jalon 6)."""

from __future__ import annotations

import pytest

from geocairn.database import NotFoundError
from geocairn.editor import DraftTrack
from geocairn.models import Point, Track


@pytest.fixture
def draft() -> DraftTrack:
    d = DraftTrack()
    for lat, lon in [(48.930, 1.440), (48.931, 1.442), (48.932, 1.441),
                     (48.933, 1.439)]:
        d.add_point(lat, lon)
    return d


# ------------------------------------------------- reprise d'une trace (a)


def test_brouillon_neuf_n_est_pas_rattache_a_une_trace():
    d = DraftTrack()
    assert d.is_existing is False
    assert d.track_id is None


def test_reprise_d_une_trace_enregistree():
    track = Track(id=7, name="Rallye V1", points=[Point(48.9, 1.4), Point(48.91, 1.41)])
    d = DraftTrack()

    d.load_track(track)

    assert d.is_existing is True
    assert d.track_id == 7
    assert d.name == "Rallye V1"
    assert len(d) == 2


def test_extension_d_une_trace_reprise():
    """Reprendre une trace, c'est pouvoir la prolonger par la fin."""
    track = Track(id=7, name="Trace", points=[Point(48.9, 1.4), Point(48.91, 1.41)])
    d = DraftTrack()
    d.load_track(track)

    d.add_point(48.92, 1.42)

    assert [p.as_tuple() for p in d.points][-1] == (48.92, 1.42)
    assert d.track_id == 7  # toujours la même trace


def test_reinitialisation_detache_la_trace(draft):
    draft.track_id = 7
    draft.reset()

    assert draft.is_existing is False
    assert draft.is_empty
    assert draft.name == "Nouvelle trace"


def test_effacement_conserve_le_rattachement(draft):
    """clear() vide les points mais on reste sur la même trace."""
    draft.track_id = 7
    draft.clear()

    assert draft.is_empty
    assert draft.track_id == 7


def test_resume_distingue_creation_et_modification(draft):
    assert draft.summary().startswith("Brouillon :")

    draft.track_id = 7
    draft.name = "Rallye V1"
    assert draft.summary().startswith("Modification de « Rallye V1 » :")


# ------------------------------------------------- fermeture en boucle (b)


def test_fermeture_en_boucle(draft):
    assert draft.is_loop is False

    assert draft.close_loop() is True

    assert len(draft) == 5
    assert draft.points[0].as_tuple() == draft.points[-1].as_tuple()
    assert draft.is_loop is True


def test_fermeture_idempotente(draft):
    draft.close_loop()
    assert draft.close_loop() is False
    assert len(draft) == 5


def test_fermeture_refusee_sous_trois_points():
    d = DraftTrack()
    d.add_point(48.9, 1.4)
    d.add_point(48.91, 1.41)

    assert d.close_loop() is False
    assert len(d) == 2
    assert d.is_loop is False


def test_boucle_conserve_l_altitude_du_depart():
    d = DraftTrack()
    d.add_point(48.9, 1.4, ele=70.0)
    d.add_point(48.91, 1.41)
    d.add_point(48.92, 1.42)

    d.close_loop()

    assert d.points[-1].ele == pytest.approx(70.0)


# --------------------------------------------- déplacement d'un point (c)


def test_deplacement_d_un_point(draft):
    assert draft.move_point(1, 48.9999, 1.4999) is True

    assert draft.points[1].as_tuple() == (48.9999, 1.4999)
    assert len(draft) == 4  # aucun point ajouté ni retiré


def test_deplacement_conserve_altitude_et_horodatage():
    d = DraftTrack()
    d.set_points([Point(48.9, 1.4, 70.0, "2026-08-10T09:00:00Z")])

    d.move_point(0, 48.95, 1.45)

    assert d.points[0].ele == pytest.approx(70.0)
    assert d.points[0].time == "2026-08-10T09:00:00Z"


def test_deplacement_hors_bornes_refuse(draft):
    assert draft.move_point(-1, 48.0, 1.0) is False
    assert draft.move_point(99, 48.0, 1.0) is False
    assert len(draft) == 4


def test_deplacement_du_premier_point_d_une_boucle(draft):
    """Sur une boucle, déplacer le départ laisse l'arrivée là où elle est."""
    draft.close_loop()

    draft.move_point(0, 48.800, 1.400)

    assert draft.points[0].as_tuple() == (48.800, 1.400)
    assert draft.points[-1].as_tuple() == (48.930, 1.440)
    assert draft.is_loop is False  # la boucle s'ouvre, c'est visible sur la carte


# --------------------------------------------- suppression de points (d)


def test_suppression_d_un_point_precis(draft):
    supprime = draft.remove_point(1)

    assert supprime.as_tuple() == (48.931, 1.442)
    assert len(draft) == 3
    assert [p.as_tuple() for p in draft.points] == [
        (48.930, 1.440), (48.932, 1.441), (48.933, 1.439),
    ]


def test_suppression_hors_bornes(draft):
    assert draft.remove_point(99) is None
    assert draft.remove_point(-1) is None
    assert len(draft) == 4


def test_suppression_d_une_selection(draft):
    """Les indices doivent rester justes pendant la suppression multiple."""
    supprimes = draft.remove_points([0, 2])

    assert supprimes == 2
    assert [p.as_tuple() for p in draft.points] == [
        (48.931, 1.442), (48.933, 1.439),
    ]


def test_suppression_multiple_dans_le_desordre(draft):
    draft.remove_points([2, 0])
    assert [p.as_tuple() for p in draft.points] == [
        (48.931, 1.442), (48.933, 1.439),
    ]


def test_suppression_multiple_ignore_doublons_et_hors_bornes(draft):
    assert draft.remove_points([1, 1, 99, -5]) == 1
    assert len(draft) == 3


def test_suppression_de_tous_les_points(draft):
    assert draft.remove_points(range(4)) == 4
    assert draft.is_empty


# ------------------------------------------------------- découpage (e)


def test_decoupage_du_brouillon(draft):
    premiere, seconde = draft.split_at(1)

    assert [p.as_tuple() for p in premiere] == [(48.930, 1.440), (48.931, 1.442)]
    assert [p.as_tuple() for p in seconde] == [
        (48.931, 1.442), (48.932, 1.441), (48.933, 1.439),
    ]


def test_le_point_de_coupe_appartient_aux_deux_moities(draft):
    premiere, seconde = draft.split_at(2)
    assert premiere[-1].as_tuple() == seconde[0].as_tuple()


def test_decoupage_refuse_aux_extremites(draft):
    assert draft.split_at(0) is None
    assert draft.split_at(3) is None  # dernier point
    assert draft.split_at(99) is None


def test_decoupage_d_une_trace_trop_courte():
    d = DraftTrack()
    d.add_point(48.9, 1.4)
    d.add_point(48.91, 1.41)
    d.add_point(48.92, 1.42)

    assert d.split_at(1) is not None  # 2 + 2 points, tout juste possible
    assert d.split_at(2) is None


# ------------------------------------------ duplication en base (g)


def test_duplication_d_une_trace(db, sample_points):
    folder = db.create_folder("Alpes")
    original = db.create_track("Rallye V1", folder_id=folder, points=sample_points)

    copie = db.duplicate_track(original)

    assert copie != original
    track = db.get_track(copie, with_points=True)
    assert track.name == "Rallye V1-copie"
    assert track.folder_id == folder
    assert [p.as_tuple() for p in track.points] == [
        p.as_tuple() for p in sample_points
    ]


def test_duplication_avec_nom_choisi(db, sample_points):
    original = db.create_track("Trace", points=sample_points)
    copie = db.duplicate_track(original, "Variante 2026")
    assert db.get_track(copie).name == "Variante 2026"


def test_la_copie_est_independante(db, sample_points):
    original = db.create_track("Trace", points=sample_points)
    copie = db.duplicate_track(original)

    db.replace_points(copie, sample_points[:2])

    assert db.count_points(original) == 4
    assert db.count_points(copie) == 2


def test_duplication_d_une_trace_inexistante(db):
    with pytest.raises(NotFoundError):
        db.duplicate_track(999)


# ---------------------------------------------- découpage en base (e)


def test_decoupage_en_base(db, sample_points):
    track_id = db.create_track("Longue", points=sample_points)

    premier, second = db.split_track(track_id, 1)

    assert premier == track_id
    assert db.get_track(premier).name == "Longue"
    assert db.get_track(second).name == "Longue (suite)"
    assert [p.as_tuple() for p in db.get_points(premier)] == [
        sample_points[0].as_tuple(), sample_points[1].as_tuple(),
    ]
    assert [p.as_tuple() for p in db.get_points(second)] == [
        p.as_tuple() for p in sample_points[1:]
    ]


def test_les_deux_moities_se_touchent(db, sample_points):
    track_id = db.create_track("Longue", points=sample_points)
    premier, second = db.split_track(track_id, 2)

    assert db.get_points(premier)[-1].as_tuple() == (
        db.get_points(second)[0].as_tuple()
    )


def test_decoupage_dans_le_meme_dossier(db, sample_points):
    folder = db.create_folder("Alpes")
    track_id = db.create_track("Longue", folder_id=folder, points=sample_points)

    _premier, second = db.split_track(track_id, 1)

    assert db.get_track(second).folder_id == folder


def test_decoupage_refuse_aux_extremites_en_base(db, sample_points):
    track_id = db.create_track("Longue", points=sample_points)

    with pytest.raises(ValueError, match="deux points"):
        db.split_track(track_id, 0)
    with pytest.raises(ValueError):
        db.split_track(track_id, 3)
    assert db.count_points(track_id) == 4  # rien n'a bougé


def test_decoupage_d_une_boucle_leve_l_indicateur(db, sample_points):
    track_id = db.create_track("Boucle", points=sample_points, is_loop=True)

    db.split_track(track_id, 1)

    assert db.get_track(track_id).is_loop is False


# ------------------------------------------------- fusion en base (f)


def test_fusion_de_deux_traces(db):
    a = db.create_track("Aller", points=[Point(48.1, 1.1), Point(48.2, 1.2)])
    b = db.create_track("Retour", points=[Point(48.3, 1.3), Point(48.4, 1.4)])

    fusion = db.merge_tracks(a, b)

    track = db.get_track(fusion, with_points=True)
    assert track.name == "Aller + Retour"
    assert [p.as_tuple() for p in track.points] == [
        (48.1, 1.1), (48.2, 1.2), (48.3, 1.3), (48.4, 1.4),
    ]


def test_la_fusion_respecte_l_ordre_demande(db):
    a = db.create_track("Aller", points=[Point(48.1, 1.1), Point(48.2, 1.2)])
    b = db.create_track("Retour", points=[Point(48.3, 1.3), Point(48.4, 1.4)])

    fusion = db.merge_tracks(b, a)

    assert [p.as_tuple() for p in db.get_points(fusion)][0] == (48.3, 1.3)


def test_la_fusion_supprime_les_traces_d_origine(db):
    a = db.create_track("Aller", points=[Point(48.1, 1.1), Point(48.2, 1.2)])
    b = db.create_track("Retour", points=[Point(48.3, 1.3), Point(48.4, 1.4)])

    db.merge_tracks(a, b)

    assert db.get_track(a) is None
    assert db.get_track(b) is None


def test_fusion_conservant_les_originaux(db):
    a = db.create_track("Aller", points=[Point(48.1, 1.1), Point(48.2, 1.2)])
    b = db.create_track("Retour", points=[Point(48.3, 1.3), Point(48.4, 1.4)])

    db.merge_tracks(a, b, keep_sources=True)

    assert db.get_track(a) is not None
    assert db.get_track(b) is not None
    assert len(db.list_tracks(None)) == 3


def test_fusion_dans_le_dossier_de_la_premiere(db):
    folder = db.create_folder("Alpes")
    a = db.create_track("Aller", folder_id=folder,
                        points=[Point(48.1, 1.1), Point(48.2, 1.2)])
    b = db.create_track("Retour", points=[Point(48.3, 1.3), Point(48.4, 1.4)])

    fusion = db.merge_tracks(a, b)

    assert db.get_track(fusion).folder_id == folder


def test_fusion_avec_nom_choisi(db):
    a = db.create_track("Aller", points=[Point(48.1, 1.1), Point(48.2, 1.2)])
    b = db.create_track("Retour", points=[Point(48.3, 1.3), Point(48.4, 1.4)])

    fusion = db.merge_tracks(a, b, name="Boucle complète")

    assert db.get_track(fusion).name == "Boucle complète"


def test_fusion_d_une_trace_avec_elle_meme_refusee(db, sample_points):
    a = db.create_track("Trace", points=sample_points)

    with pytest.raises(ValueError, match="elle-même"):
        db.merge_tracks(a, a)
    assert db.get_track(a) is not None


def test_fusion_avec_une_trace_inexistante(db, sample_points):
    a = db.create_track("Trace", points=sample_points)

    with pytest.raises(NotFoundError):
        db.merge_tracks(a, 999)
    assert db.get_track(a) is not None
