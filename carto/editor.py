"""Trace « brouillon » maintenue en mémoire pendant l'édition sur la carte.

Cette classe est la source de vérité des points en cours de saisie : la carte
Leaflet n'en est que le reflet. Elle ne dépend ni de Qt ni de la base, ce qui la
rend directement testable.
"""

from __future__ import annotations

from .geo import format_length, total_length
from .models import Point


class DraftTrack:
    """Suite ordonnée de points en cours de saisie."""

    def __init__(self, name: str = "Nouvelle trace") -> None:
        self.name = name
        self._points: list[Point] = []

    # ------------------------------------------------------------------ état

    @property
    def points(self) -> list[Point]:
        """Copie des points : l'appelant ne peut pas modifier l'état interne."""
        return list(self._points)

    def __len__(self) -> int:
        return len(self._points)

    @property
    def is_empty(self) -> bool:
        return not self._points

    @property
    def length_m(self) -> float:
        return total_length(self._points)

    def summary(self) -> str:
        """Résumé affichable dans la barre d'état."""
        if self.is_empty:
            return "Brouillon vide"
        count = len(self._points)
        pluriel = "s" if count > 1 else ""
        return f"Brouillon : {count} point{pluriel} — {format_length(self.length_m)}"

    # --------------------------------------------------------------- édition

    def add_point(self, lat: float, lon: float, ele: float | None = None) -> Point:
        """Ajoute un point à la fin du brouillon."""
        point = Point(lat, lon, ele)
        self._points.append(point)
        return point

    def undo_last(self) -> Point | None:
        """Retire le dernier point ajouté. Retourne le point retiré, ou None."""
        if not self._points:
            return None
        return self._points.pop()

    def clear(self) -> None:
        self._points.clear()

    def set_points(self, points: list[Point]) -> None:
        """Remplace le contenu du brouillon (reprise d'une trace existante)."""
        self._points = list(points)
