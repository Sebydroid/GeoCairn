"""Trace « brouillon » maintenue en mémoire pendant l'édition sur la carte.

Cette classe est la source de vérité des points en cours de saisie : la carte
Leaflet n'en est que le reflet. Elle ne dépend ni de Qt ni de la base, ce qui la
rend directement testable.

Un brouillon porte soit une trace neuve (`track_id` à None), soit une trace
enregistrée reprise pour modification (`track_id` renseigné).
"""

from __future__ import annotations

from typing import Iterable, Sequence

from .geo import format_length, total_length
from .models import Point, Track


class DraftTrack:
    """Suite ordonnée de points en cours de saisie ou de modification."""

    def __init__(self, name: str = "Nouvelle trace", track_id: int | None = None) -> None:
        self.name = name
        self.track_id = track_id
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
    def is_existing(self) -> bool:
        """Vrai si le brouillon reprend une trace déjà enregistrée."""
        return self.track_id is not None

    @property
    def is_loop(self) -> bool:
        """Vrai si le premier et le dernier point coïncident."""
        return (
            len(self._points) >= 3
            and self._points[0].as_tuple() == self._points[-1].as_tuple()
        )

    @property
    def length_m(self) -> float:
        return total_length(self._points)

    def summary(self) -> str:
        """Résumé affichable dans la barre d'état."""
        if self.is_empty:
            return "Brouillon vide"
        count = len(self._points)
        pluriel = "s" if count > 1 else ""
        detail = f"{count} point{pluriel} — {format_length(self.length_m)}"
        if self.is_existing:
            return f"Modification de « {self.name} » : {detail}"
        return f"Brouillon : {detail}"

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

    def insert_point(
        self, index: int, lat: float, lon: float, ele: float | None = None
    ) -> Point | None:
        """Insère un point à la position `index` (clic sur un segment).

        Retourne None si la position est hors du tracé.
        """
        if not 0 <= index <= len(self._points):
            return None
        point = Point(lat, lon, ele)
        self._points.insert(index, point)
        return point

    def move_point(self, index: int, lat: float, lon: float) -> bool:
        """Repositionne un point existant. Altitude et horodatage sont conservés."""
        if not 0 <= index < len(self._points):
            return False
        ancien = self._points[index]
        self._points[index] = Point(lat, lon, ancien.ele, ancien.time)
        return True

    def remove_point(self, index: int) -> Point | None:
        """Supprime un point précis. Retourne le point supprimé, ou None."""
        if not 0 <= index < len(self._points):
            return None
        return self._points.pop(index)

    def remove_points(self, indexes: Iterable[int]) -> int:
        """Supprime plusieurs points d'un coup. Retourne le nombre supprimé.

        Les indices hors bornes sont ignorés ; les doublons ne comptent qu'une
        fois. La suppression part de la fin pour que les indices restent
        valides pendant l'opération.
        """
        valides = sorted(
            {i for i in indexes if 0 <= i < len(self._points)}, reverse=True
        )
        for index in valides:
            self._points.pop(index)
        return len(valides)

    def close_loop(self) -> bool:
        """Ferme la trace en boucle en ramenant le tracé à son point de départ.

        Retourne False si la trace compte moins de trois points ou si la boucle
        est déjà fermée.
        """
        if len(self._points) < 3 or self.is_loop:
            return False
        self._points.append(self._points[0])
        return True

    def split_at(self, index: int) -> tuple[list[Point], list[Point]] | None:
        """Découpe le tracé en deux au point `index`, qui appartient aux deux.

        Retourne None si le découpage laisserait une moitié de moins de deux
        points.
        """
        if not 1 <= index <= len(self._points) - 2:
            return None
        return (self._points[: index + 1], self._points[index:])

    def clear(self) -> None:
        """Vide les points, sans oublier la trace d'origine."""
        self._points.clear()

    def reset(self, name: str = "Nouvelle trace") -> None:
        """Repart d'un brouillon neuf, détaché de toute trace enregistrée."""
        self._points.clear()
        self.track_id = None
        self.name = name

    def set_points(self, points: Sequence[Point]) -> None:
        """Remplace le contenu du brouillon."""
        self._points = list(points)

    def load_track(self, track: Track) -> None:
        """Reprend une trace enregistrée pour la modifier."""
        self.track_id = track.id
        self.name = track.name
        self._points = list(track.points)
