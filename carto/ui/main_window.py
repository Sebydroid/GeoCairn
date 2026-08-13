"""Fenêtre principale : arborescence à gauche, carte à droite."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QPoint, Qt
from PyQt6.QtGui import QAction, QKeySequence
from PyQt6.QtWidgets import (
    QApplication,
    QFileDialog,
    QInputDialog,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QProgressDialog,
    QSplitter,
    QStyle,
    QToolBar,
)

from .. import APP_NAME, APP_VERSION
from ..config import db_path
from ..database import Database
from ..editor import DraftTrack
from ..elevation import ElevationError, fetch_elevations
from ..geo import bounds, format_length, total_length
from ..gpx import (
    GpxParseError,
    count_waypoints,
    parse_gpx,
    safe_filename,
    write_gpx,
)
from .elevation_fetcher import ElevationFetcher
from .map_view import MapView
from .points_panel import PointsPanel
from .profile_panel import SOURCE_ELE_SERVICE, ProfilePanel
from .toolbar_icons import toolbar_icon
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
        #: Altitude demandée à l'IGN au fil de la saisie, en arrière-plan.
        self.elevation_fetcher = ElevationFetcher(self)
        #: Mode saisie : porté par la fenêtre, reflété par les deux boutons.
        self._edit_mode = False

        self.tree_panel = TreePanel(self.db, self.visible_tracks, self)
        self.points_panel = PointsPanel(self)
        self.map_view = MapView(self)

        left = QSplitter(Qt.Orientation.Vertical, self)
        left.addWidget(self.tree_panel)
        left.addWidget(self.points_panel)
        left.setStretchFactor(0, 3)
        left.setStretchFactor(1, 2)
        left.setSizes([480, 320])

        self.profile_panel = ProfilePanel(self)
        droite = QSplitter(Qt.Orientation.Vertical, self)
        droite.addWidget(self.map_view)
        droite.addWidget(self.profile_panel)
        droite.setStretchFactor(0, 4)
        droite.setStretchFactor(1, 1)
        droite.setSizes([560, 170])

        splitter = QSplitter(Qt.Orientation.Horizontal, self)
        splitter.addWidget(left)
        splitter.addWidget(droite)
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
        self.map_view.point_selected.connect(self.select_point)
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

        self.elevation_fetcher.resolved.connect(self._on_elevations_resolved)
        self.elevation_fetcher.failed.connect(self._on_elevation_failed)
        self.elevation_fetcher.suspended.connect(self.status_label.setText)

        self.points_panel.point_selected.connect(self.select_point)
        self.points_panel.points_selected.connect(self.select_points)
        self.points_panel.delete_requested.connect(self.remove_draft_points)
        self.points_panel.split_requested.connect(self.split_draft)

        self.tree_panel.selection_changed.connect(self._on_tree_selection)
        self.tree_panel.reverse_requested.connect(self.reverse_track)
        self.tree_panel.elevation_requested.connect(self.fetch_elevations_for)
        self.tree_panel.decimate_requested.connect(self.decimate_track)
        self.profile_panel.point_clicked.connect(self.select_point)

        self._update_draft_actions()

    # ------------------------------------------------------------ interface

    def _build_actions(self) -> None:
        style = self.style()

        self.action_create = QAction("Créer une trace", self)
        self.action_create.setIcon(toolbar_icon("creer"))
        self.action_create.setCheckable(True)
        self.action_create.setShortcut("Ctrl+N")
        self.action_create.setToolTip(
            "Mode saisie : chaque clic gauche sur la carte ajoute un point (Ctrl+N)"
        )
        self.action_create.toggled.connect(self.set_edit_mode)

        self.action_undo = QAction("Annuler le dernier point", self)
        self.action_undo.setIcon(toolbar_icon("annuler"))
        self.action_undo.setShortcut(QKeySequence.StandardKey.Undo)
        # Le QWebEngineView capte le clavier : sans ce contexte, Ctrl+Z ne
        # remonterait pas jusqu'à la fenêtre.
        self.action_undo.setShortcutContext(
            Qt.ShortcutContext.ApplicationShortcut
        )
        self.action_undo.triggered.connect(self.undo_last_point)

        self.action_save = QAction("Enregistrer", self)
        self.action_save.setIcon(toolbar_icon("enregistrer"))
        self.action_save.setShortcut(QKeySequence.StandardKey.Save)
        self.action_save.setShortcutContext(
            Qt.ShortcutContext.ApplicationShortcut
        )
        self.action_save.setToolTip(
            "Enregistrer le brouillon dans le dossier sélectionné (Ctrl+S)"
        )
        self.action_save.triggered.connect(lambda: self.save_draft())

        self.action_clear = QAction("Effacer le brouillon", self)
        self.action_clear.setIcon(toolbar_icon("effacer"))
        # triggered() transmet un booléen « checked » : sans lambda, il serait
        # reçu comme `confirm` et sauterait la demande de confirmation.
        self.action_clear.triggered.connect(lambda: self.clear_draft())

        self.action_resume = QAction("Modifier la trace", self)
        self.action_resume.setIcon(toolbar_icon("modifier"))
        self.action_resume.setCheckable(True)
        self.action_resume.setToolTip(
            "Reprendre la trace sélectionnée pour la prolonger ou la corriger"
        )
        self.action_resume.toggled.connect(self._on_resume_toggled)

        self.action_close_loop = QAction("Fermer la boucle", self)
        self.action_close_loop.setIcon(toolbar_icon("boucle"))
        self.action_close_loop.setToolTip(
            "Ramener le tracé à son point de départ"
        )
        self.action_close_loop.triggered.connect(lambda: self.close_draft_loop())

        self.action_import = QAction("Importer un GPX", self)
        self.action_import.setIcon(toolbar_icon("import"))
        self.action_import.setShortcut("Ctrl+I")
        self.action_import.setToolTip(
            "Importer un ou plusieurs fichiers GPX dans le dossier sélectionné"
        )
        self.action_import.triggered.connect(lambda: self.import_gpx())

        self.action_export = QAction("Exporter en GPX", self)
        self.action_export.setIcon(toolbar_icon("export"))
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

        # Trois groupes, dans l'ordre où l'on s'en sert : les échanges avec
        # l'extérieur, l'entrée en édition, puis les gestes d'édition.
        toolbar.addAction(self.action_import)
        toolbar.addAction(self.action_export)
        toolbar.addSeparator()
        toolbar.addAction(self.action_create)
        toolbar.addAction(self.action_resume)
        toolbar.addSeparator()
        toolbar.addAction(self.action_undo)
        toolbar.addAction(self.action_close_loop)
        toolbar.addAction(self.action_clear)
        toolbar.addSeparator()
        toolbar.addAction(self.action_save)

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
        return self._edit_mode

    def set_edit_mode(self, enabled: bool) -> None:
        """Active ou quitte le mode saisie ; le brouillon reste en mémoire.

        L'état est porté par la fenêtre, pas par la case du bouton : c'est lui
        qui décide lequel des deux boutons — créer ou modifier — apparaît
        enfoncé.
        """
        enabled = bool(enabled)
        if self._edit_mode == enabled:
            self._update_draft_actions()
            return

        self._edit_mode = enabled
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
        self._request_elevation(len(self.draft) - 1)

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
        if self.draft.is_existing:
            self.action_save.setToolTip(
                f"Écrire les modifications dans « {self.draft.name} » (Ctrl+S)"
            )
        else:
            self.action_save.setToolTip(
                "Enregistrer le brouillon dans le dossier sélectionné (Ctrl+S)"
            )

        # Un seul des deux boutons de mode apparaît enfoncé, selon qu'on
        # dessine une trace neuve ou qu'on en modifie une existante.
        for action, actif in (
            (self.action_create, self._edit_mode and not self.draft.is_existing),
            (self.action_resume, self._edit_mode and self.draft.is_existing),
        ):
            action.blockSignals(True)
            action.setChecked(actif)
            action.blockSignals(False)

        self.tree_panel.set_editing_track(
            self.draft.track_id if self.draft.is_existing else None
        )
        self.action_close_loop.setEnabled(
            len(self.draft) >= 3 and not self.draft.is_loop
        )
        self.draft_label.setText(self.draft.summary())
        if self.draft.is_empty:
            kind, ident = self.tree_panel.current_selection()
            self._on_tree_selection(kind, ident)
        else:
            self.points_panel.refresh(self.draft)
            self.profile_panel.set_points(self.draft.points, self.draft.name)

    # --------------------------------------------- édition avancée (Jalon 6)

    def resume_track(self, track_id: int) -> bool:
        """Reprend une trace enregistrée pour la prolonger ou la corriger."""
        track = self.db.get_track(track_id, with_points=True)
        if track is None or not track.points:
            self.status_label.setText("Cette trace ne contient aucun point.")
            # Sans cela, le bouton « Modifier » resterait enfoncé alors que
            # rien n'a été repris.
            self._update_draft_actions()
            return False

        if not self.draft.is_empty and not self._confirm_discard_draft():
            self._update_draft_actions()
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

    def _on_resume_toggled(self, checked: bool) -> None:
        """Le bouton « Modifier » entre en modification, et en ressort."""
        if not checked:
            self.finish_editing()
            return
        self._resume_selected_track()

    def _resume_selected_track(self) -> None:
        kind, ident = self.tree_panel.current_selection()
        if kind != KIND_TRACK:
            QMessageBox.information(
                self,
                "Aucune trace sélectionnée",
                "Sélectionnez une trace dans l'arborescence pour la modifier.",
            )
            self._update_draft_actions()   # le bouton se relève
            return
        self.resume_track(int(ident))

    def finish_editing(self) -> bool:
        """Quitte les modes saisie et modification, brouillon compris."""
        if not self.draft.is_empty and not self._confirm_discard_draft():
            self._update_draft_actions()
            return False
        self.draft.reset()
        self.map_view.clear_draft()
        self.set_edit_mode(False)
        self._update_draft_actions()
        return True

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

    # ------------------------------- consultation hors édition (Jalon 6+)

    def _on_tree_selection(self, kind: str, ident) -> None:
        """Sélectionner une trace montre ses points et son profil.

        Pendant une édition, le brouillon garde la main : c'est lui qui est
        listé et profilé.
        """
        if not self.draft.is_empty:
            return
        if kind != KIND_TRACK or ident is None:
            self.points_panel.show_points([], "")
            self.profile_panel.set_points([], "")
            return

        track = self.db.get_track(int(ident), with_points=True)
        if track is None:
            return
        self.points_panel.show_points(track.points, track.name)
        self.profile_panel.set_points(track.points, track.name)

    def displayed_points(self) -> list:
        """Points actuellement listés : ceux du brouillon, ou de la sélection."""
        if not self.draft.is_empty:
            return self.draft.points
        kind, ident = self.tree_panel.current_selection()
        if kind != KIND_TRACK or ident is None:
            return []
        track = self.db.get_track(int(ident), with_points=True)
        return track.points if track is not None else []

    def focus_point(self, index: int, center: bool = True) -> bool:
        """Met un point en avant sur la carte, et l'y centre si demandé.

        En édition, le repère du brouillon suffit ; en consultation, un repère
        indépendant est posé sur la carte.
        """
        points = self.displayed_points()
        if not 0 <= index < len(points):
            return False
        point = points[index]

        if self.draft.is_empty:
            if center:
                self.map_view.focus_point(point.lat, point.lon)
        else:
            self.map_view.select_draft_point(index, pan=center)
        self.status_label.setText(
            f"Point {index + 1} sur {len(points)} — "
            f"{point.lat:.5f} ; {point.lon:.5f}"
        )
        return True

    def select_point(self, index: int, center: bool = True) -> bool:
        """Désigne un point : liste, carte et profil se mettent d'accord.

        Point d'entrée unique des trois vues ; aucune ne réémet en retour, ce
        qui évite les allers-retours sans fin.
        """
        self.points_panel.select_index(index)
        self.profile_panel.select_index(index)
        return self.focus_point(index, center=center)

    def select_points(self, indexes) -> int:
        """Désigne plusieurs points à la fois dans les trois vues."""
        points = self.displayed_points()
        retenus = [i for i in indexes if 0 <= i < len(points)]
        self.profile_panel.select_indexes(retenus)

        if self.draft.is_empty:
            self.map_view.focus_points(
                [(points[i].lat, points[i].lon) for i in retenus]
            )
        else:
            self.map_view.select_draft_points(retenus)

        if retenus:
            self.status_label.setText(
                f"{len(retenus)} points sélectionnés sur {len(points)}."
            )
        return len(retenus)

    def _refresh_profile(self) -> None:
        """Met le profil en phase avec la trace en cours d'édition."""
        if self.draft.is_empty:
            kind, ident = self.tree_panel.current_selection()
            self._on_tree_selection(kind, ident)
        else:
            self.profile_panel.set_points(self.draft.points, self.draft.name)

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

    # ------------------------------- altitude au fil de la saisie (IGN)

    def _request_elevation(self, index: int) -> None:
        """Demande l'altitude d'un point du brouillon, sans bloquer."""
        if not 0 <= index < len(self.draft):
            return
        point = self.draft.points[index]
        self.elevation_fetcher.request([(index, point.lat, point.lon)])

    def _on_elevations_resolved(self, resultats) -> None:
        """Applique les altitudes reçues, si les points n'ont pas bougé.

        Le brouillon a pu changer pendant l'aller-retour réseau : on ne
        renseigne que les points restés aux coordonnées demandées.
        """
        applique = False
        for index, lat, lon, altitude in resultats:
            if altitude is None or not 0 <= index < len(self.draft):
                continue
            point = self.draft.points[index]
            if (point.lat, point.lon) != (lat, lon):
                continue
            applique |= self.draft.set_service_elevation(index, altitude)

        if applique:
            self.points_panel.refresh(self.draft)
            self.profile_panel.set_points(self.draft.points, self.draft.name)

    def _on_elevation_failed(self, message: str) -> None:
        """Une panne du service ne doit rien interrompre."""
        self.status_label.setText(f"Altitude non récupérée — {message}")

    def move_draft_point(self, index: int, lat: float, lon: float) -> bool:
        """Repositionne un point après un glisser sur la carte."""
        if not self.draft.move_point(index, lat, lon):
            return False
        # L'altitude d'origine ne vaut plus rien à cet endroit : on la vide en
        # attendant celle du nouvel emplacement.
        self.draft.set_service_elevation(index, None)
        self.map_view.move_draft_point(index, lat, lon)
        self._update_draft_actions()
        self.status_label.setText(
            f"Point {index + 1} déplacé en {lat:.5f} ; {lon:.5f}"
        )
        self._request_elevation(index)
        return True

    def insert_draft_point(self, index: int, lat: float, lon: float) -> bool:
        """Insère un point sur un segment du tracé (clic sur la ligne)."""
        if self.draft.insert_point(index, lat, lon) is None:
            return False
        self.map_view.insert_draft_point(index, lat, lon)
        self._update_draft_actions()
        # Le point est posé là où l'utilisateur a cliqué : le désigner suffit,
        # recentrer la carte ferait sauter la vue sans raison.
        self.select_point(index, center=False)
        self.status_label.setText(
            f"Point inséré en position {index + 1} sur {len(self.draft)}."
        )
        self._request_elevation(index)
        return True

    def show_point_menu(self, index: int, x: int, y: int) -> None:
        """Menu au clic droit sur un point de la trace en édition."""
        if not 0 <= index < len(self.draft):
            return
        self.select_point(index)

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
        if self.draft.is_existing and self.db.get_track(self.draft.track_id) is None:
            self._detach_draft_if_gone({self.draft.track_id})

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

    def reverse_track(self, track_id: int) -> bool:
        """Inverse le sens de parcours d'une trace enregistrée."""
        track = self.db.get_track(track_id)
        if track is None:
            return False
        if not self.db.reverse_track(track_id):
            self.status_label.setText(
                "Une trace d'un seul point n'a pas de sens de parcours."
            )
            return False

        if track_id in self.visible_tracks:
            self.show_track(track_id)   # redessine flèches et repères
        self.tree_panel.refresh()
        self.tree_panel.select_track(track_id)
        self._refresh_profile()
        self.status_label.setText(f"Sens de « {track.name} » inversé.")
        return True

    def fetch_elevations_for(self, track_id: int) -> int | None:
        """Renseigne l'altitude des points par le service altimétrique IGN."""
        track = self.db.get_track(track_id, with_points=True)
        if track is None or not track.points:
            return None

        dialogue = QProgressDialog(
            f"Calcul de l'altitude de « {track.name} »…",
            "Interrompre",
            0,
            len(track.points),
            self,
        )
        dialogue.setWindowTitle("Altitude IGN")
        dialogue.setMinimumDuration(0)
        # Le calcul fait tourner la boucle d'évènements pour rester réactif :
        # sans dialogue modal, l'utilisateur pourrait supprimer la trace, voire
        # fermer la fenêtre, pendant que le résultat est encore attendu.
        dialogue.setWindowModality(Qt.WindowModality.ApplicationModal)
        dialogue.setValue(0)

        def progression(faits: int, total: int) -> bool:
            dialogue.setMaximum(total)
            dialogue.setValue(faits)
            QApplication.processEvents()
            return not dialogue.wasCanceled()

        try:
            altitudes = fetch_elevations(track.points, on_progress=progression)
        except ElevationError as exc:
            dialogue.close()
            QMessageBox.warning(
                self,
                "Altitude indisponible",
                f"{exc}\n\nLe calcul demande une connexion à Internet ; la "
                "couverture se limite au territoire français.",
            )
            return None
        finally:
            dialogue.close()

        renseignes = self.db.set_service_elevations(track_id, altitudes)
        self._refresh_profile()
        self.profile_panel.set_source(SOURCE_ELE_SERVICE)

        if renseignes == 0:
            self.status_label.setText(
                "Aucune altitude obtenue : trace hors couverture du service."
            )
        else:
            self.status_label.setText(
                f"Altitude calculée pour {renseignes} points sur "
                f"{len(track.points)}."
            )
        return renseignes

    def decimate_track(self, track_id: int, cible: int | None = None) -> int | None:
        """Crée une copie allégée d'une trace trop dense.

        `cible` sert aux tests ; sans elle, le nombre de points est demandé.
        """
        track = self.db.get_track(track_id)
        if track is None:
            return None
        if track.point_count < 3:
            QMessageBox.information(
                self,
                "Décimation impossible",
                "Cette trace compte trop peu de points pour être allégée.",
            )
            return None

        if cible is None:
            propose = max(2, track.point_count // 4)
            cible, accepte = QInputDialog.getInt(
                self,
                f"Décimer « {track.name} »",
                f"Cette trace compte {track.point_count} points.\n"
                "Nombre de points souhaité (le résultat sera approchant) :",
                propose,
                2,
                track.point_count - 1,
                10,
            )
            if not accepte:
                return None

        copie = self.db.decimate_track(track_id, cible)
        if copie is None:
            self.status_label.setText(
                "La trace compte déjà moins de points que demandé."
            )
            return None

        obtenu = self.db.get_track(copie)
        self.tree_panel.refresh()
        self.tree_panel.select_track(copie)
        self.display_track(copie)
        self.status_label.setText(
            f"« {track.name} » décimée : {track.point_count} points ramenés à "
            f"{obtenu.point_count} dans « {obtenu.name} »."
        )
        return copie

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
        # Les deux sources n'existent plus : sans cela leur tracé restait
        # dessiné sur la carte, superposé à la fusion, sans aucun moyen de
        # l'effacer puisque l'arborescence ne les propose plus.
        self.forget_tracks([track_id, other_id])
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

        # La trace reprise a pu disparaître entre-temps (suppression, fusion) :
        # le brouillon redevient alors une trace neuve plutôt que d'écrire dans
        # une trace inexistante.
        if self.draft.is_existing and self.db.get_track(self.draft.track_id) is None:
            self._detach_draft_if_gone({self.draft.track_id})

        if self.draft.is_existing:
            # Modification d'une trace existante : on écrit directement, sans
            # redemander de nom. Le renommage se fait par F2 ou le clic droit.
            track_id = self.draft.track_id
            self.db.replace_points(track_id, self.draft.points)
            # Une boucle fermée pendant la modification doit rester une boucle.
            self.db.set_track_loop(track_id, self.draft.is_loop)
            message = f"Modifications de « {self.draft.name} » enregistrées."
        else:
            if name is None:
                name, accepted = QInputDialog.getText(
                    self, "Enregistrer la trace", "Nom de la trace :",
                    text=self.draft.name,
                )
                if not accepted or not name.strip():
                    return None
            track_id = self.db.create_track(
                name,
                folder_id=self.tree_panel.current_folder_id(),
                points=self.draft.points,
                is_loop=self.draft.is_loop,
            )
            message = f"Trace « {name} » enregistrée."

        self.draft.reset()
        self.map_view.clear_draft()
        # L'enregistrement clôt le travail : on quitte les modes saisie et
        # modification plutôt que de laisser croire qu'on édite encore.
        self.set_edit_mode(False)
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
        disparues = {int(t) for t in track_ids}
        for track_id in disparues:
            self.map_view.hide_track(track_id)
            self.visible_tracks.discard(track_id)
        self._detach_draft_if_gone(disparues)
        self.tree_panel.refresh_bulbs()

    def _detach_draft_if_gone(self, disparues: set[int]) -> bool:
        """Détache le brouillon de la trace qu'il modifiait si elle a disparu.

        Supprimer (ou fusionner) une trace pendant qu'on la modifie laissait le
        brouillon rattaché à un identifiant qui n'existe plus : l'enregistrement
        suivant levait alors une erreur au beau milieu d'un signal Qt, ce qui
        interrompait tout le programme. Le travail en cours est conservé, mais
        redevient une trace neuve.
        """
        if self.draft.track_id is None or self.draft.track_id not in disparues:
            return False

        points = self.draft.points
        ancien = self.draft.name
        self.draft.reset(name=ancien)
        self.draft.set_points(points)
        self._update_draft_actions()
        self.status_label.setText(
            f"« {ancien} » a été supprimée : le tracé en cours est devenu une "
            "trace neuve, à enregistrer sous un nouveau nom."
        )
        return True

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
        # La carte peut finir de charger après la fermeture de la fenêtre, ou
        # après que la base a été fermée par ailleurs : l'exception levée dans
        # ce slot Qt ferait avorter le processus.
        if self._closing or self.db.closed:
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
        # Laisser les interrogations d'altitude se terminer avant de fermer la
        # base : elles n'y touchent pas, mais autant ne rien laisser en vol.
        self.elevation_fetcher.enabled = False
        self.elevation_fetcher.wait(2000)
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
