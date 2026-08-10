"""Fenêtre principale : arborescence à gauche, carte à droite."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction, QKeySequence
from PyQt6.QtWidgets import (
    QComboBox,
    QLabel,
    QMainWindow,
    QMessageBox,
    QSplitter,
    QToolBar,
)

from .. import APP_NAME, APP_VERSION
from ..config import db_path
from ..database import Database
from .map_view import LAYER_NAMES, MapView
from .tree_panel import TreePanel


class MainWindow(QMainWindow):
    """Fenêtre principale de l'application."""

    def __init__(self, db: Database | None = None) -> None:
        super().__init__()
        self.db = db if db is not None else Database()

        self.setWindowTitle(f"{APP_NAME} — Gestion de traces GPX")
        self.resize(1280, 800)

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

        self._build_toolbar()
        self._build_menu()
        self._build_statusbar()

        self.map_view.map_ready.connect(self._on_map_ready)
        self.map_view.view_changed.connect(self._on_view_changed)
        self.map_view.map_clicked.connect(self._on_map_clicked)
        self.map_view.layer_changed.connect(self._on_layer_changed_from_map)

    # ------------------------------------------------------------ interface

    def _build_toolbar(self) -> None:
        toolbar = QToolBar("Barre d'outils", self)
        toolbar.setMovable(False)
        self.addToolBar(toolbar)

        toolbar.addWidget(QLabel("  Fond de carte : "))
        self.layer_combo = QComboBox(self)
        self.layer_combo.addItems(LAYER_NAMES)
        self.layer_combo.setMinimumWidth(190)
        self.layer_combo.currentTextChanged.connect(self.map_view.set_base_layer)
        toolbar.addWidget(self.layer_combo)

    def _build_menu(self) -> None:
        menu = self.menuBar()

        file_menu = menu.addMenu("&Fichier")
        quit_action = QAction("&Quitter", self)
        quit_action.setShortcut(QKeySequence.StandardKey.Quit)
        quit_action.triggered.connect(self.close)
        file_menu.addAction(quit_action)

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
        self.statusBar().addWidget(self.status_label, 1)
        self.statusBar().addPermanentWidget(self.coord_label)

    # -------------------------------------------------------------- signaux

    def _on_map_ready(self) -> None:
        self.status_label.setText("Carte prête.")

    def _on_view_changed(self, lat: float, lon: float, zoom: int) -> None:
        self.coord_label.setText(f"Centre : {lat:.5f} ; {lon:.5f}  —  zoom {zoom}")

    def _on_map_clicked(self, lat: float, lon: float) -> None:
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
