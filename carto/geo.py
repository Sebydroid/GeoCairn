"""Calculs géographiques sur les traces."""

from __future__ import annotations

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


def format_length(metres: float) -> str:
    """Longueur lisible : « 850 m » ou « 12,34 km »."""
    if metres < 1000:
        return f"{metres:.0f} m"
    return f"{metres / 1000:.2f} km".replace(".", ",")
