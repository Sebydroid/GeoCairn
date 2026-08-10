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


class PointsPanel(QWidget):
    """Liste des points du brouillon, avec suppression et découpage."""

    point_selected = pyqtSignal(int)
    delete_requested = pyqtSignal(list)
    split_requested = pyqtSignal(int)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)

        self.title = QLabel("Points de la trace", self)
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
        layout.addWidget(self.list)
        layout.addLayout(buttons)

        self._updating = False
        self.refresh(DraftTrack())

    # -------------------------------------------------------------- contenu

    def refresh(self, draft: DraftTrack) -> None:
        """Reconstruit la liste à partir du brouillon."""
        selection = self.selected_indexes()

        self._updating = True
        self.list.clear()
        for index, point in enumerate(draft.points, start=0):
            self.list.addItem(
                f"{index + 1:>4}   {point.lat:.5f} ; {point.lon:.5f}"
            )
        self._updating = False

        if draft.is_empty:
            self.title.setText("Points de la trace")
        elif draft.is_existing:
            self.title.setText(f"« {draft.name} » — {len(draft)} points")
        else:
            self.title.setText(f"Brouillon — {len(draft)} points")

        self._restore_selection(selection)
        self._update_buttons()

    def _restore_selection(self, indexes: list[int]) -> None:
        self._updating = True
        for index in indexes:
            if 0 <= index < self.list.count():
                self.list.item(index).setSelected(True)
        self._updating = False

    # ------------------------------------------------------------ sélection

    def selected_indexes(self) -> list[int]:
        return sorted(self.list.row(item) for item in self.list.selectedItems())

    def select_index(self, index: int) -> None:
        """Sélectionne un point depuis l'extérieur (clic sur la carte)."""
        if not 0 <= index < self.list.count():
            return
        self._updating = True
        self.list.clearSelection()
        self.list.setCurrentRow(index)
        self._updating = False
        self.list.scrollToItem(self.list.item(index))
        self._update_buttons()

    def _on_selection_changed(self) -> None:
        self._update_buttons()
        if self._updating:
            return
        indexes = self.selected_indexes()
        if len(indexes) == 1:
            self.point_selected.emit(indexes[0])

    def _update_buttons(self) -> None:
        indexes = self.selected_indexes()
        self.delete_button.setEnabled(bool(indexes))
        # Découper n'a de sens qu'en un point unique, hors extrémités.
        self.split_button.setEnabled(
            len(indexes) == 1 and 1 <= indexes[0] <= self.list.count() - 2
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
