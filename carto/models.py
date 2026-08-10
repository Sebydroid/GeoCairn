"""Structures de données du domaine."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Point:
    """Un point GPS d'une trace."""

    lat: float
    lon: float
    ele: float | None = None
    time: str | None = None

    def as_tuple(self) -> tuple[float, float]:
        return (self.lat, self.lon)


@dataclass
class Folder:
    """Un dossier de l'arborescence."""

    id: int
    name: str
    parent_id: int | None = None


@dataclass
class Track:
    """Une trace (métadonnées ; les points sont chargés à la demande)."""

    id: int
    name: str
    folder_id: int | None = None
    color: str = "#e6194b"
    description: str = ""
    is_loop: bool = False
    point_count: int = 0
    points: list[Point] = field(default_factory=list)
