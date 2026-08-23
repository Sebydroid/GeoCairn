"""Panneau de gauche : arborescence des dossiers et des traces."""

from __future__ import annotations

from PyQt6.QtCore import QSize, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QKeySequence
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

from ..database import CycleError, Database, DuplicateNameError, NotFoundError
from .icons import (
    BULB_OFF,
    BULB_ON,
    BULB_PARTIAL,
    BULB_WIDTH,
    ICON_SIZE,
    bulb_with,
)
from .toolbar_icons import toolbar_icon

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

    items_dropped = pyqtSignal(list, object)
    bulb_clicked = pyqtSignal(object)
    rename_shortcut = pyqtSignal()
    delete_shortcut = pyqtSignal()
    copy_shortcut = pyqtSignal()
    cut_shortcut = pyqtSignal()
    paste_shortcut = pyqtSignal()

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

    def keyPressEvent(self, event) -> None:  # noqa: N802
        """Raccourcis d'explorateur : F2 renomme, Suppr supprime."""
        if event.key() == Qt.Key.Key_F2:
            self.rename_shortcut.emit()
            return
        if event.key() == Qt.Key.Key_Delete:
            self.delete_shortcut.emit()
            return
        if event.matches(QKeySequence.StandardKey.Copy):
            self.copy_shortcut.emit()
            return
        if event.matches(QKeySequence.StandardKey.Cut):
            self.cut_shortcut.emit()
            return
        if event.matches(QKeySequence.StandardKey.Paste):
            self.paste_shortcut.emit()
            return
        super().keyPressEvent(event)

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

    def dragged_items(self) -> list[QTreeWidgetItem]:
        """Éléments emportés par le glisser : toute la sélection.

        Un élément dont un ancêtre est lui aussi sélectionné est écarté : le
        déplacer séparément le sortirait du dossier qui l'emmène.
        """
        selection = [
            item
            for item in self.selectedItems()
            if item.data(COL_BULB, ROLE_KIND) in (KIND_TRACK, KIND_FOLDER)
        ]
        courant = self.currentItem()
        if not selection and courant is not None:
            if courant.data(COL_BULB, ROLE_KIND) in (KIND_TRACK, KIND_FOLDER):
                selection = [courant]

        retenus = []
        for item in selection:
            parent = item.parent()
            if not any(is_self_or_descendant(parent, autre) for autre in selection):
                retenus.append(item)
        return retenus

    def _drop_is_allowed(self, dragged: list[QTreeWidgetItem], target) -> bool:
        if not dragged:
            return False
        for item in dragged:
            if item.data(COL_BULB, ROLE_KIND) != KIND_FOLDER:
                continue
            # Déposer un dossier dans lui-même ou dans sa propre descendance
            # ferait disparaître la branche : on refuse dès le survol.
            if is_self_or_descendant(target, item):
                return False
        return True

    def dragMoveEvent(self, event) -> None:  # noqa: N802
        target = self.itemAt(event.position().toPoint())
        if not self._drop_is_allowed(self.dragged_items(), target):
            event.ignore()
            return
        event.setDropAction(Qt.DropAction.MoveAction)
        event.accept()

    def dropEvent(self, event) -> None:  # noqa: N802
        dragged = self.dragged_items()
        target = self.itemAt(event.position().toPoint())
        if not self._drop_is_allowed(dragged, target):
            event.ignore()
            return

        # Destination : le dossier visé, celui qui contient la trace visée, ou
        # la racine si le dépôt a lieu sur « Mes traces » ou dans le vide.
        deplaces = [
            (item.data(COL_BULB, ROLE_KIND), int(item.data(COL_BULB, ROLE_ID)))
            for item in dragged
        ]
        destination = folder_of(target)

        # IgnoreAction, surtout pas MoveAction : voir la note de classe.
        event.setDropAction(Qt.DropAction.IgnoreAction)
        event.accept()
        self.items_dropped.emit(deplaces, destination)


class TreePanel(QWidget):
    """Arborescence de la bibliothèque de traces, alimentée par la base."""

    track_activated = pyqtSignal(int)
    selection_changed = pyqtSignal(str, object)
    #: L'étendue de la sélection a changé — un élément, ou plusieurs. Distinct
    #: de `selection_changed`, qui ne suit que l'élément courant : c'est le
    #: nombre d'éléments retenus qui décide des actions grisées.
    selection_count_changed = pyqtSignal()
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
    decimate_requested = pyqtSignal(int)

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
        # Comme un explorateur de fichiers : Ctrl et Maj étendent la sélection.
        self.tree.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection
        )
        self.tree.setUniformRowHeights(True)
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.itemDoubleClicked.connect(self._on_double_click)
        self.tree.bulb_clicked.connect(self._on_bulb_clicked)
        self.tree.rename_shortcut.connect(lambda: self.rename_selected())
        self.tree.delete_shortcut.connect(lambda: self.delete_selected())
        self.tree.currentItemChanged.connect(self._on_current_changed)
        self.tree.itemSelectionChanged.connect(self.selection_count_changed)
        self.tree.customContextMenuRequested.connect(self._show_context_menu)
        self.tree.items_dropped.connect(self._on_items_dropped)
        self.tree.copy_shortcut.connect(lambda: self.copy_selection())
        self.tree.cut_shortcut.connect(self.cut_selection)
        self.tree.paste_shortcut.connect(self.paste)

        #: Presse-papiers interne : (mode, [(kind, id), ...])
        self._clipboard: tuple[str, list] = ("copier", [])

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.tree)

        style = self.style()
        self._folder_icon = style.standardIcon(QStyle.StandardPixmap.SP_DirIcon)
        # Icônes dessinées : celles du système sont parfois vides selon le thème.
        self._track_icon = toolbar_icon("trace")
        self._editing_icon = toolbar_icon("crayon")
        #: Trace actuellement ouverte en modification, signalée par un crayon.
        self.editing_track_id: int | None = None

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
            item = QTreeWidgetItem(parent_item, [track.name])
            item.setToolTip(COL_NAME, f"{track.name} — {track.point_count} points")
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
                ident = int(item.data(COL_BULB, ROLE_ID))
                visible = ident in self.visible_tracks
                etat = BULB_ON if visible else BULB_OFF
                base = (
                    self._editing_icon
                    if ident == self.editing_track_id
                    else self._track_icon
                )
            else:
                etat = self.folder_state(item)
                base = self._folder_icon
            item.setIcon(COL_NAME, bulb_with(etat, base))

    def set_editing_track(self, track_id: int | None) -> None:
        """Signale d'un crayon la trace ouverte en modification."""
        if self.editing_track_id == track_id:
            return
        self.editing_track_id = track_id
        self.refresh_bulbs()

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
        menu = self.build_context_menu(self.tree.itemAt(position))
        menu.exec(self.tree.viewport().mapToGlobal(position))

    def build_context_menu(self, item: QTreeWidgetItem | None) -> QMenu:
        """Construit le menu du clic droit, sans l'afficher.

        Séparé de son affichage pour que les tests puissent lire ce qu'il
        contient et ce qui y est grisé : `exec` bloquerait jusqu'à un clic.
        """
        # Un clic droit sur un élément déjà retenu ne doit pas réduire la
        # sélection à lui seul : `setCurrentItem` sélectionne, et l'utilisateur
        # perdait ainsi les autres éléments au moment même où il ouvrait le
        # menu pour agir dessus.
        if item is not None and not item.isSelected():
            self.tree.setCurrentItem(item)
        kind, ident = self.current_selection()
        unique = self.selection_unique()

        # Les lambdas sont nécessaires : triggered() transmet un booléen
        # « checked » qui serait reçu comme premier argument (donc comme un nom
        # de dossier, ou comme confirm=False sur une suppression).
        menu = QMenu(self)
        # Sans cela, l'infobulle qui explique le grisage ne s'afficherait pas.
        menu.setToolTipsVisible(True)

        #: Actions ne sachant traiter qu'un seul élément, grisées au-delà.
        mono: list = []

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

        if kind in (KIND_FOLDER, KIND_TRACK):
            menu.addAction("Copier\tCtrl+C", lambda: self.copy_selection())
            menu.addAction("Couper\tCtrl+X", self.cut_selection)
        if self._clipboard[1]:
            menu.addAction("Coller\tCtrl+V", self.paste)
        menu.addSeparator()
        menu.addAction("Nouveau dossier…", lambda: self.create_folder())

        if kind == KIND_FOLDER:
            menu.addSeparator()
            mono.append(menu.addAction(
                "Renommer le dossier…\tF2", lambda: self.rename_selected()
            ))
            menu.addAction(
                "Supprimer le dossier\tSuppr", lambda: self.delete_selected()
            )
        elif kind == KIND_TRACK:
            mono.append(menu.addMenu(self._build_color_menu(int(ident), menu)))
            menu.addSeparator()
            for libelle, signal in (
                ("Modifier la trace", self.resume_requested),
                ("Inverser le sens", self.reverse_requested),
                ("Calculer l'altitude (IGN)", self.elevation_requested),
                ("Décimer la trace…", self.decimate_requested),
                ("Dupliquer la trace", self.duplicate_requested),
                ("Fusionner avec…", self.merge_requested),
            ):
                mono.append(menu.addAction(
                    libelle,
                    lambda s=signal: self._emit_for_track(s),
                ))
            menu.addSeparator()
            mono.append(menu.addAction("Exporter en GPX…", self._request_export))
            mono.append(menu.addAction(
                "Renommer la trace…\tF2", lambda: self.rename_selected()
            ))
            menu.addAction(
                "Supprimer la trace\tSuppr", lambda: self.delete_selected()
            )

        # Copier, supprimer, afficher ou zoomer savent traiter toute la
        # sélection : eux restent actionnables.
        for action in mono:
            action.setEnabled(unique)
            if not unique:
                action.setToolTip(
                    "Un seul élément à la fois : cette action ne sait pas en "
                    "traiter plusieurs."
                )

        return menu

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
        """Émet `signal` avec l'identifiant de la trace sélectionnée.

        Ne fait rien si plusieurs éléments sont retenus. Les menus grisent déjà
        ces actions ; ce refus est le garde-fou de dernier ressort, pour les
        chemins qui ne passent pas par eux.
        """
        if not self.selection_unique():
            return
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

        # L'élément a pu disparaître depuis le dernier affichage de l'arbre :
        # mieux vaut se taire que de tomber en panne dans un signal Qt.
        element = (
            self.db.get_folder(ident)
            if kind == KIND_FOLDER
            else self.db.get_track(ident)
        )
        if element is None:
            self.refresh()
            return False
        current = element.name
        titre = "Renommer le dossier" if kind == KIND_FOLDER else "Renommer la trace"
        libelle = "Nouveau nom :"

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

    def selected_items(self) -> list[QTreeWidgetItem]:
        """Éléments sélectionnés, hors racine (sélection multiple)."""
        return [
            item
            for item in self.tree.selectedItems()
            if item.data(COL_BULB, ROLE_KIND) in (KIND_FOLDER, KIND_TRACK)
        ]

    def selection_unique(self) -> bool:
        """Vrai tant qu'un seul élément est retenu.

        Beaucoup d'actions ne savent traiter qu'une trace : modifier,
        dupliquer, exporter, découper… Les laisser actionnables avec plusieurs
        éléments en surbrillance reviendrait à en désigner une au hasard de
        l'élément courant, et à laisser croire que les autres ont été traitées.
        """
        return len(self.selected_items()) <= 1

    def selected_track(self) -> int | None:
        """La trace sélectionnée, si une seule l'est. None dans tout autre cas.

        None dès qu'il y a zéro élément, plusieurs, ou un dossier : c'est le
        verrou des actions qui ne traitent qu'une trace.
        """
        items = self.selected_items()
        if len(items) != 1:
            return None
        item = items[0]
        if item.data(COL_BULB, ROLE_KIND) != KIND_TRACK:
            return None
        return int(item.data(COL_BULB, ROLE_ID))

    def delete_selected(self, confirm: bool = True) -> bool:
        """Supprime les dossiers et traces sélectionnés."""
        items = self.selected_items()
        if not items:
            return False

        dossiers = [
            int(i.data(COL_BULB, ROLE_ID))
            for i in items
            if i.data(COL_BULB, ROLE_KIND) == KIND_FOLDER
        ]
        traces = [
            int(i.data(COL_BULB, ROLE_ID))
            for i in items
            if i.data(COL_BULB, ROLE_KIND) == KIND_TRACK
        ]

        if confirm and not self._confirm_deletion(items, dossiers, traces):
            return False

        # Les traces contenues dans les dossiers supprimés disparaissent aussi.
        disparues = set(traces)
        for item in items:
            if item.data(COL_BULB, ROLE_KIND) == KIND_FOLDER:
                disparues.update(track_ids_under(item))

        # Les dossiers d'abord : leur suppression emporte leur contenu, et les
        # traces déjà parties ne posent alors plus de question.
        for folder_id in dossiers:
            self.db.delete_folder(folder_id)
        for track_id in traces:
            self.db.delete_track(track_id)

        for track_id in disparues:
            self.visible_tracks.discard(track_id)
        if disparues:
            self.tracks_removed.emit(sorted(disparues))

        self.refresh()
        self.status_message.emit(
            f"{len(items)} élément(s) supprimé(s)."
            if len(items) > 1
            else "Suppression effectuée."
        )
        return True

    def _confirm_deletion(self, items, dossiers, traces) -> bool:
        if len(items) == 1:
            item = items[0]
            nom = item.text(COL_NAME)
            if item.data(COL_BULB, ROLE_KIND) == KIND_FOLDER:
                dossier = self.db.get_folder(dossiers[0])
                question = (
                    f"Supprimer le dossier « {dossier.name if dossier else nom} » "
                    "ainsi que tous les sous-dossiers et traces qu'il contient ?"
                )
            else:
                trace = self.db.get_track(traces[0])
                question = (
                    f"Supprimer la trace « {trace.name if trace else nom} » ?"
                )
        else:
            morceaux = []
            if dossiers:
                morceaux.append(
                    f"{len(dossiers)} dossier(s) et tout leur contenu"
                )
            if traces:
                morceaux.append(f"{len(traces)} trace(s)")
            question = "Supprimer " + " et ".join(morceaux) + " ?"

        answer = QMessageBox.question(
            self,
            "Confirmer la suppression",
            question,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return answer == QMessageBox.StandardButton.Yes

    def _on_items_dropped(self, elements, folder_id: int | None) -> None:
        deplaces = self.move_items(elements, folder_id)
        if deplaces > 1:
            self.status_message.emit(f"{deplaces} éléments déplacés.")

    def move_items(self, elements, folder_id: int | None) -> int:
        """Déplace plusieurs traces et dossiers vers un dossier."""
        deplaces = 0
        for kind, ident in elements:
            if kind == KIND_TRACK:
                deplaces += bool(self.move_track(ident, folder_id))
            elif kind == KIND_FOLDER:
                deplaces += bool(self.move_folder(ident, folder_id))
        return deplaces

    # ------------------------------------------- copier, couper, coller

    def copy_selection(self, couper: bool = False) -> int:
        """Met la sélection dans le presse-papiers de l'arborescence."""
        elements = [
            (item.data(COL_BULB, ROLE_KIND), int(item.data(COL_BULB, ROLE_ID)))
            for item in self.tree.dragged_items()
        ]
        if not elements:
            return 0
        self._clipboard = ("couper" if couper else "copier", elements)
        verbe = "coupé(s)" if couper else "copié(s)"
        self.status_message.emit(f"{len(elements)} élément(s) {verbe}.")
        return len(elements)

    def cut_selection(self) -> int:
        return self.copy_selection(couper=True)

    def paste(self) -> int:
        """Colle le presse-papiers dans le dossier sélectionné."""
        if not self._clipboard[1]:
            self.status_message.emit("Rien à coller.")
            return 0

        mode, elements = self._clipboard
        destination = self.current_folder_id()

        if mode == "couper":
            deplaces = self.move_items(elements, destination)
            self._clipboard = (mode, [])
            self.status_message.emit(f"{deplaces} élément(s) déplacé(s).")
            return deplaces

        colles = 0
        dernier = None
        for kind, ident in elements:
            try:
                if kind == KIND_TRACK:
                    if self.db.get_track(ident) is None:
                        continue
                    # copy_track_to pose le suffixe « -copie » en tenant compte
                    # du dossier d'arrivée.
                    dernier = (KIND_TRACK, self.db.copy_track_to(ident, destination))
                else:
                    dernier = (KIND_FOLDER, self.db.copy_folder(ident, destination))
                colles += 1
            except (CycleError, DuplicateNameError, NotFoundError) as exc:
                QMessageBox.warning(self, "Collage impossible", str(exc))

        if colles:
            self.refresh()
            if dernier is not None:
                self._select(*dernier)
            self.status_message.emit(f"{colles} élément(s) collé(s).")
        return colles

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

        destination = self._nom_dossier(parent_id)
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

        self.status_message.emit(
            f"« {track.name} » déplacée vers « {self._nom_dossier(folder_id)} »."
        )
        return True

    def _nom_dossier(self, folder_id: int | None) -> str:
        """Nom affichable d'un dossier ; « Mes traces » pour la racine."""
        if folder_id is None:
            return "Mes traces"
        dossier = self.db.get_folder(folder_id)
        return dossier.name if dossier is not None else "Mes traces"

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
