"""Profil de la trace sous la carte : altitudes et vitesse selon la distance.

Plusieurs grandeurs peuvent être tracées ensemble. Celles qui ne partagent pas
la même unité reçoivent leur propre échelle : les altitudes à gauche en mètres,
la vitesse à droite en km/h.
"""

from __future__ import annotations

from PyQt6.QtCore import QPointF, QRectF, Qt, pyqtSignal
from PyQt6.QtGui import QBrush, QColor, QFontMetrics, QPainter, QPen, QPolygonF
from PyQt6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ..geo import (
    cumulative_distances,
    elevation_gain,
    format_length,
    format_speed,
    has_times,
    speed_stats,
    speeds,
    total_length,
)
from ..models import Point
from .widgets import ElidedLabel

#: Grandeurs traçables en ordonnée.
SOURCE_ELE_FICHIER = "ele"
SOURCE_ELE_SERVICE = "ele_service"
SOURCE_VITESSE = "vitesse"

#: (clé, libellé, unité, couleur)
SOURCES = [
    (SOURCE_ELE_FICHIER, "Altitude du fichier", "m", "#1f5fbf"),
    (SOURCE_ELE_SERVICE, "Altitude IGN", "m", "#2e8b39"),
    (SOURCE_VITESSE, "Vitesse", "km/h", "#e6194b"),
]

MARGE_GAUCHE = 52
MARGE_BASSE = 22
MARGE_HAUTE = 22
MARGE_DROITE = 12
MARGE_DROITE_AXE = 52


def series_for(points, source: str) -> list[float | None]:
    """Valeurs en ordonnée pour la grandeur demandée."""
    if source == SOURCE_ELE_FICHIER:
        return [p.ele for p in points]
    if source == SOURCE_ELE_SERVICE:
        return [p.ele_service for p in points]
    if source == SOURCE_VITESSE:
        return speeds(points)
    return []


def source_available(points, source: str) -> bool:
    """Vrai si la trace porte au moins deux valeurs exploitables."""
    if source == SOURCE_VITESSE:
        return has_times(points)
    return sum(1 for v in series_for(points, source) if v is not None) >= 2


class ProfileView(QWidget):
    """Tracé du profil, dessiné à la main (aucune dépendance graphique)."""

    point_clicked = pyqtSignal(int)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(110)
        # Expanding en hauteur : tout l'espace gagné en agrandissant le panneau
        # doit aller au tracé, pas aux étiquettes qui l'entourent.
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self.setMouseTracking(True)

        self._points: list[Point] = []
        self._distances: list[float] = []
        self._series: list[dict] = []
        self._message = "Aucune trace sélectionnée"
        self._survol: int | None = None
        self._selection: list[int] = []
        #: Fenêtre visible en abscisse, en fraction de la distance totale.
        self._vue = (0.0, 1.0)

    # -------------------------------------------------------------- contenu

    def set_series(self, points, series: list[dict], message: str = "") -> None:
        """`series` : liste de {cle, libelle, unite, couleur, valeurs}."""
        change = [p.as_tuple() for p in points] != [
            p.as_tuple() for p in self._points
        ]
        self._points = list(points)
        self._distances = cumulative_distances(self._points)
        self._series = [s for s in series if self._exploitable(s)]
        self._message = message
        self._survol = None
        if change:
            # Changer de trace remet la vue à plat ; cocher une grandeur non.
            self._selection = []
            self._vue = (0.0, 1.0)
        self.update()

    @staticmethod
    def _exploitable(serie: dict) -> bool:
        return sum(1 for v in serie["valeurs"] if v is not None) >= 2

    def clear(self, message: str = "Aucune trace sélectionnée") -> None:
        self.set_series([], [], message)

    def set_selected(self, indexes) -> None:
        """Met un ou plusieurs points en évidence, désignés par une autre vue."""
        if indexes is None:
            self._selection = []
        elif isinstance(indexes, int):
            self._selection = [indexes]
        else:
            self._selection = list(indexes)
        self.update()

    @property
    def selected(self) -> int | None:
        """Point désigné, ou le premier d'une sélection multiple."""
        return self._selection[0] if self._selection else None

    @property
    def selected_indexes(self) -> list[int]:
        return list(self._selection)

    # ---------------------------------------------------------------- zoom

    def zoom(self, facteur: float, ancre: float = 0.5) -> None:
        """Resserre ou élargit la vue en abscisse autour d'une fraction donnée."""
        debut, fin = self._vue
        largeur = (fin - debut) / facteur
        # En deçà, on lirait moins d'un millième de la trace.
        largeur = max(0.001, min(1.0, largeur))
        position = debut + (fin - debut) * ancre

        debut = position - largeur * ancre
        fin = debut + largeur
        if debut < 0:
            debut, fin = 0.0, largeur
        if fin > 1:
            debut, fin = 1.0 - largeur, 1.0
        self._vue = (debut, fin)
        self.update()

    def reset_zoom(self) -> None:
        self._vue = (0.0, 1.0)
        self.update()

    @property
    def view_range(self) -> tuple[float, float]:
        return self._vue

    def wheelEvent(self, event) -> None:  # noqa: N802
        if not self.has_data:
            return
        zone = self._plot_rect()
        ancre = (event.position().x() - zone.left()) / zone.width()
        ancre = max(0.0, min(1.0, ancre))
        self.zoom(1.25 if event.angleDelta().y() > 0 else 1 / 1.25, ancre)

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802
        self.reset_zoom()

    @property
    def has_data(self) -> bool:
        return bool(self._series)

    @property
    def units(self) -> list[str]:
        """Unités présentes, dans l'ordre d'apparition (deux au plus tracées)."""
        vues: list[str] = []
        for serie in self._series:
            if serie["unite"] not in vues:
                vues.append(serie["unite"])
        return vues

    # ------------------------------------------------------------- géométrie

    def _plot_rect(self) -> QRectF:
        droite = MARGE_DROITE_AXE if len(self.units) > 1 else MARGE_DROITE
        return QRectF(
            MARGE_GAUCHE,
            MARGE_HAUTE,
            max(1, self.width() - MARGE_GAUCHE - droite),
            max(1, self.height() - MARGE_HAUTE - MARGE_BASSE),
        )

    def _fraction(self, index: int) -> float:
        """Position du point le long de la trace, entre 0 et 1."""
        total = self._distances[-1] or 1.0
        return self._distances[index] / total

    def visible_indexes(self) -> list[int]:
        """Indices compris dans la fenêtre de zoom, avec un point de marge."""
        debut, fin = self._vue
        dedans = [
            i for i in range(len(self._distances))
            if debut <= self._fraction(i) <= fin
        ]
        if not dedans:
            return list(range(len(self._distances)))
        premier = max(0, dedans[0] - 1)
        dernier = min(len(self._distances) - 1, dedans[-1] + 1)
        return list(range(premier, dernier + 1))

    def _bornes(self, unite: str) -> tuple[float, float]:
        """Échelle commune aux séries d'une même unité, sur la partie visible."""
        visibles = set(self.visible_indexes())
        connues = [
            v
            for serie in self._series
            if serie["unite"] == unite
            for i, v in enumerate(serie["valeurs"])
            if v is not None and i in visibles
        ]
        if not connues:
            return (0.0, 1.0)
        bas, haut = min(connues), max(connues)
        if haut - bas < 1e-6:
            bas, haut = bas - 1, haut + 1
        marge = (haut - bas) * 0.08
        return (bas - marge, haut + marge)

    def index_at(self, x: float) -> int | None:
        """Indice du point sous une abscisse écran, zoom compris."""
        if not self._distances or self._distances[-1] <= 0:
            return None
        zone = self._plot_rect()
        debut, fin = self._vue
        ratio = max(0.0, min(1.0, (x - zone.left()) / zone.width()))
        cible = (debut + (fin - debut) * ratio) * self._distances[-1]
        meilleur, ecart = 0, float("inf")
        for i, d in enumerate(self._distances):
            if abs(d - cible) < ecart:
                meilleur, ecart = i, abs(d - cible)
        return meilleur

    def _abscisse(self, index: int) -> float:
        zone = self._plot_rect()
        debut, fin = self._vue
        return zone.left() + zone.width() * (
            (self._fraction(index) - debut) / (fin - debut)
        )

    def _position(self, index: int, valeur: float, bornes) -> QPointF:
        zone = self._plot_rect()
        bas, haut = bornes
        y = zone.bottom() - zone.height() * ((valeur - bas) / (haut - bas))
        return QPointF(self._abscisse(index), y)

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
        unites = self.units
        bornes = {u: self._bornes(u) for u in unites}
        metrics = QFontMetrics(painter.font())

        painter.setPen(QPen(QColor("#cccccc"), 1))
        painter.drawRect(zone)

        self._draw_axes(painter, metrics, zone, unites, bornes)
        self._draw_series(painter, zone, bornes)
        self._draw_selection(painter, zone, bornes)
        self._draw_legend(painter, metrics, zone)
        self._draw_hover(painter, metrics, zone, bornes)

        painter.end()

    def _draw_selection(self, painter, zone, bornes) -> None:
        """Repères des points désignés depuis une autre vue."""
        if not self._selection:
            return
        painter.save()
        painter.setClipRect(zone)
        multiple = len(self._selection) > 1

        for index in self._selection:
            if not 0 <= index < len(self._distances):
                continue
            x = self._abscisse(index)
            if not zone.left() - 2 <= x <= zone.right() + 2:
                continue

            painter.setPen(QPen(QColor("#b8860b"), 1 if multiple else 2))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawLine(int(x), int(zone.top()), int(x), int(zone.bottom()))

            for serie in self._series:
                valeur = serie["valeurs"][index]
                if valeur is None:
                    continue
                painter.setBrush(QBrush(QColor("#ffd700")))
                painter.setPen(QPen(QColor("#b8860b"), 2))
                painter.drawEllipse(
                    self._position(index, valeur, bornes[serie["unite"]]),
                    4 if multiple else 5,
                    4 if multiple else 5,
                )
        painter.restore()

    def _draw_axes(self, painter, metrics, zone, unites, bornes) -> None:
        for rang, unite in enumerate(unites[:2]):
            bas, haut = bornes[unite]
            couleur = QColor(
                next(s["couleur"] for s in self._series if s["unite"] == unite)
            )
            for i in range(5):
                valeur = bas + (haut - bas) * i / 4
                y = zone.bottom() - zone.height() * i / 4
                if rang == 0:
                    painter.setPen(QPen(QColor("#eeeeee"), 1))
                    painter.drawLine(
                        int(zone.left()), int(y), int(zone.right()), int(y)
                    )
                texte = f"{valeur:.0f}"
                painter.setPen(couleur if len(unites) > 1 else QColor("#666666"))
                if rang == 0:
                    x = int(zone.left()) - metrics.horizontalAdvance(texte) - 6
                else:
                    x = int(zone.right()) + 6
                painter.drawText(x, int(y) + metrics.height() // 3, texte)

            painter.setPen(couleur if len(unites) > 1 else QColor("#666666"))
            if rang == 0:
                painter.drawText(2, int(MARGE_HAUTE) - 4, unite)
            else:
                painter.drawText(
                    int(zone.right()) + 6, int(MARGE_HAUTE) - 4, unite
                )

        # Échelle des abscisses : distance parcourue sur la partie visible.
        painter.setPen(QColor("#666666"))
        total = self._distances[-1]
        debut, fin = self._vue
        for i in range(5):
            x = zone.left() + zone.width() * i / 4
            texte = format_length(total * (debut + (fin - debut) * i / 4))
            largeur = metrics.horizontalAdvance(texte)
            painter.drawText(
                int(x - largeur / 2), int(zone.bottom()) + metrics.height(), texte
            )
        if (fin - debut) < 0.999:
            painter.drawText(
                int(zone.left()) + 4,
                int(zone.bottom()) + metrics.height(),
                f"zoom ×{1 / (fin - debut):.0f}",
            )

    def _draw_series(self, painter, zone, bornes) -> None:
        remplir = len(self._series) == 1
        # Sous zoom, une partie des points tombe hors du cadre.
        painter.save()
        painter.setClipRect(zone)
        for serie in self._series:
            limites = bornes[serie["unite"]]
            couleur = QColor(serie["couleur"])

            # Les valeurs manquantes coupent le tracé plutôt que de le fausser.
            segments: list[list[QPointF]] = []
            courant: list[QPointF] = []
            for index, valeur in enumerate(serie["valeurs"]):
                if valeur is None:
                    if len(courant) > 1:
                        segments.append(courant)
                    courant = []
                    continue
                courant.append(self._position(index, valeur, limites))
            if len(courant) > 1:
                segments.append(courant)

            for segment in segments:
                if remplir:
                    aire = QPolygonF(segment)
                    aire.append(QPointF(segment[-1].x(), zone.bottom()))
                    aire.append(QPointF(segment[0].x(), zone.bottom()))
                    painter.setPen(Qt.PenStyle.NoPen)
                    fond = QColor(couleur)
                    fond.setAlpha(45)
                    painter.setBrush(QBrush(fond))
                    painter.drawPolygon(aire)

                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.setPen(QPen(couleur, 2))
                painter.drawPolyline(QPolygonF(segment))
        painter.restore()

    def _draw_legend(self, painter, metrics, zone) -> None:
        if len(self._series) < 2:
            return
        x = zone.left() + 8
        y = int(MARGE_HAUTE) - 6
        for serie in self._series:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(QColor(serie["couleur"])))
            painter.drawRect(int(x), y - 8, 10, 10)
            painter.setPen(QColor("#333333"))
            painter.drawText(int(x) + 14, y, serie["libelle"])
            x += 14 + metrics.horizontalAdvance(serie["libelle"]) + 16

    def _draw_hover(self, painter, metrics, zone, bornes) -> None:
        if self._survol is None or not 0 <= self._survol < len(self._distances):
            return

        x = self._abscisse(self._survol)
        if not zone.left() <= x <= zone.right():
            return
        painter.setPen(QPen(QColor("#b8860b"), 1, Qt.PenStyle.DashLine))
        painter.drawLine(int(x), int(zone.top()), int(x), int(zone.bottom()))

        morceaux = [format_length(self._distances[self._survol])]
        for serie in self._series:
            valeur = serie["valeurs"][self._survol]
            if valeur is None:
                continue
            position = self._position(self._survol, valeur, bornes[serie["unite"]])
            painter.setPen(QPen(QColor(serie["couleur"]), 2))
            painter.setBrush(QBrush(QColor("#ffffff")))
            painter.drawEllipse(position, 4, 4)
            morceaux.append(f"{valeur:.0f} {serie['unite']}")

        etiquette = "  —  ".join(morceaux)
        painter.setPen(QColor("#333333"))
        largeur = metrics.horizontalAdvance(etiquette)
        painter.drawText(
            int(min(x + 8, zone.right() - largeur)),
            int(zone.top()) + metrics.height(),
            etiquette,
        )

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
    """Profil et cases à cocher des grandeurs à superposer."""

    point_clicked = pyqtSignal(int)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)

        # Tout ce dont _refresh a besoin est posé avant la moindre connexion :
        # cocher une case déclenche _refresh dès la construction.
        self._points: list[Point] = []
        self._nom = ""
        self.title = ElidedLabel("Profil", self)
        self.stats = ElidedLabel("", self)
        # Une seule ligne, de hauteur fixe : sans cela le résumé se partageait
        # la hauteur avec le tracé et en prenait la moitié.
        self.stats.setSizePolicy(
            QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed
        )
        self.stats.setFixedHeight(self.stats.fontMetrics().height() + 4)
        self.view = ProfileView(self)

        self.view.point_clicked.connect(self.point_clicked)

        entete = QHBoxLayout()
        entete.setContentsMargins(4, 2, 4, 2)
        entete.addWidget(self.title, 1)
        entete.addWidget(QLabel("Afficher :", self))

        self.checks: dict[str, QCheckBox] = {}
        for cle, libelle, _unite, couleur in SOURCES:
            case = QCheckBox(libelle, self)
            case.setStyleSheet(f"QCheckBox {{ color: {couleur}; }}")
            case.toggled.connect(self._refresh)
            entete.addWidget(case)
            self.checks[cle] = case
        self.checks[SOURCE_ELE_FICHIER].setChecked(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        layout.addLayout(entete)
        layout.addWidget(self.view)
        layout.addWidget(self.stats)

        self.set_points([], "")

    # ----------------------------------------------------------- sélection

    def select_index(self, index: int | None) -> None:
        """Met un point en évidence sans réémettre : les vues se répondraient."""
        self.view.set_selected(index)

    def select_indexes(self, indexes) -> None:
        """Met plusieurs points en évidence."""
        self.view.set_selected(indexes)

    @property
    def selected(self) -> int | None:
        return self.view.selected

    @property
    def selected_indexes(self) -> list[int]:
        return self.view.selected_indexes

    # -------------------------------------------------------------- contenu

    @property
    def active_sources(self) -> list[str]:
        return [cle for cle, case in self.checks.items() if case.isChecked()]

    def set_sources(self, cles) -> None:
        """Coche exactement les grandeurs demandées."""
        voulues = set(cles)
        for cle, case in self.checks.items():
            case.blockSignals(True)
            case.setChecked(cle in voulues)
            case.blockSignals(False)
        self._refresh()

    def set_source(self, cle: str) -> bool:
        """N'affiche que cette grandeur."""
        if cle not in self.checks:
            return False
        self.set_sources([cle])
        return True

    def add_source(self, cle: str) -> bool:
        """Ajoute une grandeur à celles déjà affichées."""
        if cle not in self.checks:
            return False
        self.checks[cle].setChecked(True)
        return True

    def set_points(self, points, nom: str = "") -> None:
        self._points = list(points)
        self._nom = nom
        self._update_availability()
        self._refresh()

    def _update_availability(self) -> None:
        """Signale les grandeurs absentes sans jamais bloquer la case.

        Griser une case cochée la rendait impossible à décocher : c'est ce qui
        arrivait en passant d'une trace pourvue d'altitude IGN à une trace qui
        n'en a pas.
        """
        for cle, case in self.checks.items():
            disponible = source_available(self._points, cle)
            case.setToolTip(
                "" if disponible else self._message_absence(cle)
            )
            # La case reste cliquable ; seul son libellé s'estompe.
            couleur = self._couleur(cle) if disponible else "#9aa0a6"
            case.setStyleSheet(f"QCheckBox {{ color: {couleur}; }}")

    @staticmethod
    def _couleur(cle: str) -> str:
        for autre, _libelle, _unite, couleur in SOURCES:
            if autre == cle:
                return couleur
        return "#333333"

    def summary(self) -> str:
        """Chiffres clés de la trace : distance, dénivelés, vitesses."""
        if len(self._points) < 2:
            return ""

        morceaux = [f"Distance : {format_length(total_length(self._points))}"]

        # Dénivelés depuis l'altitude du fichier ; à défaut, celle de l'IGN.
        for cle, origine in (
            (SOURCE_ELE_FICHIER, "fichier"),
            (SOURCE_ELE_SERVICE, "IGN"),
        ):
            valeurs = series_for(self._points, cle)
            if sum(1 for v in valeurs if v is not None) >= 2:
                montee, descente = elevation_gain(valeurs)
                morceaux.append(
                    f"Dénivelé ({origine}) : +{montee:.0f} m / −{descente:.0f} m"
                )
                break

        maximale, moyenne = speed_stats(self._points)
        if maximale is not None:
            morceaux.append(f"Vitesse max : {format_speed(maximale)}")
            morceaux.append(f"moyenne : {format_speed(moyenne)}")

        return "     ".join(morceaux)

    def _refresh(self, *_args) -> None:
        self.title.setText(f"Profil — {self._nom}" if self._nom else "Profil")
        self.stats.setText(self.summary())

        if not self._points:
            self.view.clear("Sélectionnez une trace pour voir son profil")
            return

        actives = self.active_sources
        series = []
        for cle, libelle, unite, couleur in SOURCES:
            if cle not in actives:
                continue
            series.append(
                {
                    "cle": cle,
                    "libelle": libelle,
                    "unite": unite,
                    "couleur": couleur,
                    "valeurs": series_for(self._points, cle),
                }
            )

        if not series:
            self.view.set_series([], [], "Cochez une grandeur à afficher.")
            return

        self.view.set_series(self._points, series, self._message_manquant(actives))

    def _message_manquant(self, actives) -> str:
        absentes = [cle for cle in actives if not source_available(self._points, cle)]
        if not absentes:
            return "Aucune donnée à tracer."
        return self._message_absence(absentes[0])

    def _message_absence(self, cle: str) -> str:
        if cle == SOURCE_ELE_SERVICE:
            return "Aucune altitude IGN : lancez « Calculer l'altitude (IGN) »."
        if cle == SOURCE_VITESSE:
            return "Aucun horodatage dans cette trace : vitesse indisponible."
        return "Aucune altitude dans le fichier de cette trace."
