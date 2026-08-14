"""Tests de l'export GPX (Jalon 4)."""

from __future__ import annotations

import xml.etree.ElementTree as ET

import pytest

from geocairn import APP_NAME
from geocairn.gpx import GPX_NS, build_gpx, safe_filename, write_gpx
from geocairn.models import Point

NS = {"gpx": GPX_NS}


@pytest.fixture
def points() -> list[Point]:
    return [
        Point(48.9300, 1.4400, 70.0),
        Point(48.9310, 1.4420, 72.5),
        Point(48.9325, 1.4415, None),
    ]


# ------------------------------------------------------------------ structure


def test_racine_gpx_conforme(points):
    root = build_gpx("Rallye V1", points).getroot()

    assert root.tag == f"{{{GPX_NS}}}gpx"
    assert root.get("version") == "1.1"
    assert APP_NAME in root.get("creator")


def test_nom_de_la_trace_present_deux_fois(points):
    """Le nom figure dans les métadonnées et dans la piste elle-même."""
    root = build_gpx("Rallye V1", points).getroot()

    assert root.find("gpx:metadata/gpx:name", NS).text == "Rallye V1"
    assert root.find("gpx:trk/gpx:name", NS).text == "Rallye V1"


def test_tous_les_points_sont_exportes(points):
    root = build_gpx("Trace", points).getroot()
    trkpts = root.findall("gpx:trk/gpx:trkseg/gpx:trkpt", NS)

    assert len(trkpts) == 3
    assert float(trkpts[0].get("lat")) == pytest.approx(48.9300)
    assert float(trkpts[0].get("lon")) == pytest.approx(1.4400)


def test_ordre_des_points_conserve(points):
    root = build_gpx("Trace", points).getroot()
    lats = [
        float(p.get("lat"))
        for p in root.findall("gpx:trk/gpx:trkseg/gpx:trkpt", NS)
    ]
    assert lats == [pytest.approx(p.lat) for p in points]


def test_altitude_optionnelle(points):
    root = build_gpx("Trace", points).getroot()
    trkpts = root.findall("gpx:trk/gpx:trkseg/gpx:trkpt", NS)

    assert float(trkpts[0].find("gpx:ele", NS).text) == pytest.approx(70.0)
    assert trkpts[2].find("gpx:ele", NS) is None  # altitude absente


def test_horodatage_exporte_si_present():
    points = [Point(48.93, 1.44, 70.0, "2026-08-10T09:15:00Z"), Point(48.94, 1.45)]
    root = build_gpx("Trace", points).getroot()
    trkpts = root.findall("gpx:trk/gpx:trkseg/gpx:trkpt", NS)

    assert trkpts[0].find("gpx:time", NS).text == "2026-08-10T09:15:00Z"
    assert trkpts[1].find("gpx:time", NS) is None


def test_rectangle_englobant_dans_les_metadonnees(points):
    box = build_gpx("Trace", points).getroot().find("gpx:metadata/gpx:bounds", NS)

    assert float(box.get("minlat")) == pytest.approx(48.9300)
    assert float(box.get("maxlat")) == pytest.approx(48.9325)
    assert float(box.get("minlon")) == pytest.approx(1.4400)
    assert float(box.get("maxlon")) == pytest.approx(1.4420)


def test_description_optionnelle(points):
    sans = build_gpx("Trace", points).getroot()
    assert sans.find("gpx:metadata/gpx:desc", NS) is None

    avec = build_gpx("Trace", points, "Boucle familiale").getroot()
    assert avec.find("gpx:metadata/gpx:desc", NS).text == "Boucle familiale"


def test_trace_vide_reste_un_gpx_valide():
    root = build_gpx("Vide", []).getroot()
    assert root.findall("gpx:trk/gpx:trkseg/gpx:trkpt", NS) == []
    assert root.find("gpx:metadata/gpx:bounds", NS) is None


# --------------------------------------------------------------- écriture


def test_ecriture_puis_relecture(tmp_path, points):
    """Le fichier écrit doit être relisible par un parseur XML standard."""
    path = write_gpx(tmp_path / "sortie.gpx", "Rallye V1", points)

    assert path.exists()
    relu = ET.parse(path).getroot()
    assert relu.tag == f"{{{GPX_NS}}}gpx"
    assert relu.find("gpx:trk/gpx:name", NS).text == "Rallye V1"
    assert len(relu.findall("gpx:trk/gpx:trkseg/gpx:trkpt", NS)) == 3


def test_declaration_xml_et_encodage(tmp_path, points):
    path = write_gpx(tmp_path / "sortie.gpx", "Trace", points)
    debut = path.read_text(encoding="utf-8")[:60]

    assert debut.startswith("<?xml version=")
    assert "UTF-8" in debut


def test_accents_preserves(tmp_path):
    path = write_gpx(tmp_path / "s.gpx", "Forêt de Rambouillet — été", [
        Point(48.6, 1.8), Point(48.7, 1.9)
    ])
    relu = ET.parse(path).getroot()
    assert relu.find("gpx:trk/gpx:name", NS).text == "Forêt de Rambouillet — été"


def test_creation_du_dossier_parent(tmp_path, points):
    path = write_gpx(tmp_path / "sous" / "dossier" / "s.gpx", "Trace", points)
    assert path.exists()


# --------------------------------------------------------- noms de fichiers


def test_nom_de_fichier_simple():
    assert safe_filename("Rallye V1") == "Rallye V1.gpx"


def test_caracteres_interdits_remplaces():
    assert safe_filename('Trace: 20/25 km ?') == "Trace_ 20_25 km _.gpx"
    assert safe_filename(r"a\b*c|d") == "a_b_c_d.gpx"


def test_nom_vide_ou_blanc():
    assert safe_filename("") == "trace.gpx"
    assert safe_filename("   ") == "trace.gpx"
    assert safe_filename("...") == "trace.gpx"
