"""Panneau de gauche : arborescence des dossiers et des traces."""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QInputDialog,
    QMenu,
    QMessageBox,
    QStyle,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..database import Database, DuplicateNameError

#: Rôles de données portés par les items de l'arbre.
ROLE_KIND = Qt.ItemDataRole.UserRole
ROLE_ID = Qt.ItemDataRole.UserRole + 1

KIND_ROOT = "root"
KIND_FOLDER = "folder"
KIND_TRACK = "track"


def folder_of(item: QTreeWidgetItem | None) -> int | None:
    """Dossier auquel appartient un item : le premier dossier en remontant."""
    while item is not None:
        if item.data(0, ROLE_KIND) == KIND_FOLDER:
            return item.data(0, ROLE_ID)
        item = item.parent()
    return None


class _TreeWidget(QTreeWidget):
    """QTreeWidget acceptant le dépôt d'une trace sur un dossier.

    Le déplacement n'est pas appliqué par Qt : il est signalé, écrit en base,
    puis l'arbre est reconstruit. Une seule source de vérité, pas de risque de
    divergence entre l'affichage et les données.
    """

    track_dropped = pyqtSignal(int, object)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)

    def _dragged_track_id(self) -> int | None:
        item = self.currentItem()
        if item is None or item.data(0, ROLE_KIND) != KIND_TRACK:
            return None
        return int(item.data(0, ROLE_ID))

    def dragMoveEvent(self, event) -> None:  # noqa: N802
        if self._dragged_track_id() is None:
            event.ignore()
            return
        event.setDropAction(Qt.DropAction.MoveAction)
        event.accept()

    def dropEvent(self, event) -> None:  # noqa: N802
        track_id = self._dragged_track_id()
        if track_id is None:
            event.ignore()
            return
        target = self.itemAt(event.position().toPoint())
        event.setDropAction(Qt.DropAction.MoveAction)
        event.accept()
        self.track_dropped.emit(track_id, folder_of(target))


class TreePanel(QWidget):
    """Arborescence de la bibliothèque de traces, alimentée par la base."""

    track_activated = pyqtSignal(int)
    selection_changed = pyqtSignal(str, object)
    export_requested = pyqtSignal(int)
    status_message = pyqtSignal(str)

    def __init__(self, db: Database, parent=None) -> None:
        super().__init__(parent)
        self.db = db

        self.tree = _TreeWidget(self)
        self.tree.setHeaderLabel("Bibliothèque")
        self.tree.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tree.setUniformRowHeights(True)
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.itemDoubleClicked.connect(self._on_double_click)
        self.tree.currentItemChanged.connect(self._on_current_changed)
        self.tree.customContextMenuRequested.connect(self._show_context_menu)
        self.tree.track_dropped.connect(self.move_track)

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
        root.setFlags(root.flags() & ~Qt.ItemFlag.ItemIsDragEnabled)

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
            # Seules les traces se déplacent par glisser-déposer.
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsDragEnabled)
            self._populate(item, folder.id)

        for track in self.db.list_tracks(folder_id):
            label = f"{track.name}  ({track.point_count} pts)"
            item = QTreeWidgetItem(parent_item, [label])
            item.setData(0, ROLE_KIND, KIND_TRACK)
            item.setData(0, ROLE_ID, track.id)
            item.setIcon(0, self._track_icon)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsDragEnabled)

    # ------------------------------------------------------------ sélection

    def current_selection(self) -> tuple[str, int | None]:
        """(kind, id) de l'item courant ; ('root', None) par défaut."""
        item = self.tree.currentItem()
        if item is None:
            return (KIND_ROOT, None)
        return (item.data(0, ROLE_KIND), item.data(0, ROLE_ID))

    def current_folder_id(self) -> int | None:
        """Dossier de destination pour une nouvelle création."""
        return folder_of(self.tree.currentItem())

    def find_item(self, kind: str, ident: int | None) -> QTreeWidgetItem | None:
        for item in self._iter_items():
            if (item.data(0, ROLE_KIND), item.data(0, ROLE_ID)) == (kind, ident):
                return item
        return None

    def select_track(self, track_id: int) -> bool:
        """Sélectionne une trace et déplie ses dossiers parents."""
        return self._select(KIND_TRACK, track_id)

    def select_folder(self, folder_id: int | None) -> bool:
        if folder_id is None:
            return self._select(KIND_ROOT, None)
        return self._select(KIND_FOLDER, folder_id)

    def _select(self, kind: str, ident: int | None) -> bool:
        item = self.find_item(kind, ident)
        if item is None:
            return False
        parent = item.parent()
        while parent is not None:
            parent.setExpanded(True)
            parent = parent.parent()
        self.tree.setCurrentItem(item)
        return True

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

    # ------------------------------------------------------ menu contextuel

    def _show_context_menu(self, position) -> None:
        item = self.tree.itemAt(position)
        if item is not None:
            self.tree.setCurrentItem(item)
        kind, _ident = self.current_selection()

        # Les lambdas sont nécessaires : triggered() transmet un booléen
        # « checked » qui serait reçu comme premier argument (donc comme un nom
        # de dossier, ou comme confirm=False sur une suppression).
        menu = QMenu(self)
        menu.addAction("Nouveau dossier…", lambda: self.create_folder())

        if kind == KIND_FOLDER:
            menu.addSeparator()
            menu.addAction("Renommer le dossier…", lambda: self.rename_selected())
            menu.addAction("Supprimer le dossier", lambda: self.delete_selected())
        elif kind == KIND_TRACK:
            menu.addSeparator()
            menu.addAction("Exporter en GPX…", self._request_export)
            menu.addAction("Renommer la trace…", lambda: self.rename_selected())
            menu.addAction("Supprimer la trace", lambda: self.delete_selected())

        menu.exec(self.tree.viewport().mapToGlobal(position))

    def _request_export(self) -> None:
        kind, ident = self.current_selection()
        if kind == KIND_TRACK:
            self.export_requested.emit(int(ident))

    # --------------------------------------------------------- opérations

    def create_folder(self, name: str | None = None) -> int | None:
        """Crée un sous-dossier dans le dossier sélectionné.

        `name` sert aux tests ; sans lui, l'utilisateur est invité à le saisir.
        """
        parent_id = self.current_folder_id()
        if name is None:
            name, accepted = QInputDialog.getText(
                self, "Nouveau dossier", "Nom du dossier :"
            )
            if not accepted or not name.strip():
                return None

        try:
            folder_id = self.db.create_folder(name, parent_id)
        except DuplicateNameError as exc:
            QMessageBox.warning(self, "Nom déjà utilisé", str(exc))
            return None
        except ValueError as exc:
            QMessageBox.warning(self, "Nom invalide", str(exc))
            return None

        self.refresh()
        self.select_folder(folder_id)
        self.status_message.emit(f"Dossier « {name} » créé.")
        return folder_id

    def rename_selected(self, name: str | None = None) -> bool:
        """Renomme le dossier ou la trace sélectionné."""
        kind, ident = self.current_selection()
        if kind not in (KIND_FOLDER, KIND_TRACK):
            return False

        if kind == KIND_FOLDER:
            current = self.db.get_folder(ident).name
            titre, libelle = "Renommer le dossier", "Nouveau nom :"
        else:
            current = self.db.get_track(ident).name
            titre, libelle = "Renommer la trace", "Nouveau nom :"

        if name is None:
            name, accepted = QInputDialog.getText(
                self, titre, libelle, text=current
            )
            if not accepted or not name.strip() or name == current:
                return False

        try:
            if kind == KIND_FOLDER:
                self.db.rename_folder(ident, name)
            else:
                self.db.rename_track(ident, name)
        except DuplicateNameError as exc:
            QMessageBox.warning(self, "Nom déjà utilisé", str(exc))
            return False
        except ValueError as exc:
            QMessageBox.warning(self, "Nom invalide", str(exc))
            return False

        self.refresh()
        self._select(kind, ident)
        self.status_message.emit(f"Renommé en « {name} ».")
        return True

    def delete_selected(self, confirm: bool = True) -> bool:
        """Supprime le dossier (et son contenu) ou la trace sélectionné."""
        kind, ident = self.current_selection()
        if kind not in (KIND_FOLDER, KIND_TRACK):
            return False

        if kind == KIND_FOLDER:
            folder = self.db.get_folder(ident)
            question = (
                f"Supprimer le dossier « {folder.name} » ainsi que tous les "
                "sous-dossiers et traces qu'il contient ?"
            )
        else:
            track = self.db.get_track(ident)
            question = f"Supprimer la trace « {track.name} » ?"

        if confirm:
            answer = QMessageBox.question(
                self,
                "Confirmer la suppression",
                question,
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return False

        if kind == KIND_FOLDER:
            self.db.delete_folder(ident)
        else:
            self.db.delete_track(ident)

        self.refresh()
        self.status_message.emit("Suppression effectuée.")
        return True

    def move_track(self, track_id: int, folder_id: int | None) -> bool:
        """Déplace une trace dans un autre dossier (glisser-déposer)."""
        track = self.db.get_track(track_id)
        if track is None or track.folder_id == folder_id:
            return False

        self.db.move_track(track_id, folder_id)
        self.refresh()
        self.select_track(track_id)

        destination = "Mes traces"
        if folder_id is not None:
            destination = self.db.get_folder(folder_id).name
        self.status_message.emit(
            f"« {track.name} » déplacée vers « {destination} »."
        )
        return True

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
