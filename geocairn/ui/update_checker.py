"""Recherche d'une nouvelle version en arrière-plan.

La recherche a lieu au démarrage : elle ne doit donc jamais retarder
l'affichage de la fenêtre, ni faire trébucher le programme si GitHub est
injoignable. L'appel part dans un fil séparé, et toute panne se traduit par un
signal `echouee` plutôt que par une exception.

Le modèle est celui de [elevation_fetcher.py](elevation_fetcher.py), pour les
mêmes raisons : Qt détruit un `QRunnable` dès la fin de son exécution, et le
porte-signaux disparaîtrait avec lui avant que le résultat n'ait été remis au
fil de l'interface.
"""

from __future__ import annotations

from PyQt6.QtCore import QObject, QRunnable, QThreadPool, Qt, pyqtSignal

from ..updates import UpdateError, derniere_version, plus_recente


class _Signals(QObject):
    """Porte-signaux du travail de fond, détaché de la fenêtre."""

    #: La `Version` trouvée si elle est plus récente, None si rien de neuf.
    terminee = pyqtSignal(object)
    echouee = pyqtSignal(str)
    #: Émis en dernier, quelle que soit l'issue.
    finished = pyqtSignal()


class _Recherche(QRunnable):
    """Une interrogation de GitHub, exécutée hors du fil de l'interface."""

    def __init__(self, installee: str, fetch=None) -> None:
        super().__init__()
        self.installee = installee
        self.signals = _Signals()
        self._fetch = fetch
        self.setAutoDelete(False)

    def run(self) -> None:
        try:
            try:
                version = derniere_version(fetch=self._fetch)
            except UpdateError as exc:
                self.signals.echouee.emit(str(exc))
                return
            except Exception as exc:  # noqa: BLE001
                # Filet de sécurité : rien venant du réseau ne doit remonter
                # jusqu'à faire tomber l'application.
                self.signals.echouee.emit(f"Recherche impossible : {exc}")
                return

            self.signals.terminee.emit(
                version if plus_recente(version.numero, self.installee) else None
            )
        finally:
            self.signals.finished.emit()


class UpdateChecker(QObject):
    """Va voir sur GitHub s'il existe une version plus récente."""

    #: `Version` plus récente, ou None si le logiciel est à jour.
    terminee = pyqtSignal(object)
    echouee = pyqtSignal(str)

    def __init__(self, installee: str, parent=None, fetch=None) -> None:
        super().__init__(parent)
        self.installee = installee
        self.enabled = True
        self._fetch = fetch
        self._pool = QThreadPool(self)
        self._pool.setMaxThreadCount(1)
        #: Recherche en vol. Voir la remarque du module sur l'autodestruction
        #: des QRunnable : sans cette référence, le résultat serait perdu.
        self._en_vol: set = set()

    def check(self) -> bool:
        """Lance une recherche. Faux si une autre est déjà en cours."""
        if not self.enabled or self._en_vol:
            return False

        recherche = _Recherche(self.installee, fetch=self._fetch)
        self._en_vol.add(recherche)
        recherche.signals.terminee.connect(self.terminee)
        recherche.signals.echouee.connect(self.echouee)
        # Connexion différée : la fin est signalée depuis le fil de travail, et
        # l'oubli doit avoir lieu après la remise du résultat, pas avant.
        recherche.signals.finished.connect(
            lambda r=recherche: self._en_vol.discard(r),
            Qt.ConnectionType.QueuedConnection,
        )
        self._pool.start(recherche)
        return True

    def wait(self, timeout_ms: int = 3000) -> bool:
        """Attend la fin de la recherche en cours (fermeture, tests)."""
        return self._pool.waitForDone(timeout_ms)
