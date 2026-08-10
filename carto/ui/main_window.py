"""Fenêtre principale : arborescence à gauche, carte à droite."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QPoint, Qt
from PyQt6.QtGui import QAction, QKeySequence
from PyQt6.QtWidgets import (
    QFileDialog,
    QInputDialog,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QSplitter,
    QStyle,
    QToolBar,
)

from .. import APP_NAME, APP_VERSION
from ..config import db_path
from ..database import Database
from ..editor import DraftTrack
from ..geo import bounds, format_length, total_length
from ..gpx import (
    GpxParseError,
    count_waypoints,
    parse_gpx,
    safe_filename,
    write_gpx,
)
from .map_view import MapView
from .points_panel import PointsPanel
from .tree_panel import KIND_ROOT, KIND_TRACK, TreePanel, track_ids_under


class MainWindow(QMainWindow):
    """Fenêtre principale de l'application."""

    def __init__(self, db: Database | None = None) -> None:
        super().__init__()
        self.db = db if db is not None else Database()

        self.setWindowTitle(f"{APP_NAME} — Gestion de traces GPX")
        self.resize(1280, 800)

        #: Trace en cours de saisie, conservée en mémoire (Jalon 3).
        self.draft = DraftTrack()
        #: Traces enregistrées actuellement affichées sur la carte.
        #: L'état est conservé en base d'un lancement à l'autre.
        self.visible_tracks: set[int] = set()
        #: Vrai dès la fermeture : plus aucun accès à la base ne doit avoir lieu.
        self._closing = False

        self.tree_panel = TreePanel(self.db, self.visible_tracks, self)
        self.points_panel = PointsPanel(self)
        self.map_view = MapView(self)

        left = QSplitter(Qt.Orientation.Vertical, self)
        left.addWidget(self.tree_panel)
        left.addWidget(self.points_panel)
        left.setStretchFactor(0, 3)
        left.setStretchFactor(1, 2)
        left.setSizes([480, 320])

        splitter = QSplitter(Qt.Orientation.Horizontal, self)
        splitter.addWidget(left)
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
        self.map_view.point_moved.connect(self.move_draft_point)
        self.map_view.point_context.connect(self.show_point_menu)
        self.map_view.point_selected.connect(self.select_draft_point)
        self.map_view.point_inserted.connect(self.insert_draft_point)

        self.tree_panel.export_requested.connect(self.export_track)
        self.tree_panel.status_message.connect(self.status_label.setText)
        self.tree_panel.track_activated.connect(self.display_track)
        self.tree_panel.resume_requested.connect(self.resume_track)
        self.tree_panel.duplicate_requested.connect(self.duplicate_track)
        self.tree_panel.merge_requested.connect(self.merge_track)

        self.tree_panel.visibility_toggled.connect(self.toggle_visibility)
        self.tree_panel.show_requested.connect(self.show_items)
        self.tree_panel.show_only_requested.connect(self.show_only)
        self.tree_panel.hide_requested.connect(self.hide_items)
        self.tree_panel.zoom_requested.connect(self.zoom_to_items)
        self.tree_panel.style_changed.connect(self.refresh_track_style)
        self.tree_panel.tracks_removed.connect(self.forget_tracks)

        self.points_panel.point_selected.connect(self.map_view.select_draft_point)
        self.points_panel.delete_requested.connect(self.remove_draft_points)
        self.points_panel.split_requested.connect(self.split_draft)

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

        self.action_resume = QAction("Modifier la trace", self)
        self.action_resume.setIcon(
            style.standardIcon(QStyle.StandardPixmap.SP_FileDialogDetailedView)
        )
        self.action_resume.setToolTip(
            "Reprendre la trace sélectionnée pour la prolonger ou la corriger"
        )
        self.action_resume.triggered.connect(self._resume_selected_track)

        self.action_close_loop = QAction("Fermer la boucle", self)
        self.action_close_loop.setIcon(
            style.standardIcon(QStyle.StandardPixmap.SP_BrowserReload)
        )
        self.action_close_loop.setToolTip(
            "Ramener le tracé à son point de départ"
        )
        self.action_close_loop.triggered.connect(lambda: self.close_draft_loop())

        self.action_import = QAction("Importer un GPX", self)
        self.action_import.setIcon(
            style.standardIcon(QStyle.StandardPixmap.SP_DialogOpenButton)
        )
        self.action_import.setShortcut("Ctrl+I")
        self.action_import.setToolTip(
            "Importer un ou plusieurs fichiers GPX dans le dossier sélectionné"
        )
        self.action_import.triggered.connect(lambda: self.import_gpx())

        self.action_export = QAction("Exporter en GPX", self)
        self.action_export.setIcon(
            style.standardIcon(QStyle.StandardPixmap.SP_DialogSaveButton)
        )
        self.action_export.setToolTip(
            "Exporter la trace sélectionnée dans un fichier GPX"
        )
        self.action_export.triggered.connect(self._export_selected_track)

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

        # Import et export en tête ; le choix du fond de carte et la création
        # de dossier ont été retirés d'ici : ils existent déjà, l'un dans le
        # sélecteur de couches de la carte, l'autre au clic droit.
        toolbar.addAction(self.action_import)
        toolbar.addAction(self.action_export)
        toolbar.addSeparator()
        toolbar.addAction(self.action_create)
        toolbar.addAction(self.action_resume)
        toolbar.addAction(self.action_undo)
        toolbar.addAction(self.action_close_loop)
        toolbar.addAction(self.action_save)
        toolbar.addAction(self.action_clear)

    def _build_menu(self) -> None:
        menu = self.menuBar()

        file_menu = menu.addMenu("&Fichier")
        file_menu.addAction(self.action_import)
        file_menu.addAction(self.action_export)
        file_menu.addSeparator()
        quit_action = QAction("&Quitter", self)
        quit_action.setShortcut(QKeySequence.StandardKey.Quit)
        quit_action.triggered.connect(self.close)
        file_menu.addAction(quit_action)

        edit_menu = menu.addMenu("&Trace")
        edit_menu.addAction(self.action_create)
        edit_menu.addAction(self.action_resume)
        edit_menu.addAction(self.action_undo)
        edit_menu.addAction(self.action_close_loop)
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
        self.action_close_loop.setEnabled(
            len(self.draft) >= 3 and not self.draft.is_loop
        )
        self.draft_label.setText(self.draft.summary())
        self.points_panel.refresh(self.draft)

    # --------------------------------------------- édition avancée (Jalon 6)

    def resume_track(self, track_id: int) -> bool:
        """Reprend une trace enregistrée pour la prolonger ou la corriger."""
        track = self.db.get_track(track_id, with_points=True)
        if track is None or not track.points:
            self.status_label.setText("Cette trace ne contient aucun point.")
            return False

        if not self.draft.is_empty and not self._confirm_discard_draft():
            return False

        self.draft.load_track(track)
        self._show_draft_on_map(fit=True)
        # La trace passe en édition (rouge) : la garder aussi en affichage
        # simple (bleu) superposerait deux tracés identiques. Elle reste
        # mémorisée comme affichée pour la prochaine ouverture.
        self.hide_track(track_id, remember=False)
        self.set_edit_mode(True)
        self._update_draft_actions()
        self.status_label.setText(
            f"Modification de « {track.name} » : cliquez pour prolonger, "
            "glissez un point pour le déplacer."
        )
        return True

    def _resume_selected_track(self) -> None:
        kind, ident = self.tree_panel.current_selection()
        if kind != KIND_TRACK:
            QMessageBox.information(
                self,
                "Aucune trace sélectionnée",
                "Sélectionnez une trace dans l'arborescence pour la modifier.",
            )
            return
        self.resume_track(int(ident))

    def _confirm_discard_draft(self) -> bool:
        answer = QMessageBox.question(
            self,
            "Abandonner la trace en cours ?",
            f"{self.draft.summary()}\n\nCe travail n'est pas enregistré. "
            "Continuer et le perdre ?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return answer == QMessageBox.StandardButton.Yes

    def close_draft_loop(self) -> bool:
        """Ferme la trace en cours en la ramenant à son point de départ."""
        if not self.draft.close_loop():
            self.status_label.setText(
                "Il faut au moins trois points, et la boucle ne doit pas déjà "
                "être fermée."
            )
            return False
        depart = self.draft.points[0]
        self.map_view.append_draft_point(depart.lat, depart.lon)
        self._update_draft_actions()
        self.status_label.setText("Boucle fermée.")
        return True

    def _show_draft_on_map(self, fit: bool = False) -> None:
        """Redessine le brouillon sur la carte, en le cadrant si demandé.

        Sans recadrage, une trace reprise reste souvent hors du champ visible.
        """
        self.map_view.set_draft(self.draft.points)
        if not fit:
            return
        box = bounds(self.draft.points)
        if box is not None:
            self.map_view.fit_bounds(*box)

    def select_draft_point(self, index: int) -> None:
        """Un clic sur un point de la carte le désigne dans le panneau."""
        self.points_panel.select_index(index)
        self.map_view.select_draft_point(index)
        if 0 <= index < len(self.draft):
            point = self.draft.points[index]
            self.status_label.setText(
                f"Point {index + 1} sur {len(self.draft)} — "
                f"{point.lat:.5f} ; {point.lon:.5f}"
            )

    def move_draft_point(self, index: int, lat: float, lon: float) -> bool:
        """Repositionne un point après un glisser sur la carte."""
        if not self.draft.move_point(index, lat, lon):
            return False
        self.map_view.move_draft_point(index, lat, lon)
        self._update_draft_actions()
        self.status_label.setText(
            f"Point {index + 1} déplacé en {lat:.5f} ; {lon:.5f}"
        )
        return True

    def insert_draft_point(self, index: int, lat: float, lon: float) -> bool:
        """Insère un point sur un segment du tracé (clic sur la ligne)."""
        if self.draft.insert_point(index, lat, lon) is None:
            return False
        self.map_view.insert_draft_point(index, lat, lon)
        self._update_draft_actions()
        self.points_panel.select_index(index)
        self.map_view.select_draft_point(index)
        self.status_label.setText(
            f"Point inséré en position {index + 1} sur {len(self.draft)}."
        )
        return True

    def show_point_menu(self, index: int, x: int, y: int) -> None:
        """Menu au clic droit sur un point de la trace en édition."""
        if not 0 <= index < len(self.draft):
            return
        self.select_draft_point(index)

        menu = QMenu(self)
        menu.addAction(
            f"Supprimer le point {index + 1}",
            lambda: self.remove_draft_point(index),
        )
        action_decoupe = menu.addAction(
            "Découper la trace ici", lambda: self.split_draft(index)
        )
        action_decoupe.setEnabled(
            self.draft.is_existing and 1 <= index <= len(self.draft) - 2
        )
        menu.exec(self.map_view.mapToGlobal(QPoint(int(x), int(y))))

    def remove_draft_point(self, index: int) -> bool:
        """Supprime un point précis."""
        return self.remove_draft_points([index])

    def remove_draft_points(self, indexes: list[int]) -> bool:
        """Supprime un point ou une sélection de points."""
        supprimes = self.draft.remove_points(indexes)
        if not supprimes:
            return False
        self.map_view.set_draft(self.draft.points)
        self._update_draft_actions()
        pluriel = "s" if supprimes > 1 else ""
        self.status_label.setText(f"{supprimes} point{pluriel} supprimé{pluriel}.")
        return True

    def split_draft(self, index: int) -> tuple[int, int] | None:
        """Découpe en deux la trace reprise, au point sélectionné."""
        if not self.draft.is_existing:
            QMessageBox.information(
                self,
                "Trace non enregistrée",
                "Enregistrez d'abord la trace : le découpage agit sur une "
                "trace de la bibliothèque.",
            )
            return None

        moities = self.draft.split_at(index)
        if moities is None:
            self.status_label.setText(
                "Le point de découpe doit laisser au moins deux points de "
                "chaque côté."
            )
            return None

        # Le brouillon peut avoir été modifié depuis la reprise : on l'écrit
        # avant de découper, sinon la coupure porterait sur d'anciens points.
        track_id = self.draft.track_id
        self.db.replace_points(track_id, self.draft.points)
        try:
            premier, second = self.db.split_track(track_id, index)
        except ValueError as exc:
            QMessageBox.warning(self, "Découpage impossible", str(exc))
            return None

        self.draft.reset()
        self.map_view.clear_draft()
        self.set_edit_mode(False)
        self._update_draft_actions()

        self.tree_panel.refresh()
        self.tree_panel.select_track(second)
        self.display_track(premier)
        self.status_label.setText(
            f"Trace découpée en « {self.db.get_track(premier).name} » et "
            f"« {self.db.get_track(second).name} »."
        )
        return (premier, second)

    def duplicate_track(self, track_id: int, name: str | None = None) -> int | None:
        """Duplique une trace de la bibliothèque."""
        track = self.db.get_track(track_id)
        if track is None:
            return None
        copie = self.db.duplicate_track(track_id, name)
        self.tree_panel.refresh()
        self.tree_panel.select_track(copie)
        self.status_label.setText(
            f"« {track.name} » dupliquée en « {self.db.get_track(copie).name} »."
        )
        return copie

    def merge_track(self, track_id: int, other_id: int | None = None) -> int | None:
        """Fusionne la trace sélectionnée avec une autre.

        `other_id` sert aux tests ; sans lui, l'utilisateur choisit la seconde
        trace dans une liste.
        """
        track = self.db.get_track(track_id)
        if track is None:
            return None

        candidates = [
            t for t in self._all_tracks() if t.id != track_id and t.point_count
        ]
        if not candidates:
            QMessageBox.information(
                self,
                "Fusion impossible",
                "Il faut une seconde trace non vide pour fusionner.",
            )
            return None

        if other_id is None:
            libelles = [f"{t.name} ({t.point_count} pts)" for t in candidates]
            choix, accepte = QInputDialog.getItem(
                self,
                "Fusionner des traces",
                f"Ajouter à la suite de « {track.name} » :",
                libelles,
                0,
                False,
            )
            if not accepte:
                return None
            other_id = candidates[libelles.index(choix)].id

        autre = self.db.get_track(other_id)
        if autre is None:
            return None

        fusion = self.db.merge_tracks(track_id, other_id)
        self.tree_panel.refresh()
        self.tree_panel.select_track(fusion)
        self.display_track(fusion)
        self.status_label.setText(
            f"« {track.name} » et « {autre.name} » fusionnées en "
            f"« {self.db.get_track(fusion).name} »."
        )
        return fusion

    def _all_tracks(self) -> list:
        """Toutes les traces de la bibliothèque, tous dossiers confondus."""
        tracks = list(self.db.list_tracks(None))
        a_visiter = [f.id for f in self.db.list_folders(None)]
        while a_visiter:
            folder_id = a_visiter.pop()
            tracks.extend(self.db.list_tracks(folder_id))
            a_visiter.extend(f.id for f in self.db.list_folders(folder_id))
        return tracks

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

        if self.draft.is_existing:
            # Reprise d'une trace : on met à jour au lieu d'en créer une autre.
            track_id = self.draft.track_id
            self.db.replace_points(track_id, self.draft.points)
            self.db.rename_track(track_id, name)
            message = f"Trace « {name} » mise à jour."
        else:
            track_id = self.db.create_track(
                name,
                folder_id=self.tree_panel.current_folder_id(),
                points=self.draft.points,
                is_loop=self.draft.is_loop,
            )
            message = f"Trace « {name} » enregistrée."

        self.draft.reset()
        self.map_view.clear_draft()
        self._update_draft_actions()

        self.tree_panel.refresh()
        self.tree_panel.select_track(track_id)
        self.status_label.setText(message)
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
        """Affiche une trace et cadre la carte dessus (double-clic, import)."""
        if not self.show_track(track_id):
            return False
        self.map_view.zoom_tracks([track_id])
        return True

    def show_track(self, track_id: int) -> bool:
        """Ajoute une trace à la carte, sans masquer celles déjà affichées."""
        track = self.db.get_track(track_id, with_points=True)
        if track is None or not track.points:
            self.status_label.setText("Cette trace ne contient aucun point.")
            return False

        self.map_view.show_track(
            track_id, track.points, track.color, track.opacity, name=track.name
        )
        self.visible_tracks.add(track_id)
        if not track.visible:
            self.db.set_track_visible(track_id, True)
        self.tree_panel.refresh_bulbs()

        longueur = format_length(total_length(track.points))
        self.status_label.setText(
            f"« {track.name} » — {track.point_count} points, {longueur}"
            f"  ({len(self.visible_tracks)} trace(s) affichée(s))"
        )
        return True

    def hide_track(self, track_id: int, remember: bool = True) -> bool:
        """Retire une trace de la carte.

        `remember=False` sert à la reprise en édition : la trace disparaît de
        l'affichage simple, mais reste marquée comme affichée pour le prochain
        lancement.
        """
        if track_id not in self.visible_tracks:
            return False
        self.map_view.hide_track(track_id)
        self.visible_tracks.discard(track_id)
        if remember:
            self.db.set_track_visible(track_id, False)
        self.tree_panel.refresh_bulbs()
        return True

    def forget_tracks(self, track_ids: list) -> None:
        """Retire de la carte des traces qui viennent d'être supprimées."""
        for track_id in track_ids:
            self.map_view.hide_track(int(track_id))
            self.visible_tracks.discard(int(track_id))
        self.tree_panel.refresh_bulbs()

    def refresh_track_style(self, track_id: int) -> None:
        """Applique sur la carte la couleur et la transparence enregistrées."""
        track = self.db.get_track(track_id)
        if track is None:
            return
        self.map_view.set_track_style(track_id, track.color, track.opacity)

    # ----------------------------------- affichage de plusieurs traces

    def tracks_of(self, kind: str, ident: int | None) -> list[int]:
        """Traces concernées par une action visant un item de l'arborescence."""
        if kind == KIND_TRACK and ident is not None:
            return [int(ident)]
        item = (
            self.tree_panel.tree.topLevelItem(0)
            if kind == KIND_ROOT
            else self.tree_panel.find_item(kind, ident)
        )
        return track_ids_under(item) if item is not None else []

    def show_items(self, kind: str, ident: int | None) -> int:
        """Affiche une trace, ou toutes celles d'un dossier."""
        affichees = [t for t in self.tracks_of(kind, ident) if self.show_track(t)]
        if affichees:
            self.status_label.setText(
                f"{len(self.visible_tracks)} trace(s) affichée(s)."
            )
        return len(affichees)

    def hide_items(self, kind: str, ident: int | None) -> int:
        """Masque une trace, ou toutes celles d'un dossier."""
        masquees = [t for t in self.tracks_of(kind, ident) if self.hide_track(t)]
        if masquees:
            pluriel = "s" if len(masquees) > 1 else ""
            self.status_label.setText(
                f"{len(masquees)} trace{pluriel} masquée{pluriel} — "
                f"{len(self.visible_tracks)} encore affichée(s)."
            )
        return len(masquees)

    def show_only(self, kind: str, ident: int | None) -> int:
        """N'affiche que la trace ou le dossier visé."""
        cibles = self.tracks_of(kind, ident)
        for track_id in list(self.visible_tracks):
            if track_id not in cibles:
                self.hide_track(track_id)
        return self.show_items(kind, ident)

    def zoom_to_items(self, kind: str, ident: int | None) -> bool:
        """Cadre la carte sur une trace ou sur tout un dossier.

        Les traces visées sont affichées au besoin : zoomer sur une trace
        masquée n'aurait rien montré.
        """
        cibles = self.tracks_of(kind, ident)
        if not cibles:
            self.status_label.setText("Aucune trace à afficher ici.")
            return False
        for track_id in cibles:
            if track_id not in self.visible_tracks:
                self.show_track(track_id)
        self.map_view.zoom_tracks(cibles)
        return True

    def toggle_visibility(self, kind: str, ident: int | None) -> None:
        """Clic sur l'ampoule : bascule l'affichage de l'élément."""
        cibles = self.tracks_of(kind, ident)
        if not cibles:
            return
        if all(t in self.visible_tracks for t in cibles):
            self.hide_items(kind, ident)
        else:
            self.show_items(kind, ident)

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
        # La carte peut finir de charger après la fermeture de la fenêtre : la
        # base serait alors close, et l'exception levée dans ce slot Qt ferait
        # avorter le processus.
        if self._closing:
            return
        self.status_label.setText("Carte prête.")
        # Réapplique l'état courant à une carte fraîchement chargée.
        self.map_view.set_edit_mode(self.edit_mode)
        if not self.draft.is_empty:
            # Recadrer aussi : les appels émis avant le chargement de la page
            # sont perdus, y compris le cadrage initial de la reprise.
            self._show_draft_on_map(fit=True)
        # Réaffiche ce qui était visible à la fermeture précédente.
        for track_id in self.db.visible_track_ids():
            self.show_track(track_id)
        if self.visible_tracks:
            self.map_view.zoom_tracks(sorted(self.visible_tracks))
            self.status_label.setText(
                f"{len(self.visible_tracks)} trace(s) réaffichée(s)."
            )

    def _on_view_changed(self, lat: float, lon: float, zoom: int) -> None:
        self.coord_label.setText(f"Centre : {lat:.5f} ; {lon:.5f}  —  zoom {zoom}")

    def _on_map_clicked(self, lat: float, lon: float) -> None:
        if self.edit_mode:
            self.add_draft_point(lat, lon)
        else:
            self.status_label.setText(f"Point cliqué : {lat:.5f} ; {lon:.5f}")

    def _on_layer_changed_from_map(self, name: str) -> None:
        """Le fond de carte se choisit dans le sélecteur de la carte."""
        self.status_label.setText(f"Fond de carte : {name}")

    def _show_about(self) -> None:
        QMessageBox.about(
            self,
            f"À propos de {APP_NAME}",
            f"<b>{APP_NAME}</b> version {APP_VERSION}<br><br>"
            "Création et gestion de traces de randonnée (GPX).<br><br>"
            f"Données utilisateur :<br><code>{db_path()}</code>",
        )

    def closeEvent(self, event):  # noqa: N802
        self._closing = True
        # Couper les remontées de la carte avant de fermer la base : un appel
        # tardif touchant une base close ferait avorter le processus.
        for signal in (
            self.map_view.map_ready,
            self.map_view.map_clicked,
            self.map_view.view_changed,
            self.map_view.layer_changed,
            self.map_view.undo_requested,
            self.map_view.point_moved,
            self.map_view.point_context,
            self.map_view.point_selected,
            self.map_view.point_inserted,
        ):
            try:
                signal.disconnect()
            except TypeError:
                pass
        self.db.close()
        super().closeEvent(event)
