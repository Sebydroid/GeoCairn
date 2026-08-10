"""Tests de la lecture des fichiers GPX (Jalon 5)."""

from __future__ import annotations

from pathlib import Path

import pytest

from carto.gpx import GpxParseError, count_waypoints, parse_gpx, write_gpx
from carto.models import Point

# Fichier réel produit par PhotoExploreur : il annonce version="1.1" mais
# déclare l'espace de noms GPX/1/0. La lecture doit rester tolérante.
GPX_NS_INCOHERENT = """<?xml version="1.0" encoding="UTF-8"?>
<gpx version="1.1" creator="PhotoExploreur 3D 1.00"
     xmlns="http://www.topografix.com/GPX/1/0">
    <metadata><time>2016-02-06T22:29:04Z</time></metadata>
    <trk>
        <name>Rallye V1</name>
        <trkseg>
            <trkpt lat="48.939354279" lon="1.439182759"><ele>73.975845</ele></trkpt>
            <trkpt lat="48.938849460" lon="1.437042801"><ele>67.675850</ele></trkpt>
            <trkpt lat="48.938757218" lon="1.436728920"><ele>66.750847</ele></trkpt>
        </trkseg>
    </trk>
</gpx>
"""

GPX_DEUX_TRACES = """<?xml version="1.0" encoding="UTF-8"?>
<gpx version="1.1" creator="test" xmlns="http://www.topografix.com/GPX/1/1">
    <trk><name>Aller</name><trkseg>
        <trkpt lat="48.10" lon="1.10"/><trkpt lat="48.11" lon="1.11"/>
    </trkseg></trk>
    <trk><name>Retour</name><trkseg>
        <trkpt lat="48.20" lon="1.20"/><trkpt lat="48.21" lon="1.21"/>
    </trkseg></trk>
</gpx>
"""

GPX_SEGMENTS_MULTIPLES = """<?xml version="1.0" encoding="UTF-8"?>
<gpx version="1.1" creator="test" xmlns="http://www.topografix.com/GPX/1/1">
    <trk><name>Coupée</name>
        <trkseg><trkpt lat="48.10" lon="1.10"/><trkpt lat="48.11" lon="1.11"/></trkseg>
        <trkseg><trkpt lat="48.12" lon="1.12"/></trkseg>
    </trk>
</gpx>
"""

GPX_ROUTE = """<?xml version="1.0" encoding="UTF-8"?>
<gpx version="1.1" creator="test" xmlns="http://www.topografix.com/GPX/1/1">
    <rte><name>Itinéraire</name>
        <rtept lat="48.30" lon="1.30"/><rtept lat="48.31" lon="1.31"/>
    </rte>
</gpx>
"""

GPX_SANS_TRACE = """<?xml version="1.0" encoding="UTF-8"?>
<gpx version="1.1" creator="test" xmlns="http://www.topografix.com/GPX/1/1">
    <wpt lat="48.5" lon="1.5"><name>Un point isolé</name></wpt>
</gpx>
"""


def ecrire(tmp_path: Path, contenu: str, nom: str = "trace.gpx") -> Path:
    chemin = tmp_path / nom
    chemin.write_text(contenu, encoding="utf-8")
    return chemin


# ------------------------------------------------------------------ lecture


def test_lecture_d_une_trace_simple(tmp_path):
    traces = parse_gpx(ecrire(tmp_path, GPX_NS_INCOHERENT))

    assert len(traces) == 1
    assert traces[0].name == "Rallye V1"
    assert len(traces[0].points) == 3
    assert traces[0].points[0].lat == pytest.approx(48.939354279)
    assert traces[0].points[0].lon == pytest.approx(1.439182759)
    assert traces[0].points[0].ele == pytest.approx(73.975845)


def test_espace_de_noms_gpx_1_0_accepte(tmp_path):
    """Régression : les vieux fichiers déclarent GPX/1/0, pas GPX/1/1."""
    assert parse_gpx(ecrire(tmp_path, GPX_NS_INCOHERENT))


def test_plusieurs_traces_dans_un_fichier(tmp_path):
    traces = parse_gpx(ecrire(tmp_path, GPX_DEUX_TRACES))

    assert [t.name for t in traces] == ["Aller", "Retour"]
    assert traces[0].points[0].lat == pytest.approx(48.10)
    assert traces[1].points[0].lat == pytest.approx(48.20)


def test_segments_mis_bout_a_bout(tmp_path):
    traces = parse_gpx(ecrire(tmp_path, GPX_SEGMENTS_MULTIPLES))

    assert len(traces) == 1
    assert len(traces[0].points) == 3


def test_lecture_d_une_route(tmp_path):
    traces = parse_gpx(ecrire(tmp_path, GPX_ROUTE))

    assert len(traces) == 1
    assert traces[0].name == "Itinéraire"
    assert len(traces[0].points) == 2


def test_fichier_sans_trace(tmp_path):
    assert parse_gpx(ecrire(tmp_path, GPX_SANS_TRACE)) == []


def test_nom_par_defaut_tire_du_fichier(tmp_path):
    contenu = GPX_NS_INCOHERENT.replace("<name>Rallye V1</name>", "")
    traces = parse_gpx(ecrire(tmp_path, contenu, "Bosc Roger 38 km.gpx"))

    assert traces[0].name == "Bosc Roger 38 km"


def test_altitude_et_horodatage_optionnels(tmp_path):
    contenu = """<?xml version="1.0"?>
    <gpx version="1.1" xmlns="http://www.topografix.com/GPX/1/1"><trk><trkseg>
        <trkpt lat="48.1" lon="1.1"><ele>70</ele><time>2026-08-10T09:00:00Z</time></trkpt>
        <trkpt lat="48.2" lon="1.2"/>
    </trkseg></trk></gpx>"""
    points = parse_gpx(ecrire(tmp_path, contenu))[0].points

    assert points[0].ele == pytest.approx(70.0)
    assert points[0].time == "2026-08-10T09:00:00Z"
    assert points[1].ele is None
    assert points[1].time is None


def test_points_sans_coordonnees_ignores(tmp_path):
    contenu = """<?xml version="1.0"?>
    <gpx version="1.1" xmlns="http://www.topografix.com/GPX/1/1"><trk><trkseg>
        <trkpt lat="48.1" lon="1.1"/>
        <trkpt lon="1.2"/>
        <trkpt lat="abc" lon="1.3"/>
        <trkpt lat="48.4" lon="1.4"/>
    </trkseg></trk></gpx>"""
    points = parse_gpx(ecrire(tmp_path, contenu))[0].points

    assert [p.lat for p in points] == [pytest.approx(48.1), pytest.approx(48.4)]


# ------------------------------------------------------------------ erreurs


def test_xml_invalide(tmp_path):
    with pytest.raises(GpxParseError, match="XML illisible"):
        parse_gpx(ecrire(tmp_path, "<gpx><trk>pas fermé"))


def test_fichier_qui_n_est_pas_du_gpx(tmp_path):
    with pytest.raises(GpxParseError, match="n'est pas un fichier GPX"):
        parse_gpx(ecrire(tmp_path, "<html><body>bonjour</body></html>"))


def test_fichier_absent(tmp_path):
    with pytest.raises(GpxParseError):
        parse_gpx(tmp_path / "inexistant.gpx")


# --------------------------------------------------------- aller-retour


def test_export_puis_import_conserve_la_trace(tmp_path):
    """Ce que Carto écrit, Carto doit savoir le relire à l'identique."""
    points = [
        Point(48.9300, 1.4400, 70.0),
        Point(48.9310, 1.4420, 72.5),
        Point(48.9325, 1.4415, None),
    ]
    chemin = write_gpx(tmp_path / "aller-retour.gpx", "Boucle du lac", points)

    traces = parse_gpx(chemin)

    assert len(traces) == 1
    assert traces[0].name == "Boucle du lac"
    relus = traces[0].points
    assert len(relus) == 3
    for original, relu in zip(points, relus):
        assert relu.lat == pytest.approx(original.lat)
        assert relu.lon == pytest.approx(original.lon)
        if original.ele is None:
            assert relu.ele is None
        else:
            assert relu.ele == pytest.approx(original.ele)


def test_aller_retour_avec_description(tmp_path):
    chemin = write_gpx(
        tmp_path / "d.gpx", "Trace", [Point(48.1, 1.1), Point(48.2, 1.2)],
        description="Boucle familiale",
    )
    assert parse_gpx(chemin)[0].description == "Boucle familiale"


# -------------------------------------------- fichiers d'exemple du projet

EXEMPLES = Path(__file__).resolve().parent.parent / "GPX exemples"


@pytest.mark.skipif(not EXEMPLES.is_dir(), reason="dossier d'exemples absent")
def test_tous_les_gpx_d_exemple_se_lisent_sans_erreur():
    """Les fichiers réels fournis avec le projet doivent tous se parser."""
    fichiers = sorted(EXEMPLES.glob("*.gpx"))
    assert fichiers, "aucun fichier d'exemple trouvé"

    for fichier in fichiers:
        for trace in parse_gpx(fichier):
            assert trace.points, f"{fichier.name} : trace « {trace.name} » vide"
            assert all(-90 <= p.lat <= 90 for p in trace.points)
            assert all(-180 <= p.lon <= 180 for p in trace.points)


@pytest.mark.skipif(not EXEMPLES.is_dir(), reason="dossier d'exemples absent")
def test_les_parcours_d_exemple_contiennent_bien_des_traces():
    for fichier in sorted(EXEMPLES.glob("Parcours*.gpx")):
        traces = parse_gpx(fichier)
        assert traces, f"{fichier.name} : aucune trace lue"
        assert len(traces[0].points) > 10


@pytest.mark.skipif(
    not (EXEMPLES / "Questions.gpx").is_file(), reason="exemple absent"
)
def test_fichier_de_points_d_interet_reconnu_comme_tel():
    """« Questions.gpx » ne contient que des <wpt> : aucune trace à importer.

    Le cas est légitime (relevé de points remarquables) ; l'import doit
    l'expliquer plutôt que d'échouer en silence.
    """
    fichier = EXEMPLES / "Questions.gpx"

    assert parse_gpx(fichier) == []
    assert count_waypoints(fichier) > 0


def test_comptage_des_points_d_interet(tmp_path):
    assert count_waypoints(ecrire(tmp_path, GPX_SANS_TRACE)) == 1
    assert count_waypoints(ecrire(tmp_path, GPX_DEUX_TRACES)) == 0
