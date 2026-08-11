"""Décimation d'une trace : réduire le nombre de points sans la déformer.

Un enregistreur GPS pose un point toutes les secondes ; une sortie de trois
heures en compte des milliers, dont l'écrasante majorité n'apporte rien au
dessin. Les retirer au hasard, ou un sur deux, abîmerait les virages autant que
les lignes droites.

L'algorithme de Ramer-Douglas-Peucker écarte les points qui s'éloignent peu de
la ligne joignant leurs voisins : les longues lignes droites fondent, les
virages restent. Le nombre de points obtenu dépend du seuil de tolérance, qu'on
ajuste par recherche dichotomique pour approcher la quantité demandée — d'où un
résultat approximatif, mais fidèle à la forme.
"""

from __future__ import annotations

from math import cos, radians
from typing import Sequence

from .models import Point

#: Mètres par degré de latitude ; suffisant pour comparer des écarts locaux.
METRES_PAR_DEGRE = 111_320.0

#: Nombre d'essais de la recherche dichotomique sur la tolérance.
ESSAIS = 40


def _projeter(points: Sequence[Point]) -> list[tuple[float, float]]:
    """Coordonnées planes approchées, en mètres, pour comparer des distances.

    Les longitudes sont resserrées selon la latitude moyenne : sans cela, un
    écart en longitude compterait davantage qu'il ne vaut sous nos latitudes.
    """
    if not points:
        return []
    latitude_moyenne = sum(p.lat for p in points) / len(points)
    facteur = cos(radians(latitude_moyenne))
    return [
        (p.lon * facteur * METRES_PAR_DEGRE, p.lat * METRES_PAR_DEGRE)
        for p in points
    ]


def _distance_au_segment(point, debut, fin) -> float:
    """Distance d'un point au segment [debut, fin], en mètres."""
    (px, py), (ax, ay), (bx, by) = point, debut, fin
    dx, dy = bx - ax, by - ay
    if dx == 0 and dy == 0:
        return ((px - ax) ** 2 + (py - ay) ** 2) ** 0.5

    t = ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)
    t = max(0.0, min(1.0, t))
    projx, projy = ax + t * dx, ay + t * dy
    return ((px - projx) ** 2 + (py - projy) ** 2) ** 0.5


def _indices_conserves(plans, debut: int, fin: int, tolerance: float) -> list[int]:
    """Indices à garder entre `debut` et `fin`, extrémités comprises."""
    if fin <= debut + 1:
        return [debut, fin] if fin > debut else [debut]

    pire, ecart = debut, -1.0
    for i in range(debut + 1, fin):
        d = _distance_au_segment(plans[i], plans[debut], plans[fin])
        if d > ecart:
            pire, ecart = i, d

    if ecart <= tolerance:
        return [debut, fin]

    gauche = _indices_conserves(plans, debut, pire, tolerance)
    droite = _indices_conserves(plans, pire, fin, tolerance)
    return gauche[:-1] + droite


def douglas_peucker(points: Sequence[Point], tolerance: float) -> list[Point]:
    """Simplifie une trace en écartant les points à moins de `tolerance` mètres."""
    if len(points) < 3 or tolerance <= 0:
        return list(points)
    plans = _projeter(points)
    gardes = _indices_conserves(plans, 0, len(points) - 1, tolerance)
    return [points[i] for i in gardes]


def simplify_to(points: Sequence[Point], cible: int) -> list[Point]:
    """Réduit la trace à environ `cible` points, en préservant sa forme.

    Le compte obtenu est approximatif : la tolérance qui donnerait exactement
    le nombre demandé n'existe pas toujours. Le résultat n'excède jamais la
    trace d'origine, et conserve toujours le départ et l'arrivée.
    """
    if cible >= len(points) or len(points) < 3:
        return list(points)
    if cible < 2:
        cible = 2

    # Bornes de la recherche : 0 conserve tout, la diagonale supprime tout.
    plans = _projeter(points)
    etendue = max(
        max(x for x, _ in plans) - min(x for x, _ in plans),
        max(y for _, y in plans) - min(y for _, y in plans),
        1.0,
    )
    basse, haute = 0.0, etendue
    meilleur = list(points)

    for _ in range(ESSAIS):
        milieu = (basse + haute) / 2
        essai = douglas_peucker(points, milieu)
        if len(essai) > cible:
            basse = milieu
        else:
            haute = milieu
            meilleur = essai
        if len(essai) == cible:
            return essai

    return meilleur
