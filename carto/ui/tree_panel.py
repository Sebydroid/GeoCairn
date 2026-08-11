"""Panneau de gauche : arborescence des dossiers et des traces."""

from __future__ import annotations

from PyQt6.QtCore import QSize, Qt, pyqtSignal
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QColorDialog,
    QInputDialog,
    QMenu,
    QMessageBox,
    QStyle,
    QStyleOptionViewItem,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..database import CycleError, Database, DuplicateNameError
from .icons import (
    BULB_OFF,
    BULB_ON,
    BULB_PARTIAL,
    BULB_WIDTH,
    ICON_SIZE,
    bulb_with,
)

#: L'arbre n'a qu'une colonne : l'ampoule est dessinée dans la même icône que
#: le logo du dossier ou de la trace, juste à sa gauche.
COL_BULB = 0
COL_NAME = 0

#: Rôles de données portés par les items de l'arbre (colonne 0).
ROLE_KIND = Qt.ItemDataRole.UserRole
ROLE_ID = Qt.ItemDataRole.UserRole + 1

KIND_ROOT = "root"
KIND_FOLDER = "folder"
KIND_TRACK = "track"

#: Couleurs proposées au clic droit, choisies pour rester distinctes entre
#: elles et lisibles sur un fond de carte.
COULEURS = [
    ("Bleu", "#1f5fbf"),
    ("Rouge", "#e6194b"),
    ("Vert", "#2e8b39"),
    ("Orange", "#f08c00"),
    ("Violet", "#8b2fc9"),
    ("Turquoise", "#0f9b8e"),
    ("Rose", "#e050a0"),
    ("Noir", "#202020"),
]

#: Pourcentages de transparence proposés au clic droit (0 % = opaque).
TRANSPARENCES = [0, 25, 50, 75]

#: Au-delà, la trace deviendrait introuvable sur la carte.
TRANSPARENCE_MAX = 95


def folder_of(item: QTreeWidgetItem | None) -> int | None:
    """Dossier auquel appartient un item : le premier dossier en remontant."""
    while item is not None:
        if item.data(COL_BULB, ROLE_KIND) == KIND_FOLDER:
            return item.data(COL_BULB, ROLE_ID)
        item = item.parent()
    return None


def is_self_or_descendant(candidate: QTreeWidgetItem | None,
                          ancestor: QTreeWidgetItem) -> bool:
    """Vrai si `candidate` est `ancestor` ou l'un de ses descendants."""
    while candidate is not None:
        if candidate is ancestor:
            return True
        candidate = candidate.parent()
    return False


def track_ids_under(item: QTreeWidgetItem) -> list[int]:
    """Identifiants de toutes les traces contenues dans un item, en profondeur."""
    trouvees: list[int] = []
    pile = [item]
    while pile:
        courant = pile.pop()
        if courant.data(COL_BULB, ROLE_KIND) == KIND_TRACK:
            trouvees.append(int(courant.data(COL_BULB, ROLE_ID)))
        pile.extend(courant.child(i) for i in range(courant.childCount()))
    return trouvees


class _TreeWidget(QTreeWidget):
    """QTreeWidget acceptant le dépôt d'une trace ou d'un dossier.

    Le déplacement n'est pas appliqué par Qt : il est signalé, écrit en base,
    puis l'arbre est reconstruit. Une seule source de vérité, pas de risque de
    divergence entre l'affichage et les données.

    Corollaire : dropEvent doit retenir IgnoreAction. Avec MoveAction, Qt
    supprimerait la ligne d'origine une fois dropEvent terminé, c'est-à-dire
    après notre reconstruction — l'élément déplacé disparaîtrait de l'affichage.
    """

    item_dropped = pyqtSignal(str, int, object)
    bulb_clicked = pyqtSignal(object)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)

    # --------------------------------------------------- clic sur l'ampoule

    def icon_left(self, item: QTreeWidgetItem) -> int:
        """Abscisse du bord gauche de l'icône, indentation comprise."""
        index = self.indexFromItem(item, COL_NAME)
        rect = self.visualRect(index)
        option = QStyleOptionViewItem()
        try:
            self.initViewItemOption(option)
            option.rect = rect
            decoration = self.style().subElementRect(
                QStyle.SubElement.SE_ItemViewItemDecoration, option, self
            )
            if decoration.width() > 0:
                return decoration.left()
        except (AttributeError, TypeError):
            pass
        return rect.left()

    def is_bulb_click(self, item: QTreeWidgetItem, x: int) -> bool:
        """Vrai si l'abscisse tombe sur l'ampoule plutôt que sur le reste."""
        gauche = self.icon_left(item)
        return gauche <= x < gauche + BULB_WIDTH

    def mousePressEvent(self, event) -> None:  # noqa: N802
        position = event.position().toPoint()
        item = self.itemAt(position)
        if (
            item is not None
            and event.button() == Qt.MouseButton.LeftButton
            and self.is_bulb_click(item, position.x())
        ):
            # Événement consommé : cliquer l'ampoule ne doit pas non plus
            # déplacer la sélection ni amorcer un glisser-déposer.
            self.bulb_clicked.emit(item)
            return
        super().mousePressEvent(event)

    def _dragged_item(self) -> QTreeWidgetItem | None:
        item = self.currentItem()
        if item is None or item.data(COL_BULB, ROLE_KIND) not in (
            KIND_TRACK, KIND_FOLDER
        ):
            return None
        return item

    def _drop_is_allowed(self, dragged: QTreeWidgetItem | None, target) -> bool:
        if dragged is None:
            return False
        if dragged.data(COL_BULB, ROLE_KIND) != KIND_FOLDER:
            return True
        # Déposer un dossier dans lui-même ou dans sa propre descendance
        # ferait disparaître la branche : on refuse dès le survol.
        return not is_self_or_descendant(target, dragged)

    def dragMoveEvent(self, event) -> None:  # noqa: N802
        dragged = self._dragged_item()
        target = self.itemAt(event.position().toPoint())
        if not self._drop_is_allowed(dragged, target):
            event.ignore()
            return
        event.setDropAction(Qt.DropAction.MoveAction)
        event.accept()

    def dropEvent(self, event) -> None:  # noqa: N802
        dragged = self._dragged_item()
        target = self.itemAt(event.position().toPoint())
        if not self._drop_is_allowed(dragged, target):
            event.ignore()
            return

        # Destination : le dossier visé, celui qui contient la trace visée, ou
        # la racine si le dépôt a lieu sur « Mes traces » ou dans le vide.
        kind = dragged.data(COL_BULB, ROLE_KIND)
        destination = folder_of(target)

        # IgnoreAction, surtout pas MoveAction : voir la note de classe.
        event.setDropAction(Qt.DropAction.IgnoreAction)
        event.accept()
        self.item_dropped.emit(
            kind, int(dragged.data(COL_BULB, ROLE_ID)), destination
        )


class TreePanel(QWidget):
    """Arborescence de la bibliothèque de traces, alimentée par la base."""

    track_activated = pyqtSignal(int)
    selection_changed = pyqtSignal(str, object)
    export_requested = pyqtSignal(int)
    status_message = pyqtSignal(str)
    resume_requested = pyqtSignal(int)
    duplicate_requested = pyqtSignal(int)
    merge_requested = pyqtSignal(int)

    #: Affichage sur la carte : (kind, identifiant)
    visibility_toggled = pyqtSignal(str, object)
    show_requested = pyqtSignal(str, object)
    show_only_requested = pyqtSignal(str, object)
    hide_requested = pyqtSignal(str, object)
    zoom_requested = pyqtSignal(str, object)
    style_changed = pyqtSignal(int)
    tracks_removed = pyqtSignal(list)
    reverse_requested = pyqtSignal(int)
    elevation_requested = pyqtSignal(int)

    def __init__(
        self,
        db: Database,
        visible_tracks: set[int] | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.db = db
        #: Ensemble partagé avec la fenêtre : les traces visibles sur la carte.
        self.visible_tracks = visible_tracks if visible_tracks is not None else set()

        self.tree = _TreeWidget(self)
        self.tree.setHeaderLabel("Bibliothèque")
        # Sans cela, l'icône composite (ampoule + logo) serait ramenée à la
        # largeur d'une icône simple, donc écrasée.
        self.tree.setIconSize(QSize(BULB_WIDTH + ICON_SIZE, ICON_SIZE))
        self.tree.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tree.setUniformRowHeights(True)
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.itemDoubleClicked.connect(self._on_double_click)
        self.tree.bulb_clicked.connect(self._on_bulb_clicked)
        self.tree.currentItemChanged.connect(self._on_current_changed)
        self.tree.customContextMenuRequested.connect(self._show_context_menu)
        self.tree.item_dropped.connect(self._on_item_dropped)

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
        root.setData(COL_BULB, ROLE_KIND, KIND_ROOT)
        root.setData(COL_BULB, ROLE_ID, None)
        root.setFlags(root.flags() & ~Qt.ItemFlag.ItemIsDragEnabled)

        self._populate(root, None)
        root.setExpanded(True)

        self._restore_state(expanded, selected)
        self.refresh_bulbs()

    def _populate(self, parent_item: QTreeWidgetItem, folder_id: int | None) -> None:
        """Ajoute récursivement sous-dossiers puis traces d'un dossier."""
        for folder in self.db.list_folders(folder_id):
            item = QTreeWidgetItem(parent_item, [folder.name])
            item.setData(COL_BULB, ROLE_KIND, KIND_FOLDER)
            item.setData(COL_BULB, ROLE_ID, folder.id)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsDragEnabled)
            self._populate(item, folder.id)

        for track in self.db.list_tracks(folder_id):
            label = f"{track.name}  ({track.point_count} pts)"
            item = QTreeWidgetItem(parent_item, [label])
            item.setData(COL_BULB, ROLE_KIND, KIND_TRACK)
            item.setData(COL_BULB, ROLE_ID, track.id)
            item.setForeground(COL_NAME, QColor(track.color))
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsDragEnabled)

    # ------------------------------------------------------------- ampoules

    def refresh_bulbs(self) -> None:
        """Met à jour les ampoules sans reconstruire l'arbre."""
        for item in self._iter_items():
            kind = item.data(COL_BULB, ROLE_KIND)
            if kind == KIND_TRACK:
                visible = int(item.data(COL_BULB, ROLE_ID)) in self.visible_tracks
                etat = BULB_ON if visible else BULB_OFF
                base = self._track_icon
            else:
                etat = self.folder_state(item)
                base = self._folder_icon
            item.setIcon(COL_NAME, bulb_with(etat, base))

    def folder_state(self, item: QTreeWidgetItem) -> str:
        """État d'affichage d'un dossier : toutes, certaines ou aucune trace."""
        traces = track_ids_under(item)
        if not traces:
            return BULB_OFF
        visibles = sum(1 for t in traces if t in self.visible_tracks)
        if visibles == 0:
            return BULB_OFF
        if visibles == len(traces):
            return BULB_ON
        return BULB_PARTIAL

    def _on_bulb_clicked(self, item: QTreeWidgetItem) -> None:
        self.visibility_toggled.emit(
            item.data(COL_BULB, ROLE_KIND), item.data(COL_BULB, ROLE_ID)
        )

    # ------------------------------------------------------------ sélection

    def current_selection(self) -> tuple[str, int | None]:
        """(kind, id) de l'item courant ; ('root', None) par défaut."""
        item = self.tree.currentItem()
        if item is None:
            return (KIND_ROOT, None)
        return (item.data(COL_BULB, ROLE_KIND), item.data(COL_BULB, ROLE_ID))

    def current_folder_id(self) -> int | None:
        """Dossier de destination pour une nouvelle création."""
        return folder_of(self.tree.currentItem())

    def find_item(self, kind: str, ident: int | None) -> QTreeWidgetItem | None:
        for item in self._iter_items():
            if (
                item.data(COL_BULB, ROLE_KIND),
                item.data(COL_BULB, ROLE_ID),
            ) == (kind, ident):
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
            item.data(COL_BULB, ROLE_ID)
            for item in self._iter_items()
            if item.isExpanded()
            and item.data(COL_BULB, ROLE_KIND) == KIND_FOLDER
        }

    def _restore_state(self, expanded: set[int], selected: tuple[str, int | None]) -> None:
        for item in self._iter_items():
            kind = item.data(COL_BULB, ROLE_KIND)
            ident = item.data(COL_BULB, ROLE_ID)
            if kind == KIND_FOLDER and ident in expanded:
                item.setExpanded(True)
            if (kind, ident) == selected:
                self.tree.setCurrentItem(item)

    # ------------------------------------------------------ menu contextuel

    def _show_context_menu(self, position) -> None:
        item = self.tree.itemAt(position)
        if item is not None:
            self.tree.setCurrentItem(item)
        kind, ident = self.current_selection()

        # Les lambdas sont nécessaires : triggered() transmet un booléen
        # « checked » qui serait reçu comme premier argument (donc comme un nom
        # de dossier, ou comme confirm=False sur une suppression).
        menu = QMenu(self)

        if kind in (KIND_FOLDER, KIND_TRACK, KIND_ROOT):
            cible = "le dossier" if kind != KIND_TRACK else "la trace"
            if kind == KIND_ROOT:
                cible = "tout"
            menu.addAction(
                "Afficher",
                lambda: self.show_requested.emit(kind, ident),
            )
            menu.addAction(
                "Afficher seulement ceci",
                lambda: self.show_only_requested.emit(kind, ident),
            )
            menu.addAction(
                "Masquer", lambda: self.hide_requested.emit(kind, ident)
            )
            menu.addAction(
                f"Zoom sur {cible}",
                lambda: self.zoom_requested.emit(kind, ident),
            )
            menu.addSeparator()

        menu.addAction("Nouveau dossier…", lambda: self.create_folder())

        if kind == KIND_FOLDER:
            menu.addSeparator()
            menu.addAction("Renommer le dossier…", lambda: self.rename_selected())
            menu.addAction("Supprimer le dossier", lambda: self.delete_selected())
        elif kind == KIND_TRACK:
            menu.addMenu(self._build_color_menu(int(ident), menu))
            menu.addSeparator()
            menu.addAction(
                "Modifier la trace",
                lambda: self._emit_for_track(self.resume_requested),
            )
            menu.addAction(
                "Inverser le sens",
                lambda: self._emit_for_track(self.reverse_requested),
            )
            menu.addAction(
                "Calculer l'altitude (IGN)",
                lambda: self._emit_for_track(self.elevation_requested),
            )
            menu.addAction(
                "Dupliquer la trace",
                lambda: self._emit_for_track(self.duplicate_requested),
            )
            menu.addAction(
                "Fusionner avec…",
                lambda: self._emit_for_track(self.merge_requested),
            )
            menu.addSeparator()
            menu.addAction("Exporter en GPX…", self._request_export)
            menu.addAction("Renommer la trace…", lambda: self.rename_selected())
            menu.addAction("Supprimer la trace", lambda: self.delete_selected())

        menu.exec(self.tree.viewport().mapToGlobal(position))

    def _build_color_menu(self, track_id: int, parent: QMenu) -> QMenu:
        menu = QMenu("Couleur", parent)
        for nom, valeur in COULEURS:
            action = menu.addAction(nom)
            action.setIcon(self._color_swatch(valeur))
            action.triggered.connect(
                lambda _checked=False, c=valeur: self.set_track_color(track_id, c)
            )
        menu.addSeparator()
        menu.addMenu(self._build_transparency_menu(track_id, menu))
        menu.addAction(
            "Couleur personnalisée…",
            lambda: self.choose_track_color(track_id),
        )
        return menu

    def _build_transparency_menu(self, track_id: int, parent: QMenu) -> QMenu:
        """Transparence exprimée en pourcentage : 0 % = trace opaque."""
        menu = QMenu("Transparence", parent)
        track = self.db.get_track(track_id)
        actuel = (
            round((1.0 - track.opacity) * 100) if track is not None else 0
        )
        for pourcentage in TRANSPARENCES:
            libelle = f"{pourcentage} %"
            if pourcentage == 0:
                libelle += " (opaque)"
            action = menu.addAction(libelle)
            action.setCheckable(True)
            action.setChecked(pourcentage == actuel)
            action.triggered.connect(
                lambda _checked=False, p=pourcentage: self.set_track_transparency(
                    track_id, p
                )
            )
        menu.addSeparator()
        menu.addAction(
            "Autre pourcentage…",
            lambda: self.choose_track_transparency(track_id),
        )
        return menu

    def _color_swatch(self, couleur: str):
        from PyQt6.QtGui import QIcon, QPixmap

        pixmap = QPixmap(14, 14)
        pixmap.fill(QColor(couleur))
        return QIcon(pixmap)

    def _request_export(self) -> None:
        self._emit_for_track(self.export_requested)

    def _emit_for_track(self, signal) -> None:
        """Émet `signal` avec l'identifiant de la trace sélectionnée."""
        kind, ident = self.current_selection()
        if kind == KIND_TRACK:
            signal.emit(int(ident))

    # ------------------------------------------------- couleur des traces

    def set_track_color(
        self, track_id: int, color: str, opacity: float | None = None
    ) -> bool:
        """Applique une couleur (et éventuellement une transparence)."""
        track = self.db.get_track(track_id)
        if track is None:
            return False
        self.db.set_track_style(track_id, color=color, opacity=opacity)
        item = self.find_item(KIND_TRACK, track_id)
        if item is not None:
            item.setForeground(COL_NAME, QColor(color))
        self.style_changed.emit(track_id)
        self.status_message.emit(f"Couleur de « {track.name} » modifiée.")
        return True

    def set_track_transparency(self, track_id: int, pourcentage: int) -> bool:
        """Applique une transparence exprimée en pourcentage (0 = opaque)."""
        track = self.db.get_track(track_id)
        if track is None:
            return False
        pourcentage = max(0, min(TRANSPARENCE_MAX, int(pourcentage)))
        self.db.set_track_style(track_id, opacity=1.0 - pourcentage / 100)
        self.style_changed.emit(track_id)
        self.status_message.emit(
            f"« {track.name} » : transparence {pourcentage} %."
        )
        return True

    def choose_track_transparency(self, track_id: int) -> bool:
        """Demande un pourcentage de transparence à l'utilisateur."""
        track = self.db.get_track(track_id)
        if track is None:
            return False
        actuel = round((1.0 - track.opacity) * 100)
        pourcentage, accepte = QInputDialog.getInt(
            self,
            f"Transparence de « {track.name} »",
            "Transparence en % (0 = opaque) :",
            actuel,
            0,
            TRANSPARENCE_MAX,
            5,
        )
        if not accepte:
            return False
        return self.set_track_transparency(track_id, pourcentage)

    def choose_track_color(self, track_id: int) -> bool:
        """Ouvre le sélecteur de couleur. La transparence a son propre menu."""
        track = self.db.get_track(track_id)
        if track is None:
            return False

        choisie = QColorDialog.getColor(
            QColor(track.color), self, f"Couleur de « {track.name} »"
        )
        if not choisie.isValid():
            return False

        return self.set_track_color(track_id, choisie.name())

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
            item = self.find_item(KIND_FOLDER, ident)
            disparues = track_ids_under(item) if item is not None else []
            self.db.delete_folder(ident)
        else:
            disparues = [int(ident)]
            self.db.delete_track(ident)

        # Les traces supprimées doivent aussi disparaître de la carte.
        for track_id in disparues:
            self.visible_tracks.discard(track_id)
        if disparues:
            self.tracks_removed.emit(disparues)

        self.refresh()
        self.status_message.emit("Suppression effectuée.")
        return True

    def _on_item_dropped(self, kind: str, ident: int, folder_id: int | None) -> None:
        if kind == KIND_TRACK:
            self.move_track(ident, folder_id)
        elif kind == KIND_FOLDER:
            self.move_folder(ident, folder_id)

    def move_folder(self, folder_id: int, parent_id: int | None) -> bool:
        """Déplace un dossier sous un autre parent (glisser-déposer)."""
        folder = self.db.get_folder(folder_id)
        if folder is None or folder.parent_id == parent_id:
            return False

        try:
            self.db.move_folder(folder_id, parent_id)
        except CycleError as exc:
            QMessageBox.warning(self, "Déplacement impossible", str(exc))
            return False
        except DuplicateNameError as exc:
            QMessageBox.warning(self, "Nom déjà utilisé", str(exc))
            return False

        self.refresh()
        self.select_folder(folder_id)

        destination = "Mes traces"
        if parent_id is not None:
            destination = self.db.get_folder(parent_id).name
        self.status_message.emit(
            f"Dossier « {folder.name} » déplacé vers « {destination} »."
        )
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
        if item.data(COL_BULB, ROLE_KIND) == KIND_TRACK:
            self.track_activated.emit(int(item.data(COL_BULB, ROLE_ID)))

    def _on_current_changed(self, current, _previous) -> None:
        if current is None:
            self.selection_changed.emit(KIND_ROOT, None)
        else:
            self.selection_changed.emit(
                current.data(COL_BULB, ROLE_KIND),
                current.data(COL_BULB, ROLE_ID),
            )
