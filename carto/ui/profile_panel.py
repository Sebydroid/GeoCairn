"""Profil de la trace sous la carte : altitude ou vitesse selon la distance."""

from __future__ import annotations

from PyQt6.QtCore import QPointF, QRectF, Qt, pyqtSignal
from PyQt6.QtGui import QBrush, QColor, QFontMetrics, QPainter, QPen, QPolygonF
from PyQt6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ..geo import cumulative_distances, format_length, has_times, speeds
from ..models import Point
from .widgets import ElidedLabel

#: Sources traçables en ordonnée.
SOURCE_ELE_FICHIER = "ele"
SOURCE_ELE_SERVICE = "ele_service"
SOURCE_VITESSE = "vitesse"

SOURCES = [
    (SOURCE_ELE_FICHIER, "Altitude du fichier", "m"),
    (SOURCE_ELE_SERVICE, "Altitude IGN", "m"),
    (SOURCE_VITESSE, "Vitesse", "km/h"),
]

MARGE_GAUCHE = 52
MARGE_BASSE = 22
MARGE_HAUTE = 10
MARGE_DROITE = 10


def series_for(points, source: str) -> list[float | None]:
    """Valeurs en ordonnée pour la source demandée."""
    if source == SOURCE_ELE_FICHIER:
        return [p.ele for p in points]
    if source == SOURCE_ELE_SERVICE:
        return [p.ele_service for p in points]
    if source == SOURCE_VITESSE:
        return speeds(points)
    return []


def source_available(points, source: str) -> bool:
    """Vrai si la source contient au moins deux valeurs exploitables."""
    if source == SOURCE_VITESSE:
        return has_times(points)
    return sum(1 for v in series_for(points, source) if v is not None) >= 2


class ProfileView(QWidget):
    """Tracé du profil, dessiné à la main (aucune dépendance graphique)."""

    point_clicked = pyqtSignal(int)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(110)
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
        self.setMouseTracking(True)

        self._points: list[Point] = []
        self._distances: list[float] = []
        self._valeurs: list[float | None] = []
        self._unite = "m"
        self._message = "Aucune trace sélectionnée"
        self._survol: int | None = None

    # -------------------------------------------------------------- contenu

    def set_series(
        self,
        points,
        valeurs: list[float | None],
        unite: str,
        message: str = "",
    ) -> None:
        self._points = list(points)
        self._distances = cumulative_distances(self._points)
        self._valeurs = list(valeurs)
        self._unite = unite
        self._message = message
        self._survol = None
        self.update()

    def clear(self, message: str = "Aucune trace sélectionnée") -> None:
        self.set_series([], [], "m", message)

    @property
    def has_data(self) -> bool:
        return sum(1 for v in self._valeurs if v is not None) >= 2

    # ------------------------------------------------------------- géométrie

    def _plot_rect(self) -> QRectF:
        return QRectF(
            MARGE_GAUCHE,
            MARGE_HAUTE,
            max(1, self.width() - MARGE_GAUCHE - MARGE_DROITE),
            max(1, self.height() - MARGE_HAUTE - MARGE_BASSE),
        )

    def _bornes(self) -> tuple[float, float]:
        connues = [v for v in self._valeurs if v is not None]
        bas, haut = min(connues), max(connues)
        if haut - bas < 1e-6:
            bas, haut = bas - 1, haut + 1
        marge = (haut - bas) * 0.08
        return (bas - marge, haut + marge)

    def index_at(self, x: float) -> int | None:
        """Indice du point sous une abscisse écran."""
        if not self._distances or self._distances[-1] <= 0:
            return None
        zone = self._plot_rect()
        ratio = (x - zone.left()) / zone.width()
        ratio = max(0.0, min(1.0, ratio))
        cible = ratio * self._distances[-1]
        meilleur, ecart = 0, float("inf")
        for i, d in enumerate(self._distances):
            if abs(d - cible) < ecart:
                meilleur, ecart = i, abs(d - cible)
        return meilleur

    def _position(self, index: int, bas: float, haut: float) -> QPointF:
        zone = self._plot_rect()
        total = self._distances[-1] or 1.0
        x = zone.left() + zone.width() * (self._distances[index] / total)
        valeur = self._valeurs[index]
        y = zone.bottom() - zone.height() * ((valeur - bas) / (haut - bas))
        return QPointF(x, y)

    # --------------------------------------------------------------- dessin

    def paintEvent(self, _event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor("#fbfbfb"))

        if not self.has_data:
            painter.setPen(QColor("#888888"))
            painter.drawText(
                self.rect(), Qt.AlignmentFlag.AlignCenter, self._message
            )
            painter.end()
            return

        zone = self._plot_rect()
        bas, haut = self._bornes()

        painter.setPen(QPen(QColor("#cccccc"), 1))
        painter.drawRect(zone)

        # Graduations horizontales et échelle des ordonnées.
        metrics = QFontMetrics(painter.font())
        painter.setPen(QColor("#666666"))
        for i in range(5):
            valeur = bas + (haut - bas) * i / 4
            y = zone.bottom() - zone.height() * i / 4
            painter.setPen(QPen(QColor("#eeeeee"), 1))
            painter.drawLine(int(zone.left()), int(y), int(zone.right()), int(y))
            painter.setPen(QColor("#666666"))
            texte = f"{valeur:.0f}"
            painter.drawText(
                int(zone.left()) - metrics.horizontalAdvance(texte) - 6,
                int(y) + metrics.height() // 3,
                texte,
            )

        painter.drawText(2, int(MARGE_HAUTE) + metrics.height() // 2, self._unite)

        # Échelle des abscisses : distance cumulée.
        total = self._distances[-1]
        for i in range(5):
            x = zone.left() + zone.width() * i / 4
            texte = format_length(total * i / 4)
            largeur = metrics.horizontalAdvance(texte)
            painter.drawText(
                int(x - largeur / 2),
                int(zone.bottom()) + metrics.height(),
                texte,
            )

        # Courbe : les trous (valeurs absentes) coupent le tracé.
        segments: list[list[QPointF]] = []
        courant: list[QPointF] = []
        for index, valeur in enumerate(self._valeurs):
            if valeur is None:
                if len(courant) > 1:
                    segments.append(courant)
                courant = []
                continue
            courant.append(self._position(index, bas, haut))
        if len(courant) > 1:
            segments.append(courant)

        for segment in segments:
            aire = QPolygonF(segment)
            aire.append(QPointF(segment[-1].x(), zone.bottom()))
            aire.append(QPointF(segment[0].x(), zone.bottom()))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(QColor(31, 95, 191, 45)))
            painter.drawPolygon(aire)

            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(QColor("#1f5fbf"), 2))
            painter.drawPolyline(QPolygonF(segment))

        # Repère de survol.
        if self._survol is not None and 0 <= self._survol < len(self._valeurs):
            valeur = self._valeurs[self._survol]
            if valeur is not None:
                position = self._position(self._survol, bas, haut)
                painter.setPen(QPen(QColor("#b8860b"), 1, Qt.PenStyle.DashLine))
                painter.drawLine(
                    int(position.x()), int(zone.top()),
                    int(position.x()), int(zone.bottom()),
                )
                painter.setPen(QPen(QColor("#b8860b"), 2))
                painter.setBrush(QBrush(QColor("#ffd700")))
                painter.drawEllipse(position, 4, 4)

                etiquette = (
                    f"{format_length(self._distances[self._survol])} — "
                    f"{valeur:.0f} {self._unite}"
                )
                painter.setPen(QColor("#333333"))
                largeur = metrics.horizontalAdvance(etiquette)
                x = min(position.x() + 8, zone.right() - largeur)
                painter.drawText(int(x), int(zone.top()) + metrics.height(), etiquette)

        painter.end()

    # ------------------------------------------------------------ souris

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if not self.has_data:
            return
        self._survol = self.index_at(event.position().x())
        self.update()

    def leaveEvent(self, _event) -> None:  # noqa: N802
        self._survol = None
        self.update()

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if not self.has_data:
            return
        index = self.index_at(event.position().x())
        if index is not None:
            self.point_clicked.emit(index)


class ProfilePanel(QWidget):
    """Profil et sélecteur de la grandeur portée en ordonnée."""

    point_clicked = pyqtSignal(int)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)

        self.title = ElidedLabel("Profil", self)
        self.source_combo = QComboBox(self)
        for _cle, libelle, _unite in SOURCES:
            self.source_combo.addItem(libelle)
        self.source_combo.currentIndexChanged.connect(self._on_source_changed)

        self.view = ProfileView(self)
        self.view.point_clicked.connect(self.point_clicked)

        entete = QHBoxLayout()
        entete.setContentsMargins(4, 2, 4, 2)
        # Le titre prend la place restante : un espaceur la lui prendrait, et
        # l'étiquette abrégée se réduirait à rien.
        entete.addWidget(self.title, 1)
        entete.addWidget(QLabel("Afficher :", self))
        entete.addWidget(self.source_combo)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        layout.addLayout(entete)
        layout.addWidget(self.view)

        self._points: list[Point] = []
        self._nom = ""
        self.set_points([], "")

    # -------------------------------------------------------------- contenu

    @property
    def source(self) -> str:
        return SOURCES[self.source_combo.currentIndex()][0]

    def set_source(self, source: str) -> bool:
        for rang, (cle, _libelle, _unite) in enumerate(SOURCES):
            if cle == source:
                self.source_combo.setCurrentIndex(rang)
                return True
        return False

    def set_points(self, points, nom: str = "") -> None:
        self._points = list(points)
        self._nom = nom
        self._update_availability()
        self._refresh()

    def _update_availability(self) -> None:
        """Grise les sources dont la trace ne porte pas les données."""
        modele = self.source_combo.model()
        for rang, (cle, _libelle, _unite) in enumerate(SOURCES):
            disponible = source_available(self._points, cle)
            item = modele.item(rang)
            if item is not None:
                item.setEnabled(disponible)

    def _on_source_changed(self, _index: int) -> None:
        self._refresh()

    def _refresh(self) -> None:
        cle, libelle, unite = SOURCES[self.source_combo.currentIndex()]
        self.title.setText(f"Profil — {self._nom}" if self._nom else "Profil")

        if not self._points:
            self.view.clear("Sélectionnez une trace pour voir son profil")
            return

        valeurs = series_for(self._points, cle)
        if sum(1 for v in valeurs if v is not None) < 2:
            self.view.set_series([], [], unite, self._message_absence(cle, libelle))
            return

        self.view.set_series(self._points, valeurs, unite)

    def _message_absence(self, cle: str, libelle: str) -> str:
        if cle == SOURCE_ELE_SERVICE:
            return "Aucune altitude IGN : lancez « Calculer l'altitude (IGN) »."
        if cle == SOURCE_VITESSE:
            return "Aucun horodatage dans cette trace : vitesse indisponible."
        return f"{libelle} absente de cette trace."
