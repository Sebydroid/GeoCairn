"""Interrogation du service altimétrique en arrière-plan.

Pendant le dessin d'une trace, chaque point posé demande son altitude à l'IGN.
L'appel part dans un fil séparé : l'interface ne doit jamais attendre le réseau.

Aucune panne réseau ne remonte sous forme d'exception : une coupure, un service
indisponible ou une réponse illisible se traduisent par un signal `failed`. Au
bout de plusieurs échecs d'affilée, la récupération automatique se met en veille
d'elle-même plutôt que de harceler un service absent.
"""

from __future__ import annotations

from PyQt6.QtCore import QObject, QRunnable, QThreadPool, Qt, pyqtSignal

from ..elevation import ElevationError, fetch_elevations
from ..models import Point

#: Échecs consécutifs au bout desquels la récupération se met en veille.
ECHECS_AVANT_VEILLE = 3


class _Signals(QObject):
    """Porte-signaux du travail de fond.

    Volontairement détaché de la fenêtre : le fil peut se terminer après la
    fermeture de celle-ci, et Qt coupe seul les connexions vers un destinataire
    détruit.
    """

    resolved = pyqtSignal(list)   # [(index, lat, lon, altitude), ...]
    failed = pyqtSignal(str)
    #: Émis en dernier, quelle que soit l'issue : l'appelant peut alors oublier
    #: la requête.
    finished = pyqtSignal()


class _Request(QRunnable):
    """Une interrogation du service, exécutée hors du fil de l'interface."""

    def __init__(self, demandes, fetch=None) -> None:
        super().__init__()
        self.demandes = list(demandes)   # [(index, lat, lon), ...]
        self.signals = _Signals()
        self._fetch = fetch
        # Qt détruirait l'objet à la fin de run(), emportant le porte-signaux
        # avant la remise du résultat. C'est l'appelant qui décide de l'oublier.
        self.setAutoDelete(False)

    def run(self) -> None:
        points = [Point(lat, lon) for _index, lat, lon in self.demandes]
        try:
            try:
                altitudes = fetch_elevations(points, fetch=self._fetch)
            except ElevationError as exc:
                self.signals.failed.emit(str(exc))
                return
            except Exception as exc:  # noqa: BLE001
                # Filet de sécurité : rien venant du réseau ne doit remonter
                # jusqu'à faire tomber l'application.
                self.signals.failed.emit(f"Altitude indisponible : {exc}")
                return

            self.signals.resolved.emit(
                [
                    (index, lat, lon, altitude)
                    for (index, lat, lon), altitude in zip(self.demandes, altitudes)
                ]
            )
        finally:
            self.signals.finished.emit()


class ElevationFetcher(QObject):
    """Fournit les altitudes au fil de la saisie, sans bloquer l'interface."""

    resolved = pyqtSignal(list)
    failed = pyqtSignal(str)
    suspended = pyqtSignal(str)

    def __init__(self, parent=None, fetch=None) -> None:
        super().__init__(parent)
        self.enabled = True
        self.echecs = 0
        self._fetch = fetch
        self._pool = QThreadPool(self)
        # Une seule interrogation à la fois : le service n'aime pas les rafales.
        self._pool.setMaxThreadCount(1)
        #: Interrogations en vol. Qt détruit le QRunnable dès la fin de son
        #: exécution ; sans cette référence, le porte-signaux disparaîtrait avec
        #: lui avant que le résultat n'ait été remis au fil de l'interface, et
        #: l'altitude serait perdue sans explication.
        self._en_vol: set = set()

    def request(self, demandes) -> bool:
        """Demande l'altitude de points désignés par (indice, lat, lon)."""
        if not self.enabled or not demandes:
            return False
        requete = _Request(demandes, fetch=self._fetch)
        self._en_vol.add(requete)
        requete.signals.resolved.connect(self._on_resolved)
        requete.signals.failed.connect(self._on_failed)
        # Connexion explicitement différée : la fin est signalée depuis le fil
        # de travail, et l'oubli doit avoir lieu après la remise du résultat au
        # fil de l'interface, pas avant.
        requete.signals.finished.connect(
            lambda r=requete: self._en_vol.discard(r),
            Qt.ConnectionType.QueuedConnection,
        )
        self._pool.start(requete)
        return True

    def reset(self) -> None:
        """Réveille la récupération après une mise en veille."""
        self.enabled = True
        self.echecs = 0

    def wait(self, timeout_ms: int = 5000) -> bool:
        """Attend la fin des interrogations en cours (fermeture, tests)."""
        return self._pool.waitForDone(timeout_ms)

    # -------------------------------------------------------------- signaux

    def _on_resolved(self, resultats) -> None:
        self.echecs = 0
        self.resolved.emit(resultats)

    def _on_failed(self, message: str) -> None:
        self.echecs += 1
        self.failed.emit(message)
        if self.echecs >= ECHECS_AVANT_VEILLE:
            self.enabled = False
            self.suspended.emit(
                "Altitude automatique suspendue : le service IGN ne répond pas."
            )
