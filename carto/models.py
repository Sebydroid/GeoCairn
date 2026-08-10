"""Structures de données du domaine."""

from __future__ import annotations

from dataclasses import dataclass, field


#: Couleur des traces enregistrées (bleu), distincte du brouillon en cours de
#: saisie (rouge) : les deux peuvent être affichés en même temps.
DEFAULT_TRACK_COLOR = "#1f5fbf"

#: Opacité par défaut du tracé sur la carte (1.0 = opaque).
DEFAULT_TRACK_OPACITY = 0.9


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
    color: str = DEFAULT_TRACK_COLOR
    opacity: float = DEFAULT_TRACK_OPACITY
    description: str = ""
    is_loop: bool = False
    #: Affichée sur la carte ; conservé d'un lancement à l'autre.
    visible: bool = False
    point_count: int = 0
    points: list[Point] = field(default_factory=list)
