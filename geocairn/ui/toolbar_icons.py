"""Icônes de la barre d'outils, dessinées à la volée.

Les icônes standard de Qt sont hétéroclites : disquettes, dossiers système et
flèches d'un autre âge, sans rapport les unes avec les autres. Celles-ci sont
tracées sur une même grille, au même trait et dans une palette commune, pour que
la barre se lise d'un coup d'œil.
"""

from __future__ import annotations

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QBrush, QColor, QIcon, QPainter, QPen, QPixmap, QPolygonF

#: Côté de la grille de dessin.
TAILLE = 22

TRAIT = "#37474f"        # gris ardoise, couleur de base
ACCENT = "#1f5fbf"       # bleu, ce qui touche à la trace
ACTION = "#2e8b39"       # vert, ce qui ajoute
ALERTE = "#c62828"       # rouge, ce qui retire

_cache: dict[str, QIcon] = {}


def _peintre(pixmap: QPixmap) -> QPainter:
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    return painter


def _stylo(painter: QPainter, couleur: str, epaisseur: float = 1.8) -> None:
    pen = QPen(QColor(couleur), epaisseur)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)


def _trace(painter: QPainter, couleur: str = ACCENT) -> None:
    """Ligne brisée évoquant une trace, motif commun à plusieurs icônes."""
    _stylo(painter, couleur, 2.0)
    painter.drawPolyline(
        QPolygonF([QPointF(3, 16), QPointF(8, 8), QPointF(13, 13), QPointF(19, 5)])
    )


def _pastille(painter: QPainter, x: float, y: float, couleur: str) -> None:
    painter.setPen(QPen(QColor(couleur), 1.6))
    painter.setBrush(QBrush(QColor("#ffffff")))
    painter.drawEllipse(QPointF(x, y), 2.2, 2.2)


def _fleche_verticale(painter: QPainter, vers_le_bas: bool, couleur: str) -> None:
    _stylo(painter, couleur, 2.0)
    haut, bas = (4, 14) if vers_le_bas else (14, 4)
    painter.drawLine(QPointF(11, haut), QPointF(11, bas))
    pointe = QPolygonF(
        [
            QPointF(11, bas),
            QPointF(11 - 4, bas + (-4 if vers_le_bas else 4)),
            QPointF(11 + 4, bas + (-4 if vers_le_bas else 4)),
        ]
    )
    painter.setBrush(QBrush(QColor(couleur)))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawPolygon(pointe)


def _socle(painter: QPainter) -> None:
    """Trait horizontal figurant la bibliothèque, sous les flèches."""
    _stylo(painter, TRAIT, 2.0)
    painter.drawLine(QPointF(4, 18), QPointF(18, 18))


def _dessiner(nom: str) -> QPixmap:
    pixmap = QPixmap(TAILLE, TAILLE)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = _peintre(pixmap)

    if nom == "import":
        _fleche_verticale(painter, True, ACCENT)
        _socle(painter)

    elif nom == "export":
        _fleche_verticale(painter, False, TRAIT)
        _socle(painter)

    elif nom == "creer":
        _trace(painter)
        # Un « + » vert : cette action ajoute une trace.
        _stylo(painter, ACTION, 2.2)
        painter.drawLine(QPointF(16, 15), QPointF(20, 15))
        painter.drawLine(QPointF(18, 13), QPointF(18, 17))

    elif nom == "modifier":
        _trace(painter, TRAIT)
        for x, y in ((3, 16), (8, 8), (13, 13), (19, 5)):
            _pastille(painter, x, y, ACCENT)

    elif nom == "annuler":
        # Arc sur la moitié haute, pointe vers le bas à son extrémité gauche :
        # une flèche qui revient en arrière.
        _stylo(painter, TRAIT, 2.0)
        painter.drawArc(QRectF(5, 7, 13, 12), 10 * 16, 170 * 16)
        painter.setBrush(QBrush(QColor(TRAIT)))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawPolygon(
            QPolygonF([QPointF(1.5, 10), QPointF(8.5, 10), QPointF(5, 16.5)])
        )

    elif nom == "boucle":
        _stylo(painter, ACCENT, 2.0)
        painter.drawEllipse(QRectF(5, 5, 12, 12))
        _pastille(painter, 11, 5, ACTION)

    elif nom == "enregistrer":
        # Disquette : le contour, le volet coulissant et l'étiquette.
        _stylo(painter, TRAIT, 1.6)
        painter.drawRoundedRect(QRectF(3.5, 3.5, 15, 15), 2, 2)
        painter.setBrush(QBrush(QColor(TRAIT)))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRect(QRectF(7, 3.5, 8, 5))          # volet
        painter.setBrush(QBrush(QColor("#ffffff")))
        painter.drawRect(QRectF(12, 4.5, 2, 3))         # loquet
        _stylo(painter, TRAIT, 1.4)
        painter.drawRect(QRectF(6.5, 11, 9, 7.5))       # étiquette

    elif nom == "imprimer":
        # Imprimante : le bac, le corps, et la feuille qui sort, une trace
        # dessinée dessus.
        _stylo(painter, TRAIT, 1.6)
        painter.drawRect(QRectF(6.5, 2.5, 9, 5))                # bac
        painter.drawRoundedRect(QRectF(2.5, 7.5, 17, 8), 2, 2)  # corps
        painter.setBrush(QBrush(QColor("#ffffff")))
        painter.drawRect(QRectF(6.5, 12.5, 9, 7))               # feuille
        _stylo(painter, ACCENT, 1.4)
        painter.drawPolyline(
            QPolygonF([QPointF(8, 18), QPointF(10, 15), QPointF(12, 17), QPointF(14, 14)])
        )

    elif nom == "trace":
        # Icône des traces dans l'arborescence : ne dépend d'aucun thème.
        _trace(painter)

    elif nom == "crayon":
        # Trace en cours de modification.
        _stylo(painter, TRAIT, 1.8)
        painter.drawLine(QPointF(4, 18), QPointF(6, 13))
        painter.drawLine(QPointF(6, 13), QPointF(15, 4))
        painter.drawLine(QPointF(15, 4), QPointF(18, 7))
        painter.drawLine(QPointF(18, 7), QPointF(9, 16))
        painter.drawLine(QPointF(9, 16), QPointF(4, 18))
        painter.setBrush(QBrush(QColor(ACTION)))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawPolygon(
            QPolygonF([QPointF(4, 18), QPointF(6, 13), QPointF(9, 16)])
        )

    elif nom == "effacer":
        _stylo(painter, ALERTE, 1.8)
        painter.drawLine(QPointF(4, 7), QPointF(18, 7))
        painter.drawRoundedRect(QRectF(6, 7, 10, 12), 2, 2)
        painter.drawLine(QPointF(9, 3), QPointF(13, 3))
        painter.drawLine(QPointF(11, 10), QPointF(11, 16))

    painter.end()
    return pixmap


def toolbar_icon(nom: str) -> QIcon:
    """Icône de la barre d'outils, dessinée une fois puis gardée en mémoire."""
    if nom not in _cache:
        _cache[nom] = QIcon(_dessiner(nom))
    return _cache[nom]
