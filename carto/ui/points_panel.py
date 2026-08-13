"""Panneau listant les points de la trace en cours d'édition (Jalon 6).

Permet de désigner un point précis, d'en sélectionner plusieurs pour les
supprimer, et de choisir l'endroit où découper la trace.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..editor import DraftTrack
from ..geo import cumulative_distances, format_length
from .widgets import ElidedLabel


def format_elevation(ele: float | None, ele_service: float | None = None) -> str:
    """Altitude lisible.

    Celle du fichier est prioritaire ; celle calculée par l'IGN prend le relais,
    signalée par « ~ » pour qu'on ne confonde pas les deux.
    """
    if ele is not None:
        return f"{ele:.0f} m"
    if ele_service is not None:
        return f"~{ele_service:.0f} m"
    return "—"


class PointsPanel(QWidget):
    """Liste des points du brouillon, avec suppression et découpage."""

    point_selected = pyqtSignal(int)
    points_selected = pyqtSignal(list)
    delete_requested = pyqtSignal(list)
    split_requested = pyqtSignal(int)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)

        self.title = ElidedLabel("Points de la trace", self)
        self.header = ElidedLabel(
            "   n°       latitude ; longitude    altitude    distance", self
        )
        self.header.setEnabled(False)
        self.list = QListWidget(self)
        self.list.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection
        )
        self.list.setUniformItemSizes(True)
        self.list.itemSelectionChanged.connect(self._on_selection_changed)

        self.delete_button = QPushButton("Supprimer", self)
        self.delete_button.setToolTip(
            "Supprimer les points sélectionnés (Suppr)"
        )
        self.delete_button.clicked.connect(self._request_delete)

        self.split_button = QPushButton("Découper ici", self)
        self.split_button.setToolTip(
            "Couper la trace en deux au point sélectionné"
        )
        self.split_button.clicked.connect(self._request_split)

        buttons = QHBoxLayout()
        buttons.setContentsMargins(0, 0, 0, 0)
        buttons.addWidget(self.delete_button)
        buttons.addWidget(self.split_button)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addWidget(self.title)
        layout.addWidget(self.header)
        layout.addWidget(self.list)
        layout.addLayout(buttons)

        self._updating = False
        self._editable = True
        #: Sélection posée par le programme, à ne pas renvoyer aux autres vues.
        self._silencieux: list[int] | None = None
        self.refresh(DraftTrack())

    # -------------------------------------------------------------- contenu

    def refresh(self, draft: DraftTrack) -> None:
        """Reconstruit la liste à partir du brouillon en cours d'édition."""
        if draft.is_empty:
            titre = "Points de la trace"
        elif draft.is_existing:
            titre = f"« {draft.name} » — {len(draft)} points"
        else:
            titre = f"Brouillon — {len(draft)} points"
        self._fill(draft.points, titre, editable=True)

    def show_points(self, points, nom: str = "") -> None:
        """Affiche les points d'une trace consultée, hors mode édition.

        La liste reste lisible et sélectionnable ; seules les modifications
        sont hors de portée tant que la trace n'est pas reprise.
        """
        titre = (
            f"« {nom} » — {len(points)} points (consultation)"
            if nom
            else "Points de la trace"
        )
        self._fill(points, titre, editable=False)

    def _fill(self, points, titre: str, editable: bool) -> None:
        selection = self.selected_indexes()
        self._editable = editable

        distances = cumulative_distances(points)

        self._updating = True
        self.list.clear()
        # Les lignes sont ajoutées d'un bloc : ajoutées une à une, chacune
        # relance la mise en page et la barre de défilement de la liste. Sur une
        # trace de vingt mille points, déplacer un seul repère figeait
        # l'interface une seconde et demie.
        self.list.addItems(
            [
                f"{index + 1:>4}   {point.lat:.5f} ; {point.lon:.5f}"
                f"   {format_elevation(point.ele, point.ele_service):>8}"
                f"   {format_length(distances[index]):>9}"
                for index, point in enumerate(points)
            ]
        )
        self._updating = False

        self.title.setText(titre)
        self._restore_selection(selection)
        self._update_buttons()

    def _restore_selection(self, indexes: list[int]) -> None:
        self._updating = True
        retenus = [i for i in indexes if 0 <= i < self.list.count()]
        for index in retenus:
            self.list.item(index).setSelected(True)
        self._silencieux = retenus
        self._updating = False

    # ------------------------------------------------------------ sélection

    def selected_indexes(self) -> list[int]:
        return sorted(self.list.row(item) for item in self.list.selectedItems())

    def select_index(self, index: int) -> None:
        """Sélectionne un point depuis l'extérieur (carte ou profil)."""
        if not 0 <= index < self.list.count():
            return
        self._updating = True
        self.list.clearSelection()
        self.list.setCurrentRow(index)
        self._silencieux = [index]
        self._updating = False
        self.list.scrollToItem(self.list.item(index))
        self._update_buttons()

    def _on_selection_changed(self) -> None:
        self._update_buttons()
        indexes = self.selected_indexes()

        # Une sélection posée par le programme ne doit pas repartir vers la
        # carte : Qt émet parfois ce signal en différé, après la retombée du
        # drapeau, d'où la comparaison sur la valeur elle-même.
        if self._updating or indexes == self._silencieux:
            self._silencieux = None
            return

        self._silencieux = None
        if len(indexes) == 1:
            self.point_selected.emit(indexes[0])
        elif indexes:
            self.points_selected.emit(indexes)

    def _update_buttons(self) -> None:
        indexes = self.selected_indexes()
        self.delete_button.setEnabled(self._editable and bool(indexes))
        # Découper n'a de sens qu'en un point unique, hors extrémités.
        self.split_button.setEnabled(
            self._editable
            and len(indexes) == 1
            and 1 <= indexes[0] <= self.list.count() - 2
        )

    # -------------------------------------------------------------- actions

    def _request_delete(self) -> None:
        indexes = self.selected_indexes()
        if indexes:
            self.delete_requested.emit(indexes)

    def _request_split(self) -> None:
        indexes = self.selected_indexes()
        if len(indexes) == 1:
            self.split_requested.emit(indexes[0])

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() == Qt.Key.Key_Delete:
            self._request_delete()
            return
        super().keyPressEvent(event)
