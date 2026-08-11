"""Calculs géographiques sur les traces."""

from __future__ import annotations

from datetime import datetime
from math import asin, cos, radians, sin, sqrt
from typing import Sequence

from .models import Point

#: Rayon moyen de la Terre en mètres (IUGG).
EARTH_RADIUS_M = 6371008.8


def distance(a: Point, b: Point) -> float:
    """Distance orthodromique entre deux points, en mètres (formule de haversine)."""
    lat1, lon1 = radians(a.lat), radians(a.lon)
    lat2, lon2 = radians(b.lat), radians(b.lon)
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    h = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    return 2 * EARTH_RADIUS_M * asin(sqrt(h))


def total_length(points: Sequence[Point]) -> float:
    """Longueur cumulée d'une trace, en mètres."""
    return sum(
        distance(points[i], points[i + 1]) for i in range(len(points) - 1)
    )


def bounds(points: Sequence[Point]) -> tuple[tuple[float, float], tuple[float, float]] | None:
    """Rectangle englobant ((sud, ouest), (nord, est)), ou None si vide."""
    if not points:
        return None
    lats = [p.lat for p in points]
    lons = [p.lon for p in points]
    return ((min(lats), min(lons)), (max(lats), max(lons)))


def cumulative_distances(points: Sequence[Point]) -> list[float]:
    """Distance parcourue depuis le départ, point par point, en mètres."""
    distances = [0.0]
    for i in range(len(points) - 1):
        distances.append(distances[-1] + distance(points[i], points[i + 1]))
    return distances if points else []


def _parse_time(valeur: str | None):
    """Horodatage GPX vers datetime ; None si absent ou illisible."""
    if not valeur:
        return None
    texte = valeur.strip().replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(texte)
    except ValueError:
        return None


def speeds(points: Sequence[Point]) -> list[float | None]:
    """Vitesse en km/h à chaque point, calculée sur le segment précédent.

    Retourne None là où les horodatages manquent ou n'avancent pas : une trace
    dessinée à la main n'a aucune vitesse.
    """
    if not points:
        return []

    resultats: list[float | None] = [None]
    for i in range(1, len(points)):
        avant = _parse_time(points[i - 1].time)
        apres = _parse_time(points[i].time)
        if avant is None or apres is None:
            resultats.append(None)
            continue
        secondes = (apres - avant).total_seconds()
        if secondes <= 0:
            resultats.append(None)
            continue
        resultats.append(distance(points[i - 1], points[i]) / secondes * 3.6)

    # Le premier point hérite du second : sans cela le profil commencerait
    # toujours par un trou.
    if len(resultats) > 1:
        resultats[0] = resultats[1]
    return resultats


def has_times(points: Sequence[Point]) -> bool:
    """Vrai si au moins deux points portent un horodatage exploitable."""
    horodates = sum(1 for p in points if _parse_time(p.time) is not None)
    return horodates >= 2


def format_length(metres: float) -> str:
    """Longueur lisible : « 850 m » ou « 12,34 km »."""
    if metres < 1000:
        return f"{metres:.0f} m"
    return f"{metres / 1000:.2f} km".replace(".", ",")
