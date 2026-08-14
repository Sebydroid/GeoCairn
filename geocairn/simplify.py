"""Décimation d'une trace : réduire le nombre de points sans la déformer.

Un enregistreur GPS pose un point toutes les secondes ; une sortie de trois
heures en compte des milliers, dont l'écrasante majorité n'apporte rien au
dessin. Les retirer au hasard, ou un sur deux, abîmerait les virages autant que
les lignes droites.

Le principe commun aux deux méthodes réunies ici : donner à chaque point un
« poids », l'importance qu'il a dans le dessin. Ramener la trace à mille points,
c'est alors garder les mille plus lourds — exactement, et en une seule passe.

Deux façons de peser un point, selon ce qu'on demande :

— Ramer-Douglas-Peucker mesure l'écart, en mètres, entre le point et la ligne
  joignant ses voisins retenus. C'est la référence quand on raisonne en
  tolérance (« lisser à moins de deux mètres »), mais son découpage dégénère
  sur une longue ligne droite relevée au GPS : le coût y devient le carré du
  nombre de points, soit plusieurs minutes pour dix mille.

— Visvalingam-Whyatt mesure l'aire du triangle formé avec les voisins et retire
  les points les plus plats, un tas maintenant l'ordre. Le coût est garanti,
  quelle que soit la forme du tracé : c'est ce qui sert à ramener une trace à un
  nombre de points voulu.
"""

from __future__ import annotations

from heapq import heapify, heappop, heappush
from math import cos, inf, radians
from typing import Sequence

from .models import Point

#: Mètres par degré de latitude ; suffisant pour comparer des écarts locaux.
METRES_PAR_DEGRE = 111_320.0


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


def _poids(plans) -> list[float]:
    """Écart auquel chaque point disparaîtrait, en mètres.

    C'est le découpage de Douglas-Peucker mené jusqu'au bout, en notant au
    passage l'écart qui a justifié chaque point. Les extrémités valent l'infini :
    elles ne disparaissent jamais.

    Deux précautions :
    — la pile est tenue à la main plutôt que par la récursion, qu'un tracé de
      plusieurs milliers de points pourrait faire déborder ;
    — le poids d'un point ne dépasse jamais celui du point qui l'a fait
      apparaître, sans quoi un point pourrait « survivre » à son parent et le
      classement ne correspondrait plus au découpage.
    """
    n = len(plans)
    poids = [0.0] * n
    poids[0] = poids[n - 1] = inf

    pile = [(0, n - 1, inf)]
    while pile:
        debut, fin, plafond = pile.pop()
        if fin <= debut + 1:
            continue

        pire, ecart = -1, -1.0
        for i in range(debut + 1, fin):
            d = _distance_au_segment(plans[i], plans[debut], plans[fin])
            if d > ecart:
                pire, ecart = i, d
        if pire < 0:
            continue

        valeur = ecart if ecart < plafond else plafond
        poids[pire] = valeur
        pile.append((debut, pire, valeur))
        pile.append((pire, fin, valeur))
    return poids


def douglas_peucker(points: Sequence[Point], tolerance: float) -> list[Point]:
    """Simplifie une trace en écartant les points à moins de `tolerance` mètres."""
    if len(points) < 3 or tolerance <= 0:
        return list(points)
    return [
        point
        for point, poids in zip(points, _poids(_projeter(points)))
        if poids > tolerance
    ]


def _aire(plans, precedent: int, milieu: int, suivant: int) -> float:
    """Aire du triangle formé par un point et ses deux voisins, en m².

    Plus elle est petite, moins le point apporte au dessin : un point aligné
    avec ses voisins donne une aire nulle.
    """
    (ax, ay), (bx, by), (cx, cy) = plans[precedent], plans[milieu], plans[suivant]
    return abs((bx - ax) * (cy - ay) - (cx - ax) * (by - ay)) / 2


def _poids_par_aire(plans) -> list[float]:
    """Aire à laquelle chaque point disparaîtrait (Visvalingam-Whyatt).

    On retire à chaque tour le point le plus plat, puis on recalcule ses deux
    voisins. Le tas garantit un coût en n·log(n) quelle que soit la forme du
    tracé, là où le découpage de Douglas-Peucker s'emballe : sur une trace
    quasi rectiligne mais bruitée — une longue ligne droite relevée au GPS —
    il dégénère et demandait plusieurs minutes pour dix mille points.

    Comme pour le découpage, le poids ne décroît jamais : un point retiré après
    un autre ne peut pas être jugé moins utile que lui, sans quoi les
    simplifications successives ne s'emboîteraient plus.
    """
    n = len(plans)
    poids = [0.0] * n
    poids[0] = poids[n - 1] = inf

    precedent = list(range(-1, n - 1))
    suivant = list(range(1, n + 1))
    version = [0] * n

    tas = [(_aire(plans, i - 1, i, i + 1), i, 0) for i in range(1, n - 1)]
    heapify(tas)

    plancher = 0.0
    while tas:
        aire, i, marque = heappop(tas)
        if marque != version[i]:
            continue   # entrée périmée : le point a changé de voisins depuis

        plancher = max(plancher, aire)
        poids[i] = plancher

        avant, apres = precedent[i], suivant[i]
        suivant[avant] = apres
        precedent[apres] = avant
        for voisin in (avant, apres):
            if 0 < voisin < n - 1:
                version[voisin] += 1
                heappush(
                    tas,
                    (
                        _aire(plans, precedent[voisin], voisin, suivant[voisin]),
                        voisin,
                        version[voisin],
                    ),
                )
    return poids


def simplify_to(points: Sequence[Point], cible: int) -> list[Point]:
    """Réduit la trace à `cible` points, en préservant sa forme.

    Le départ et l'arrivée sont toujours conservés, ainsi que l'ordre. Le
    résultat n'excède jamais la trace d'origine.
    """
    if cible >= len(points) or len(points) < 3:
        return list(points)
    if cible < 2:
        cible = 2

    poids = _poids_par_aire(_projeter(points))
    # Les `cible` points les plus lourds, remis dans l'ordre du parcours.
    retenus = sorted(
        sorted(range(len(points)), key=lambda i: -poids[i])[:cible]
    )
    return [points[i] for i in retenus]
