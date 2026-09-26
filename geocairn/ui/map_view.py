"""Vue cartographique interactive (Leaflet dans un QWebEngineView)."""

from __future__ import annotations

import json

from PyQt6.QtCore import QObject, QUrl, pyqtSignal, pyqtSlot
from PyQt6.QtWebChannel import QWebChannel
from PyQt6.QtWebEngineCore import QWebEnginePage, QWebEngineSettings
from PyQt6.QtWebEngineWidgets import QWebEngineView

from ..config import resource_path
from ..models import DEFAULT_TRACK_COLOR, DEFAULT_TRACK_OPACITY

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
    point_context = pyqtSignal(int, int, int)
    point_selected = pyqtSignal(int)
    point_inserted = pyqtSignal(int, float, float)
    impression_prete = pyqtSignal()

    @pyqtSlot()
    def js_ready(self) -> None:
        self.ready.emit()

    @pyqtSlot()
    def js_impression_prete(self) -> None:
        self.impression_prete.emit()

    @pyqtSlot()
    def js_undo_request(self) -> None:
        self.undo_requested.emit()

    @pyqtSlot(int, float, float)
    def js_point_moved(self, index: int, lat: float, lon: float) -> None:
        self.point_moved.emit(index, lat, lon)

    @pyqtSlot(int, int, int)
    def js_point_context(self, index: int, x: int, y: int) -> None:
        self.point_context.emit(index, x, y)

    @pyqtSlot(int)
    def js_point_selected(self, index: int) -> None:
        self.point_selected.emit(index)

    @pyqtSlot(int, float, float)
    def js_point_inserted(self, index: int, lat: float, lon: float) -> None:
        self.point_inserted.emit(index, lat, lon)

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
    point_context = pyqtSignal(int, int, int)
    point_selected = pyqtSignal(int)
    point_inserted = pyqtSignal(int, float, float)
    #: Les tuiles demandées par `preparer_impression` sont arrivées.
    impression_prete = pyqtSignal()

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
        self.bridge.point_inserted.connect(self.point_inserted)
        self.bridge.impression_prete.connect(self.impression_prete)

        self._channel = QWebChannel(self._page)
        self._channel.registerObject("bridge", self.bridge)
        self._page.setWebChannel(self._channel)

        self.load(QUrl.fromLocalFile(str(resource_path("map.html"))))

    # ------------------------------------------------------------------ API

    def _on_ready(self) -> None:
        self.is_ready = True
        # La page a pu se charger avant que la disposition ne soit établie.
        self.run_js("geocairn.invalidateSize();")
        self.map_ready.emit()

    def run_js(self, script: str) -> None:
        self._page.runJavaScript(script)

    def invalidate_size(self) -> None:
        """Prévient Leaflet que le conteneur a changé de taille.

        Sans cela, la carte garde la taille qu'elle avait au chargement — nulle
        si le composant n'était pas encore disposé — et le recadrage automatique
        ne déplace plus rien.
        """
        if self.is_ready:
            self.run_js("geocairn.invalidateSize();")

    def resizeEvent(self, event):  # noqa: N802
        super().resizeEvent(event)
        self.invalidate_size()

    def set_view(self, lat: float, lon: float, zoom: int | None = None) -> None:
        zoom_arg = "undefined" if zoom is None else str(int(zoom))
        self.run_js(f"geocairn.setView({lat!r}, {lon!r}, {zoom_arg});")

    def fit_bounds(self, south_west: tuple, north_east: tuple) -> None:
        bounds = json.dumps([list(south_west), list(north_east)])
        self.run_js(f"geocairn.fitBounds({bounds});")

    def set_base_layer(self, name: str) -> None:
        self.run_js(f"geocairn.setBaseLayer({json.dumps(name)});")

    # -------------------------------------------------------------- brouillon

    def set_edit_mode(self, enabled: bool) -> None:
        """Active le mode saisie (curseur en croix sur la carte)."""
        self.run_js(f"geocairn.setEditMode({str(bool(enabled)).lower()});")

    def append_draft_point(self, lat: float, lon: float) -> None:
        """Ajoute un point à la polyligne du brouillon."""
        self.run_js(f"geocairn.appendDraftPoint({lat!r}, {lon!r});")

    def pop_draft_point(self) -> None:
        """Retire le dernier point de la polyligne du brouillon."""
        self.run_js("geocairn.popDraftPoint();")

    def set_draft(self, points) -> None:
        """Réaffiche entièrement le brouillon à partir d'une liste de points."""
        coords = json.dumps([[p.lat, p.lon] for p in points])
        self.run_js(f"geocairn.setDraft({coords});")

    def clear_draft(self) -> None:
        self.run_js("geocairn.clearDraft();")

    def insert_draft_point(self, index: int, lat: float, lon: float) -> None:
        """Insère un point dans la polyligne du brouillon."""
        self.run_js(f"geocairn.insertPoint({int(index)}, {lat!r}, {lon!r});")

    def move_draft_point(self, index: int, lat: float, lon: float) -> None:
        """Repositionne un point du brouillon sur la carte."""
        self.run_js(f"geocairn.movePoint({int(index)}, {lat!r}, {lon!r});")

    def focus_point(self, lat: float, lon: float) -> None:
        """Désigne un point d'une trace consultée et centre la carte dessus."""
        self.run_js(f"geocairn.focusPoint({lat!r}, {lon!r});")

    def focus_points(self, coords) -> None:
        """Désigne plusieurs points d'une trace consultée."""
        valeurs = json.dumps([[lat, lon] for lat, lon in coords])
        self.run_js(f"geocairn.focusPoints({valeurs});")

    def select_draft_points(self, indexes) -> None:
        """Met plusieurs points du brouillon en évidence."""
        valeurs = json.dumps([int(i) for i in indexes])
        self.run_js(f"geocairn.selectPoints({valeurs});")

    def clear_focus(self) -> None:
        self.run_js("geocairn.clearFocus();")

    def select_draft_point(self, index: int | None, pan: bool = True) -> None:
        """Met un point en évidence (−1 ou None pour n'en sélectionner aucun).

        `pan=False` laisse la carte où elle est : utile quand le point vient
        d'être posé à l'endroit même où l'utilisateur a cliqué.
        """
        self.run_js(
            f"geocairn.selectPoint({-1 if index is None else int(index)},"
            f" {str(bool(pan)).lower()});"
        )

    # ------------------------------------------------ traces affichées (J5)

    def show_track(
        self,
        track_id: int,
        points,
        color: str = DEFAULT_TRACK_COLOR,
        opacity: float = DEFAULT_TRACK_OPACITY,
        fit: bool = False,
        name: str = "",
    ) -> None:
        """Affiche une trace enregistrée, sans masquer les autres."""
        coords = json.dumps([[p.lat, p.lon] for p in points])
        self.run_js(
            f"geocairn.showTrack({int(track_id)}, {coords}, {json.dumps(color)},"
            f" {float(opacity)!r}, {str(bool(fit)).lower()},"
            f" {json.dumps(name)});"
        )

    def hide_track(self, track_id: int) -> None:
        self.run_js(f"geocairn.hideTrack({int(track_id)});")

    def clear_tracks(self) -> None:
        self.run_js("geocairn.clearTracks();")

    def set_track_style(
        self, track_id: int, color: str, opacity: float
    ) -> None:
        self.run_js(
            f"geocairn.setTrackStyle({int(track_id)}, {json.dumps(color)},"
            f" {float(opacity)!r});"
        )

    def zoom_tracks(self, track_ids) -> None:
        """Cadre la carte sur une ou plusieurs traces affichées."""
        ids = json.dumps([int(i) for i in track_ids])
        self.run_js(f"geocairn.zoomTracks({ids});")

    # ------------------------------------------------------------ impression

    def set_print_frame(
        self,
        largeur_m: float,
        hauteur_m: float,
        ajuster: bool = False,
        centre: tuple[float, float] | None = None,
    ) -> None:
        """Dessine, au centre de la carte, la zone que couvrira la feuille.

        `ajuster` cadre la carte sur la feuille ; `centre` recentre d'abord
        la carte à cet endroit.
        """
        position = "null, null" if centre is None else f"{centre[0]!r}, {centre[1]!r}"
        self.run_js(
            f"geocairn.setPrintFrame({float(largeur_m)!r}, {float(hauteur_m)!r},"
            f" {str(bool(ajuster)).lower()}, {position});"
        )

    def clear_print_frame(self) -> None:
        self.run_js("geocairn.clearPrintFrame();")

    def preparer_impression(
        self, lat: float, lon: float, zoom: float, couche: str
    ) -> None:
        """Cadre la carte pour le rendu imprimé ; `impression_prete` suivra."""
        self.run_js(
            f"geocairn.preparerImpression({lat!r}, {lon!r}, {float(zoom)!r},"
            f" {json.dumps(couche)});"
        )
