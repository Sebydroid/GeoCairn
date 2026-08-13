"""Lecture et écriture de traces au format GPX."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from math import isfinite
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


#: Altitudes possibles à l'écriture d'un fichier. Une trace peut en porter deux
#: — celle du fichier d'origine et celle calculée par l'IGN — mais le format GPX
#: n'a qu'une balise `<ele>` : il faut choisir laquelle sortir. Les valeurs
#: reprennent les noms des champs d'un point, et celles du profil.
ELE_FICHIER = "ele"
ELE_IGN = "ele_service"
#: Celle du fichier d'origine, et à défaut celle de l'IGN.
ELE_AUTO = "auto"

#: Libellés présentés à l'utilisateur au moment de l'export.
LIBELLES_ELEVATION = {
    ELE_FICHIER: "Altitude d'origine de la trace",
    ELE_IGN: "Altitude calculée par l'IGN",
}


def altitude_de(point: Point, source: str = ELE_AUTO) -> float | None:
    """Altitude d'un point selon l'origine demandée."""
    if source == ELE_FICHIER:
        return point.ele
    if source == ELE_IGN:
        return point.ele_service
    return point.ele if point.ele is not None else point.ele_service


def altitudes_disponibles(points: Sequence[Point]) -> list[str]:
    """Origines d'altitude réellement présentes dans une trace."""
    return [
        source
        for source in (ELE_FICHIER, ELE_IGN)
        if any(altitude_de(p, source) is not None for p in points)
    ]


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
    name: str,
    points: Sequence[Point],
    description: str = "",
    elevation: str = ELE_AUTO,
) -> ET.ElementTree:
    """Construit l'arbre XML GPX d'une trace.

    `elevation` désigne l'altitude à écrire : celle du fichier d'origine, celle
    de l'IGN, ou la première des deux qui existe.
    """
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
        # Le format ne prévoit qu'une altitude. Sans ce choix, une trace
        # dessinée à la main ressortait sans la moindre altitude, alors qu'on
        # venait de la lui faire calculer.
        altitude = altitude_de(point, elevation)
        if altitude is not None:
            ET.SubElement(trkpt, f"{{{GPX_NS}}}ele").text = f"{altitude:.6f}"
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
    elevation: str = ELE_AUTO,
) -> Path:
    """Écrit la trace dans un fichier GPX. Retourne le chemin écrit."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tree = build_gpx(name, points, description, elevation)
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
    #: Points écartés du fichier : coordonnées absentes ou aberrantes.
    ignores: int = 0


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


#: Bornes des coordonnées, telles que les fixe le schéma GPX 1.1.
LAT_MAX = 90.0
LON_MAX = 180.0


def coordonnee_valide(lat: float, lon: float) -> bool:
    """Vrai si le couple désigne un point réel du globe.

    Un fichier abîmé peut porter « NaN », « 1e999 » ou une latitude de 195° :
    ces valeurs ne sont pas seulement fausses, elles sont contagieuses. La base
    refuse d'enregistrer un NaN, et le calcul de distance s'interrompt sur un
    infini — au beau milieu d'un signal Qt, ce qui emporte toute l'application,
    à l'import comme à chaque démarrage suivant.
    """
    return (
        isfinite(lat)
        and isfinite(lon)
        and -LAT_MAX <= lat <= LAT_MAX
        and -LON_MAX <= lon <= LON_MAX
    )


def _read_point(element) -> Point | None:
    """Convertit un <trkpt>/<rtept> ; retourne None si les coordonnées manquent.

    Les coordonnées aberrantes sont écartées de la même façon : mieux vaut une
    trace amputée d'un point qu'un logiciel qui ne se lance plus.
    """
    try:
        lat = float(element.get("lat"))
        lon = float(element.get("lon"))
    except (TypeError, ValueError):
        return None

    if not coordonnee_valide(lat, lon):
        return None

    ele_text = _child_text(element, "ele")
    try:
        ele = float(ele_text) if ele_text else None
    except ValueError:
        ele = None

    return Point(lat, lon, ele, _child_text(element, "time") or None)


def _collect_points(container, point_tag: str) -> tuple[list[Point], int]:
    """Points lisibles du conteneur, et nombre de points écartés."""
    points = []
    ignores = 0
    for element in container.iter():
        if _local(element.tag) == point_tag:
            point = _read_point(element)
            if point is None:
                ignores += 1
            else:
                points.append(point)
    return (points, ignores)


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
            points, ignores = _collect_points(element, "trkpt")
        elif tag == "rte":
            points, ignores = _collect_points(element, "rtept")
        else:
            continue
        if not points:
            continue
        tracks.append(
            GpxTrack(
                name=_child_text(element, "name") or path.stem,
                points=points,
                description=_child_text(element, "desc"),
                ignores=ignores,
            )
        )
    return tracks
