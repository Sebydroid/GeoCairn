"""Export de traces au format GPX 1.1 standard."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Sequence

from . import APP_NAME, APP_VERSION
from .geo import bounds
from .models import Point

GPX_NS = "http://www.topografix.com/GPX/1/1"
XSI_NS = "http://www.w3.org/2001/XMLSchema-instance"
SCHEMA_LOCATION = (
    "http://www.topografix.com/GPX/1/1 http://www.topografix.com/GPX/1/1/gpx.xsd"
)

#: Caractères interdits dans un nom de fichier Windows.
_FORBIDDEN = r'[<>:"/\\|?*\x00-\x1f]'


def safe_filename(name: str, extension: str = ".gpx") -> str:
    """Transforme un nom de trace en nom de fichier valide sous Windows."""
    cleaned = re.sub(_FORBIDDEN, "_", name).strip(" .")
    cleaned = re.sub(r"\s+", " ", cleaned)
    if not cleaned:
        cleaned = "trace"
    return cleaned + extension


def build_gpx(
    name: str, points: Sequence[Point], description: str = ""
) -> ET.ElementTree:
    """Construit l'arbre XML GPX d'une trace."""
    ET.register_namespace("", GPX_NS)
    ET.register_namespace("xsi", XSI_NS)

    gpx = ET.Element(
        f"{{{GPX_NS}}}gpx",
        {
            "version": "1.1",
            "creator": f"{APP_NAME} {APP_VERSION}",
            f"{{{XSI_NS}}}schemaLocation": SCHEMA_LOCATION,
        },
    )

    metadata = ET.SubElement(gpx, f"{{{GPX_NS}}}metadata")
    ET.SubElement(metadata, f"{{{GPX_NS}}}name").text = name
    if description:
        ET.SubElement(metadata, f"{{{GPX_NS}}}desc").text = description

    box = bounds(points)
    if box is not None:
        (min_lat, min_lon), (max_lat, max_lon) = box
        ET.SubElement(
            metadata,
            f"{{{GPX_NS}}}bounds",
            {
                "minlat": f"{min_lat:.9f}",
                "minlon": f"{min_lon:.9f}",
                "maxlat": f"{max_lat:.9f}",
                "maxlon": f"{max_lon:.9f}",
            },
        )

    trk = ET.SubElement(gpx, f"{{{GPX_NS}}}trk")
    ET.SubElement(trk, f"{{{GPX_NS}}}name").text = name
    if description:
        ET.SubElement(trk, f"{{{GPX_NS}}}desc").text = description

    trkseg = ET.SubElement(trk, f"{{{GPX_NS}}}trkseg")
    for point in points:
        trkpt = ET.SubElement(
            trkseg,
            f"{{{GPX_NS}}}trkpt",
            {"lat": f"{point.lat:.9f}", "lon": f"{point.lon:.9f}"},
        )
        if point.ele is not None:
            ET.SubElement(trkpt, f"{{{GPX_NS}}}ele").text = f"{point.ele:.6f}"
        if point.time:
            ET.SubElement(trkpt, f"{{{GPX_NS}}}time").text = point.time

    tree = ET.ElementTree(gpx)
    ET.indent(tree, space="    ")
    return tree


def write_gpx(
    path: str | Path,
    name: str,
    points: Sequence[Point],
    description: str = "",
) -> Path:
    """Écrit la trace dans un fichier GPX. Retourne le chemin écrit."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tree = build_gpx(name, points, description)
    tree.write(path, encoding="UTF-8", xml_declaration=True)
    return path
