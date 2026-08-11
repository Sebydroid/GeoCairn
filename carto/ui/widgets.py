"""Petits composants partagés par les panneaux."""

from __future__ import annotations

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QFontMetrics, QPainter
from PyQt6.QtWidgets import QLabel, QSizePolicy

#: Largeur au-delà de laquelle le texte n'exige plus de place supplémentaire.
LARGEUR_SOUHAITEE = 160


class ElidedLabel(QLabel):
    """Étiquette abrégée à l'affichage, texte complet conservé.

    Les noms de traces dépassent souvent la largeur du panneau. Une QLabel
    ordinaire imposerait sa longueur comme largeur minimale et élargirait tout
    le panneau ; celle-ci se laisse rétrécir et abrège son texte par le milieu,
    le nom entier restant accessible en infobulle et via text().
    """

    def __init__(self, texte: str = "", parent=None) -> None:
        super().__init__(texte, parent)
        self.setSizePolicy(
            QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred
        )
        self.setMinimumWidth(0)
        self.setToolTip(texte)

    def setText(self, texte: str) -> None:  # noqa: N802
        super().setText(texte)
        self.setToolTip(texte)

    def sizeHint(self):  # noqa: N802
        """Largeur souhaitée plafonnée : le texte ne dicte pas la mise en page."""
        hint = super().sizeHint()
        return QSize(min(hint.width(), LARGEUR_SOUHAITEE), hint.height())

    def minimumSizeHint(self):  # noqa: N802
        """Largeur minimale réduite aux points de suspension."""
        hauteur = super().minimumSizeHint().height()
        return QSize(QFontMetrics(self.font()).horizontalAdvance("…"), hauteur)

    def paintEvent(self, _event) -> None:  # noqa: N802
        painter = QPainter(self)
        metrics = QFontMetrics(self.font())
        abrege = metrics.elidedText(
            self.text(), Qt.TextElideMode.ElideMiddle, self.width()
        )
        painter.drawText(self.rect(), int(self.alignment()), abrege)
        painter.end()
