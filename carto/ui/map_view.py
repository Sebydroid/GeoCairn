"""Vue cartographique interactive (Leaflet dans un QWebEngineView)."""

from __future__ import annotations

import json

from PyQt6.QtCore import QObject, QUrl, pyqtSignal, pyqtSlot
from PyQt6.QtWebChannel import QWebChannel
from PyQt6.QtWebEngineCore import QWebEnginePage, QWebEngineSettings
from PyQt6.QtWebEngineWidgets import QWebEngineView

from ..config import resource_path

#: Couches disponibles, dans l'ordre du sélecteur (identiques à map.html).
LAYER_NAMES = [
    "Plan (OpenStreetMap)",
    "Aérienne / Satellite",
    "IGN Plan",
    "IGN Carte topographique",
    "Photos aériennes IGN",
]


class MapBridge(QObject):
    """Objet exposé au JavaScript via QWebChannel."""

    ready = pyqtSignal()
    clicked = pyqtSignal(float, float)
    view_changed = pyqtSignal(float, float, int)
    layer_changed = pyqtSignal(str)
    undo_requested = pyqtSignal()
    point_moved = pyqtSignal(int, float, float)
    point_context = pyqtSignal(int)
    point_selected = pyqtSignal(int)

    @pyqtSlot()
    def js_ready(self) -> None:
        self.ready.emit()

    @pyqtSlot()
    def js_undo_request(self) -> None:
        self.undo_requested.emit()

    @pyqtSlot(int, float, float)
    def js_point_moved(self, index: int, lat: float, lon: float) -> None:
        self.point_moved.emit(index, lat, lon)

    @pyqtSlot(int)
    def js_point_context(self, index: int) -> None:
        self.point_context.emit(index)

    @pyqtSlot(int)
    def js_point_selected(self, index: int) -> None:
        self.point_selected.emit(index)

    @pyqtSlot(float, float)
    def js_map_click(self, lat: float, lon: float) -> None:
        self.clicked.emit(lat, lon)

    @pyqtSlot(float, float, int)
    def js_view_changed(self, lat: float, lon: float, zoom: int) -> None:
        self.view_changed.emit(lat, lon, zoom)

    @pyqtSlot(str)
    def js_layer_changed(self, name: str) -> None:
        self.layer_changed.emit(name)


class _Page(QWebEnginePage):
    """Page qui relaie la console JavaScript vers un signal Qt (débogage)."""

    console = pyqtSignal(str)

    def javaScriptConsoleMessage(self, level, message, line, source):  # noqa: N802
        self.console.emit(f"[JS:{line}] {message}")


class MapView(QWebEngineView):
    """Carte interactive : couches, déplacement, zoom, clics."""

    map_ready = pyqtSignal()
    map_clicked = pyqtSignal(float, float)
    view_changed = pyqtSignal(float, float, int)
    layer_changed = pyqtSignal(str)
    undo_requested = pyqtSignal()
    point_moved = pyqtSignal(int, float, float)
    point_context = pyqtSignal(int)
    point_selected = pyqtSignal(int)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.is_ready = False

        self._page = _Page(self)
        self.setPage(self._page)

        settings = self._page.settings()
        settings.setAttribute(
            QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True
        )
        settings.setAttribute(
            QWebEngineSettings.WebAttribute.JavascriptEnabled, True
        )
        settings.setAttribute(
            QWebEngineSettings.WebAttribute.ShowScrollBars, False
        )

        self.bridge = MapBridge()
        self.bridge.ready.connect(self._on_ready)
        self.bridge.clicked.connect(self.map_clicked)
        self.bridge.view_changed.connect(self.view_changed)
        self.bridge.layer_changed.connect(self.layer_changed)
        self.bridge.undo_requested.connect(self.undo_requested)
        self.bridge.point_moved.connect(self.point_moved)
        self.bridge.point_context.connect(self.point_context)
        self.bridge.point_selected.connect(self.point_selected)

        self._channel = QWebChannel(self._page)
        self._channel.registerObject("bridge", self.bridge)
        self._page.setWebChannel(self._channel)

        self.load(QUrl.fromLocalFile(str(resource_path("map.html"))))

    # ------------------------------------------------------------------ API

    def _on_ready(self) -> None:
        self.is_ready = True
        self.map_ready.emit()

    def run_js(self, script: str) -> None:
        self._page.runJavaScript(script)

    def set_view(self, lat: float, lon: float, zoom: int | None = None) -> None:
        zoom_arg = "undefined" if zoom is None else str(int(zoom))
        self.run_js(f"carto.setView({lat!r}, {lon!r}, {zoom_arg});")

    def fit_bounds(self, south_west: tuple, north_east: tuple) -> None:
        bounds = json.dumps([list(south_west), list(north_east)])
        self.run_js(f"carto.fitBounds({bounds});")

    def set_base_layer(self, name: str) -> None:
        self.run_js(f"carto.setBaseLayer({json.dumps(name)});")

    # -------------------------------------------------------------- brouillon

    def set_edit_mode(self, enabled: bool) -> None:
        """Active le mode saisie (curseur en croix sur la carte)."""
        self.run_js(f"carto.setEditMode({str(bool(enabled)).lower()});")

    def append_draft_point(self, lat: float, lon: float) -> None:
        """Ajoute un point à la polyligne du brouillon."""
        self.run_js(f"carto.appendDraftPoint({lat!r}, {lon!r});")

    def pop_draft_point(self) -> None:
        """Retire le dernier point de la polyligne du brouillon."""
        self.run_js("carto.popDraftPoint();")

    def set_draft(self, points) -> None:
        """Réaffiche entièrement le brouillon à partir d'une liste de points."""
        coords = json.dumps([[p.lat, p.lon] for p in points])
        self.run_js(f"carto.setDraft({coords});")

    def clear_draft(self) -> None:
        self.run_js("carto.clearDraft();")

    def move_draft_point(self, index: int, lat: float, lon: float) -> None:
        """Repositionne un point du brouillon sur la carte."""
        self.run_js(f"carto.movePoint({int(index)}, {lat!r}, {lon!r});")

    def select_draft_point(self, index: int | None) -> None:
        """Met un point en évidence (−1 ou None pour n'en sélectionner aucun)."""
        self.run_js(f"carto.selectPoint({-1 if index is None else int(index)});")

    # -------------------------------------------------- trace affichée (J5)

    def show_track(self, points, color: str = "#1f5fbf", fit: bool = True) -> None:
        """Affiche une trace enregistrée et cadre la carte dessus."""
        coords = json.dumps([[p.lat, p.lon] for p in points])
        self.run_js(
            f"carto.showTrack({coords}, {json.dumps(color)}, "
            f"{str(bool(fit)).lower()});"
        )

    def clear_track(self) -> None:
        self.run_js("carto.clearTrack();")
