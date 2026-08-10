"""Panneau de gauche : arborescence des dossiers et des traces."""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QStyle,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..database import Database

#: Rôles de données portés par les items de l'arbre.
ROLE_KIND = Qt.ItemDataRole.UserRole
ROLE_ID = Qt.ItemDataRole.UserRole + 1

KIND_ROOT = "root"
KIND_FOLDER = "folder"
KIND_TRACK = "track"


class TreePanel(QWidget):
    """Arborescence de la bibliothèque de traces, alimentée par la base."""

    track_activated = pyqtSignal(int)
    selection_changed = pyqtSignal(str, object)

    def __init__(self, db: Database, parent=None) -> None:
        super().__init__(parent)
        self.db = db

        self.tree = QTreeWidget(self)
        self.tree.setHeaderLabel("Bibliothèque")
        self.tree.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tree.setUniformRowHeights(True)
        self.tree.itemDoubleClicked.connect(self._on_double_click)
        self.tree.currentItemChanged.connect(self._on_current_changed)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.tree)

        style = self.style()
        self._folder_icon = style.standardIcon(QStyle.StandardPixmap.SP_DirIcon)
        self._track_icon = style.standardIcon(QStyle.StandardPixmap.SP_FileIcon)

        self.refresh()

    # -------------------------------------------------------------- contenu

    def refresh(self) -> None:
        """Reconstruit l'arbre à partir de la base (sans doublons)."""
        expanded = self._expanded_folder_ids()
        selected = self.current_selection()

        self.tree.clear()
        root = QTreeWidgetItem(self.tree, ["Mes traces"])
        root.setData(0, ROLE_KIND, KIND_ROOT)
        root.setData(0, ROLE_ID, None)
        root.setIcon(0, self._folder_icon)

        self._populate(root, None)
        root.setExpanded(True)

        self._restore_state(expanded, selected)

    def _populate(self, parent_item: QTreeWidgetItem, folder_id: int | None) -> None:
        """Ajoute récursivement sous-dossiers puis traces d'un dossier."""
        for folder in self.db.list_folders(folder_id):
            item = QTreeWidgetItem(parent_item, [folder.name])
            item.setData(0, ROLE_KIND, KIND_FOLDER)
            item.setData(0, ROLE_ID, folder.id)
            item.setIcon(0, self._folder_icon)
            self._populate(item, folder.id)

        for track in self.db.list_tracks(folder_id):
            label = f"{track.name}  ({track.point_count} pts)"
            item = QTreeWidgetItem(parent_item, [label])
            item.setData(0, ROLE_KIND, KIND_TRACK)
            item.setData(0, ROLE_ID, track.id)
            item.setIcon(0, self._track_icon)

    # ------------------------------------------------------------ sélection

    def current_selection(self) -> tuple[str, int | None]:
        """(kind, id) de l'item courant ; ('root', None) par défaut."""
        item = self.tree.currentItem()
        if item is None:
            return (KIND_ROOT, None)
        return (item.data(0, ROLE_KIND), item.data(0, ROLE_ID))

    def current_folder_id(self) -> int | None:
        """Dossier de destination pour une nouvelle création."""
        kind, ident = self.current_selection()
        if kind == KIND_FOLDER:
            return ident
        if kind == KIND_TRACK:
            track = self.db.get_track(ident)
            return track.folder_id if track else None
        return None

    def _iter_items(self):
        stack = [self.tree.topLevelItem(i) for i in range(self.tree.topLevelItemCount())]
        while stack:
            item = stack.pop()
            yield item
            stack.extend(item.child(i) for i in range(item.childCount()))

    def _expanded_folder_ids(self) -> set[int]:
        return {
            item.data(0, ROLE_ID)
            for item in self._iter_items()
            if item.isExpanded() and item.data(0, ROLE_KIND) == KIND_FOLDER
        }

    def _restore_state(self, expanded: set[int], selected: tuple[str, int | None]) -> None:
        for item in self._iter_items():
            kind, ident = item.data(0, ROLE_KIND), item.data(0, ROLE_ID)
            if kind == KIND_FOLDER and ident in expanded:
                item.setExpanded(True)
            if (kind, ident) == selected:
                self.tree.setCurrentItem(item)

    # -------------------------------------------------------------- signaux

    def _on_double_click(self, item: QTreeWidgetItem, _column: int) -> None:
        if item.data(0, ROLE_KIND) == KIND_TRACK:
            self.track_activated.emit(int(item.data(0, ROLE_ID)))

    def _on_current_changed(self, current, _previous) -> None:
        if current is None:
            self.selection_changed.emit(KIND_ROOT, None)
        else:
            self.selection_changed.emit(
                current.data(0, ROLE_KIND), current.data(0, ROLE_ID)
            )
