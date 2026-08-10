"""Fenêtre principale : arborescence à gauche, carte à droite."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction, QKeySequence
from PyQt6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QInputDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QSplitter,
    QStyle,
    QToolBar,
)

from .. import APP_NAME, APP_VERSION
from ..config import db_path
from ..database import Database
from ..editor import DraftTrack
from ..geo import format_length, total_length
from ..gpx import (
    GpxParseError,
    count_waypoints,
    parse_gpx,
    safe_filename,
    write_gpx,
)
from .map_view import LAYER_NAMES, MapView
from .tree_panel import KIND_TRACK, TreePanel


class MainWindow(QMainWindow):
    """Fenêtre principale de l'application."""

    def __init__(self, db: Database | None = None) -> None:
        super().__init__()
        self.db = db if db is not None else Database()

        self.setWindowTitle(f"{APP_NAME} — Gestion de traces GPX")
        self.resize(1280, 800)

        #: Trace en cours de saisie, conservée en mémoire (Jalon 3).
        self.draft = DraftTrack()
        #: Trace enregistrée actuellement affichée sur la carte (Jalon 5).
        self.displayed_track_id: int | None = None

        self.tree_panel = TreePanel(self.db, self)
        self.map_view = MapView(self)

        splitter = QSplitter(Qt.Orientation.Horizontal, self)
        splitter.addWidget(self.tree_panel)
        splitter.addWidget(self.map_view)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([300, 980])
        splitter.setChildrenCollapsible(False)
        self.setCentralWidget(splitter)

        self._build_actions()
        self._build_toolbar()
        self._build_menu()
        self._build_statusbar()

        self.map_view.map_ready.connect(self._on_map_ready)
        self.map_view.view_changed.connect(self._on_view_changed)
        self.map_view.map_clicked.connect(self._on_map_clicked)
        self.map_view.layer_changed.connect(self._on_layer_changed_from_map)
        self.map_view.undo_requested.connect(self.undo_last_point)

        self.tree_panel.export_requested.connect(self.export_track)
        self.tree_panel.status_message.connect(self.status_label.setText)
        self.tree_panel.track_activated.connect(self.display_track)

        self._update_draft_actions()

    # ------------------------------------------------------------ interface

    def _build_actions(self) -> None:
        style = self.style()

        self.action_create = QAction("Créer une trace", self)
        # Même icône que les traces dans l'arborescence ; le dossier est
        # réservé à l'action « Nouveau dossier ».
        self.action_create.setIcon(
            style.standardIcon(QStyle.StandardPixmap.SP_FileIcon)
        )
        self.action_create.setCheckable(True)
        self.action_create.setShortcut("Ctrl+N")
        self.action_create.setToolTip(
            "Mode saisie : chaque clic gauche sur la carte ajoute un point (Ctrl+N)"
        )
        self.action_create.toggled.connect(self.set_edit_mode)

        self.action_undo = QAction("Annuler le dernier point", self)
        self.action_undo.setIcon(
            style.standardIcon(QStyle.StandardPixmap.SP_ArrowBack)
        )
        self.action_undo.setShortcut(QKeySequence.StandardKey.Undo)
        # Le QWebEngineView capte le clavier : sans ce contexte, Ctrl+Z ne
        # remonterait pas jusqu'à la fenêtre.
        self.action_undo.setShortcutContext(
            Qt.ShortcutContext.ApplicationShortcut
        )
        self.action_undo.triggered.connect(self.undo_last_point)

        self.action_save = QAction("Enregistrer la trace", self)
        self.action_save.setIcon(
            style.standardIcon(QStyle.StandardPixmap.SP_DialogSaveButton)
        )
        self.action_save.setShortcut(QKeySequence.StandardKey.Save)
        self.action_save.setShortcutContext(
            Qt.ShortcutContext.ApplicationShortcut
        )
        self.action_save.setToolTip(
            "Enregistrer le brouillon dans le dossier sélectionné (Ctrl+S)"
        )
        self.action_save.triggered.connect(lambda: self.save_draft())

        self.action_clear = QAction("Effacer le brouillon", self)
        self.action_clear.setIcon(
            style.standardIcon(QStyle.StandardPixmap.SP_DialogDiscardButton)
        )
        # triggered() transmet un booléen « checked » : sans lambda, il serait
        # reçu comme `confirm` et sauterait la demande de confirmation.
        self.action_clear.triggered.connect(lambda: self.clear_draft())

        self.action_import = QAction("Importer un GPX", self)
        self.action_import.setIcon(
            style.standardIcon(QStyle.StandardPixmap.SP_DialogOpenButton)
        )
        self.action_import.setShortcut("Ctrl+I")
        self.action_import.setToolTip(
            "Importer un ou plusieurs fichiers GPX dans le dossier sélectionné"
        )
        self.action_import.triggered.connect(lambda: self.import_gpx())

        self.action_new_folder = QAction("Nouveau dossier", self)
        self.action_new_folder.setIcon(
            style.standardIcon(QStyle.StandardPixmap.SP_FileDialogNewFolder)
        )
        self.action_new_folder.triggered.connect(
            lambda: self.tree_panel.create_folder()
        )

        self.addAction(self.action_undo)
        self.addAction(self.action_save)

    def _build_toolbar(self) -> None:
        toolbar = QToolBar("Barre d'outils", self)
        toolbar.setMovable(False)
        toolbar.setToolButtonStyle(
            Qt.ToolButtonStyle.ToolButtonTextBesideIcon
        )
        self.addToolBar(toolbar)

        toolbar.addAction(self.action_create)
        toolbar.addAction(self.action_undo)
        toolbar.addAction(self.action_save)
        toolbar.addAction(self.action_clear)
        toolbar.addSeparator()
        toolbar.addAction(self.action_import)
        toolbar.addAction(self.action_new_folder)
        toolbar.addSeparator()

        toolbar.addWidget(QLabel("  Fond de carte : "))
        self.layer_combo = QComboBox(self)
        self.layer_combo.addItems(LAYER_NAMES)
        self.layer_combo.setMinimumWidth(190)
        self.layer_combo.currentTextChanged.connect(self.map_view.set_base_layer)
        toolbar.addWidget(self.layer_combo)

    def _build_menu(self) -> None:
        menu = self.menuBar()

        file_menu = menu.addMenu("&Fichier")
        file_menu.addAction(self.action_import)
        export_action = QAction("&Exporter la trace sélectionnée en GPX…", self)
        export_action.triggered.connect(self._export_selected_track)
        file_menu.addAction(export_action)
        file_menu.addSeparator()
        quit_action = QAction("&Quitter", self)
        quit_action.setShortcut(QKeySequence.StandardKey.Quit)
        quit_action.triggered.connect(self.close)
        file_menu.addAction(quit_action)

        edit_menu = menu.addMenu("&Trace")
        edit_menu.addAction(self.action_create)
        edit_menu.addAction(self.action_undo)
        edit_menu.addAction(self.action_save)
        edit_menu.addAction(self.action_clear)
        edit_menu.addSeparator()
        edit_menu.addAction(self.action_new_folder)

        view_menu = menu.addMenu("&Affichage")
        refresh_action = QAction("&Actualiser l'arborescence", self)
        refresh_action.setShortcut("F5")
        refresh_action.triggered.connect(self.tree_panel.refresh)
        view_menu.addAction(refresh_action)

        help_menu = menu.addMenu("&Aide")
        about_action = QAction("À &propos", self)
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)

    def _build_statusbar(self) -> None:
        self.coord_label = QLabel("—", self)
        self.status_label = QLabel("Initialisation…", self)
        self.draft_label = QLabel(self.draft.summary(), self)
        self.statusBar().addWidget(self.status_label, 1)
        self.statusBar().addPermanentWidget(self.draft_label)
        self.statusBar().addPermanentWidget(self.coord_label)

    # ------------------------------------------------------- édition (J3)

    @property
    def edit_mode(self) -> bool:
        return self.action_create.isChecked()

    def set_edit_mode(self, enabled: bool) -> None:
        """Active ou quitte le mode saisie ; le brouillon reste en mémoire."""
        if self.action_create.isChecked() != enabled:
            self.action_create.setChecked(enabled)
            return  # toggled() rappellera cette méthode
        self.map_view.set_edit_mode(enabled)
        if enabled:
            self.status_label.setText(
                "Mode saisie : cliquez sur la carte pour ajouter des points."
            )
        else:
            self.status_label.setText("Mode saisie désactivé.")
        self._update_draft_actions()

    def add_draft_point(self, lat: float, lon: float) -> None:
        """Ajoute un point au brouillon (mémoire) et à la carte (affichage)."""
        self.draft.add_point(lat, lon)
        self.map_view.append_draft_point(lat, lon)
        self.status_label.setText(f"Point ajouté : {lat:.5f} ; {lon:.5f}")
        self._update_draft_actions()

    def undo_last_point(self) -> None:
        """Retire le dernier point ajouté (Ctrl+Z)."""
        removed = self.draft.undo_last()
        if removed is None:
            self.status_label.setText("Aucun point à annuler.")
            return
        self.map_view.pop_draft_point()
        self.status_label.setText(
            f"Point annulé : {removed.lat:.5f} ; {removed.lon:.5f}"
        )
        self._update_draft_actions()

    def clear_draft(self, confirm: bool = True) -> None:
        """Vide le brouillon, après confirmation s'il contient des points."""
        if self.draft.is_empty:
            return
        if confirm:
            answer = QMessageBox.question(
                self,
                "Effacer le brouillon",
                f"Effacer les {len(self.draft)} points de la trace en cours ?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        self.draft.clear()
        self.map_view.clear_draft()
        self.status_label.setText("Brouillon effacé.")
        self._update_draft_actions()

    def _update_draft_actions(self) -> None:
        """Reflète l'état du brouillon dans la barre d'état et les actions."""
        has_points = not self.draft.is_empty
        self.action_undo.setEnabled(has_points)
        self.action_clear.setEnabled(has_points)
        self.action_save.setEnabled(len(self.draft) >= 2)
        self.draft_label.setText(self.draft.summary())

    # ------------------------------------------------- sauvegarde (Jalon 4)

    def save_draft(self, name: str | None = None) -> int | None:
        """Enregistre le brouillon en base, dans le dossier sélectionné.

        `name` sert aux tests ; sans lui, l'utilisateur est invité à le saisir.
        Retourne l'identifiant de la trace créée, ou None si abandon.
        """
        if len(self.draft) < 2:
            QMessageBox.information(
                self,
                "Trace incomplète",
                "Une trace doit compter au moins deux points pour être "
                "enregistrée.",
            )
            return None

        if name is None:
            name, accepted = QInputDialog.getText(
                self, "Enregistrer la trace", "Nom de la trace :",
                text=self.draft.name,
            )
            if not accepted or not name.strip():
                return None

        folder_id = self.tree_panel.current_folder_id()
        track_id = self.db.create_track(
            name, folder_id=folder_id, points=self.draft.points
        )

        self.draft.clear()
        self.map_view.clear_draft()
        self._update_draft_actions()

        self.tree_panel.refresh()
        self.tree_panel.select_track(track_id)
        self.status_label.setText(f"Trace « {name} » enregistrée.")
        return track_id

    # ------------------------------------------- import et affichage (J5)

    def import_gpx(self, paths: list[str] | None = None) -> list[int]:
        """Importe un ou plusieurs fichiers GPX dans le dossier sélectionné.

        `paths` sert aux tests ; sans lui, une boîte de dialogue est ouverte.
        Retourne les identifiants des traces créées.
        """
        if paths is None:
            paths, _filter = QFileDialog.getOpenFileNames(
                self, "Importer des fichiers GPX", "", "Fichiers GPX (*.gpx)"
            )
            if not paths:
                return []

        folder_id = self.tree_panel.current_folder_id()
        created: list[int] = []
        problemes: list[str] = []

        for path in paths:
            try:
                tracks = parse_gpx(path)
            except GpxParseError as exc:
                problemes.append(str(exc))
                continue
            if not tracks:
                nom = Path(path).name
                reperes = count_waypoints(path)
                if reperes:
                    problemes.append(
                        f"{nom} ne contient aucune trace, seulement {reperes} "
                        "points d'intérêt (non gérés pour l'instant)."
                    )
                else:
                    problemes.append(f"{nom} ne contient aucune trace.")
                continue
            for track in tracks:
                created.append(
                    self.db.create_track(
                        track.name,
                        folder_id=folder_id,
                        points=track.points,
                        description=track.description,
                    )
                )

        if created:
            self.tree_panel.refresh()
            self.tree_panel.select_track(created[-1])
            self.display_track(created[-1])
            self.status_label.setText(
                f"{len(created)} trace(s) importée(s) depuis "
                f"{len(paths)} fichier(s)."
            )

        if problemes:
            QMessageBox.warning(
                self,
                "Import partiel" if created else "Import impossible",
                "\n".join(problemes),
            )
        return created

    def display_track(self, track_id: int) -> bool:
        """Affiche une trace enregistrée et cadre la carte dessus."""
        track = self.db.get_track(track_id, with_points=True)
        if track is None or not track.points:
            self.status_label.setText("Cette trace ne contient aucun point.")
            return False

        self.map_view.show_track(track.points, track.color)
        self.displayed_track_id = track_id
        longueur = format_length(total_length(track.points))
        self.status_label.setText(
            f"« {track.name} » — {track.point_count} points, {longueur}"
        )
        return True

    # ---------------------------------------------------- export GPX (J4)

    def _export_selected_track(self) -> None:
        kind, ident = self.tree_panel.current_selection()
        if kind != KIND_TRACK:
            QMessageBox.information(
                self,
                "Aucune trace sélectionnée",
                "Sélectionnez une trace dans l'arborescence pour l'exporter.",
            )
            return
        self.export_track(int(ident))

    def export_track(self, track_id: int, path: str | None = None) -> str | None:
        """Écrit une trace de la base dans un fichier GPX.

        `path` sert aux tests ; sans lui, une boîte de dialogue est ouverte.
        """
        track = self.db.get_track(track_id, with_points=True)
        if track is None:
            return None
        if not track.points:
            QMessageBox.information(
                self,
                "Trace vide",
                f"La trace « {track.name} » ne contient aucun point.",
            )
            return None

        if path is None:
            path, _filter = QFileDialog.getSaveFileName(
                self,
                "Exporter en GPX",
                safe_filename(track.name),
                "Fichiers GPX (*.gpx)",
            )
            if not path:
                return None

        try:
            written = write_gpx(path, track.name, track.points, track.description)
        except OSError as exc:
            QMessageBox.critical(
                self, "Échec de l'export", f"Impossible d'écrire le fichier :\n{exc}"
            )
            return None

        self.status_label.setText(
            f"Trace « {track.name} » exportée vers {written}."
        )
        return str(written)

    # -------------------------------------------------------------- signaux

    def _on_map_ready(self) -> None:
        self.status_label.setText("Carte prête.")
        # Réapplique l'état courant à une carte fraîchement chargée.
        self.map_view.set_edit_mode(self.edit_mode)
        if not self.draft.is_empty:
            self.map_view.set_draft(self.draft.points)
        if self.displayed_track_id is not None:
            self.display_track(self.displayed_track_id)

    def _on_view_changed(self, lat: float, lon: float, zoom: int) -> None:
        self.coord_label.setText(f"Centre : {lat:.5f} ; {lon:.5f}  —  zoom {zoom}")

    def _on_map_clicked(self, lat: float, lon: float) -> None:
        if self.edit_mode:
            self.add_draft_point(lat, lon)
        else:
            self.status_label.setText(f"Point cliqué : {lat:.5f} ; {lon:.5f}")

    def _on_layer_changed_from_map(self, name: str) -> None:
        """Garde le sélecteur de la barre d'outils synchronisé avec la carte."""
        if name != self.layer_combo.currentText():
            self.layer_combo.blockSignals(True)
            self.layer_combo.setCurrentText(name)
            self.layer_combo.blockSignals(False)

    def _show_about(self) -> None:
        QMessageBox.about(
            self,
            f"À propos de {APP_NAME}",
            f"<b>{APP_NAME}</b> version {APP_VERSION}<br><br>"
            "Création et gestion de traces de randonnée (GPX).<br><br>"
            f"Données utilisateur :<br><code>{db_path()}</code>",
        )

    def closeEvent(self, event):  # noqa: N802
        self.db.close()
        super().closeEvent(event)
