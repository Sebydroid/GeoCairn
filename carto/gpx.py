"""Lecture et écriture de traces au format GPX."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
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

#: Noms réservés par Windows aux périphériques. Même suivis d'une extension,
#: ils ne désignent pas un fichier : « CON.gpx » écrit dans la console, et
#: l'export ne laisse aucune trace sur le disque.
_RESERVES = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{n}" for n in range(1, 10)),
    *(f"LPT{n}" for n in range(1, 10)),
}


def safe_filename(name: str, extension: str = ".gpx") -> str:
    """Transforme un nom de trace en nom de fichier valide sous Windows."""
    cleaned = re.sub(_FORBIDDEN, "_", name).strip(" .")
    cleaned = re.sub(r"\s+", " ", cleaned)
    if not cleaned:
        cleaned = "trace"
    if cleaned.upper() in _RESERVES:
        cleaned = f"{cleaned}_"
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


# ---------------------------------------------------------------- lecture


class GpxParseError(ValueError):
    """Le fichier n'est pas un GPX exploitable."""


@dataclass
class GpxTrack:
    """Une trace lue dans un fichier GPX."""

    name: str
    points: list[Point] = field(default_factory=list)
    description: str = ""


def _local(tag: str) -> str:
    """Nom d'un élément sans son espace de noms.

    Indispensable : les fichiers rencontrés déclarent aussi bien GPX/1/0 que
    GPX/1/1, parfois en contradiction avec leur attribut `version`.
    """
    return tag.rsplit("}", 1)[-1]


def _find_child(element, name: str):
    for child in element:
        if _local(child.tag) == name:
            return child
    return None


def _child_text(element, name: str) -> str:
    child = _find_child(element, name)
    return (child.text or "").strip() if child is not None else ""


def _read_point(element) -> Point | None:
    """Convertit un <trkpt>/<rtept> ; retourne None si les coordonnées manquent."""
    try:
        lat = float(element.get("lat"))
        lon = float(element.get("lon"))
    except (TypeError, ValueError):
        return None

    ele_text = _child_text(element, "ele")
    try:
        ele = float(ele_text) if ele_text else None
    except ValueError:
        ele = None

    return Point(lat, lon, ele, _child_text(element, "time") or None)


def _collect_points(container, point_tag: str) -> list[Point]:
    points = []
    for element in container.iter():
        if _local(element.tag) == point_tag:
            point = _read_point(element)
            if point is not None:
                points.append(point)
    return points


def _read_root(path: Path):
    """Ouvre un fichier GPX et retourne sa racine, ou lève GpxParseError."""
    try:
        root = ET.parse(path).getroot()
    except ET.ParseError as exc:
        raise GpxParseError(f"XML illisible dans {path.name} : {exc}") from exc
    except OSError as exc:
        raise GpxParseError(f"Fichier illisible : {exc}") from exc

    if _local(root.tag) != "gpx":
        raise GpxParseError(
            f"{path.name} n'est pas un fichier GPX "
            f"(élément racine « {_local(root.tag)} »)."
        )
    return root


def count_waypoints(path: str | Path) -> int:
    """Nombre de points d'intérêt `<wpt>` du fichier.

    Certains fichiers ne contiennent que cela (relevés de points remarquables,
    sans itinéraire). Carto ne les gère pas encore, mais le savoir permet
    d'expliquer à l'utilisateur pourquoi l'import ne donne rien.
    """
    root = _read_root(Path(path))
    return sum(1 for element in root if _local(element.tag) == "wpt")


def parse_gpx(path: str | Path) -> list[GpxTrack]:
    """Lit un fichier GPX et retourne ses traces.

    Chaque `<trk>` donne une trace (ses segments sont mis bout à bout) ; les
    `<rte>` sont également reprises. Les traces sans point sont ignorées.
    """
    path = Path(path)
    root = _read_root(path)

    tracks: list[GpxTrack] = []
    for element in root:
        tag = _local(element.tag)
        if tag == "trk":
            points = _collect_points(element, "trkpt")
        elif tag == "rte":
            points = _collect_points(element, "rtept")
        else:
            continue
        if not points:
            continue
        tracks.append(
            GpxTrack(
                name=_child_text(element, "name") or path.stem,
                points=points,
                description=_child_text(element, "desc"),
            )
        )
    return tracks
