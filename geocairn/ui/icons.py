"""Icônes dessinées à la volée (aucune ressource externe à embarquer)."""

from __future__ import annotations

from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QBrush, QColor, QIcon, QPainter, QPen, QPixmap

#: États possibles de l'ampoule d'affichage.
BULB_ON = "on"
BULB_OFF = "off"
BULB_PARTIAL = "partial"

_COULEURS = {
    #            contour      remplissage
    BULB_ON: ("#b8860b", "#ffd54a"),
    BULB_OFF: ("#9aa0a6", "#eceff1"),
    BULB_PARTIAL: ("#b8860b", "#fff3c4"),
}

#: Largeur de la zone cliquable de l'ampoule, dans l'icône composite.
BULB_WIDTH = 18

#: Côté des icônes de l'arborescence.
ICON_SIZE = 16

_cache: dict[tuple[str, int], QIcon] = {}
_cache_composite: dict[tuple[str, int, int], QIcon] = {}


def bulb_icon(state: str, size: int = 16) -> QIcon:
    """Petite ampoule indiquant si l'élément est affiché sur la carte.

    `partial` sert aux dossiers dont une partie seulement des traces est
    visible.
    """
    cle = (state, size)
    if cle in _cache:
        return _cache[cle]

    contour, remplissage = _COULEURS.get(state, _COULEURS[BULB_OFF])

    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(QPen(QColor(contour), 1.2))
    painter.setBrush(QBrush(QColor(remplissage)))

    # Le verre : un cercle occupant les deux tiers supérieurs.
    marge = size * 0.12
    diametre = size * 0.62
    painter.drawEllipse(QRectF(marge + size * 0.06, marge, diametre, diametre))

    # Le culot : un petit rectangle sous le verre.
    largeur = size * 0.30
    hauteur = size * 0.18
    painter.drawRect(
        QRectF(
            (size - largeur) / 2,
            marge + diametre - size * 0.04,
            largeur,
            hauteur,
        )
    )

    if state == BULB_ON:
        # Deux rayons pour que l'état allumé se lise d'un coup d'œil.
        painter.setPen(QPen(QColor(contour), 1.1))
        milieu = size / 2
        painter.drawLine(
            int(size * 0.06), int(size * 0.30), int(size * 0.20), int(size * 0.36)
        )
        painter.drawLine(
            int(size * 0.94), int(size * 0.30), int(size * 0.80), int(size * 0.36)
        )
        painter.drawLine(int(milieu), int(size * 0.02), int(milieu), int(size * 0.12))

    painter.end()

    icone = QIcon(pixmap)
    _cache[cle] = icone
    return icone


def bulb_with(state: str, base: QIcon, size: int = 16) -> QIcon:
    """Ampoule suivie de l'icône de l'élément, en une seule image.

    Un item d'arbre n'accepte qu'une icône par colonne : les deux sont donc
    dessinées côte à côte, l'ampoule occupant les `BULB_WIDTH` premiers pixels.
    """
    # La clé s'appuie sur le contenu de l'icône, pas sur l'adresse de l'objet :
    # Python réattribue les adresses libérées, et une icône construite après la
    # disparition d'une autre aurait hérité de son dessin.
    cle = (state, size, int(base.cacheKey()))
    if cle in _cache_composite:
        return _cache_composite[cle]

    pixmap = QPixmap(BULB_WIDTH + size, size)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    painter.drawPixmap(0, 0, bulb_icon(state, size).pixmap(size, size))
    painter.drawPixmap(BULB_WIDTH, 0, base.pixmap(size, size))
    painter.end()

    icone = QIcon(pixmap)
    _cache_composite[cle] = icone
    return icone
