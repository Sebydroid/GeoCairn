"""Vérifie que l'application supporte l'absence de service altimétrique.

    python tests/check_hors_ligne.py

Détourne le service vers une adresse injoignable, puis dessine une trace comme
le ferait l'utilisateur. Rien ne doit s'interrompre.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PyQt6.QtCore import QEventLoop, QTimer  # noqa: E402

from geocairn import elevation  # noqa: E402
from geocairn.app import create_app  # noqa: E402
from geocairn.database import Database  # noqa: E402
from geocairn.ui.main_window import MainWindow  # noqa: E402

#: Adresse réservée à la documentation : aucune machine ne répond.
INJOIGNABLE = "http://192.0.2.1/altimetrie"


def patienter(ms: int) -> None:
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


def main() -> int:
    elevation.SERVICE_URL = INJOIGNABLE
    elevation.TIMEOUT_S = 2

    app = create_app(["geocairn"])
    base = Path(tempfile.mkdtemp()) / "geocairn.db"
    window = MainWindow(db=Database(base))
    window.show()
    patienter(2000)

    messages = []
    window.elevation_fetcher.failed.connect(messages.append)
    window.elevation_fetcher.suspended.connect(messages.append)

    print("dessin de 6 points sans service altimétrique…", flush=True)
    window.set_edit_mode(True)
    for i in range(6):
        window.add_draft_point(48.930 + i / 1000, 1.440 + i / 1000)
        patienter(400)

    window.elevation_fetcher.wait(10000)
    patienter(500)

    print(f"points dessinés     : {len(window.draft)}", flush=True)
    print(f"altitudes obtenues  : "
          f"{sum(1 for p in window.draft.points if p.ele_service is not None)}",
          flush=True)
    print(f"échecs signalés     : {len(messages)}", flush=True)
    print(f"récupération active : {window.elevation_fetcher.enabled}", flush=True)

    # Le dessin doit rester parfaitement utilisable.
    window.move_draft_point(0, 48.95, 1.46)
    window.undo_last_point()
    track_id = window.save_draft("Sans réseau")
    patienter(300)

    enregistres = window.db.count_points(track_id)
    print(f"trace enregistrée   : {enregistres} points", flush=True)
    print(f"statut              : {window.status_label.text()}", flush=True)

    window.close()
    ok = len(window.draft) == 0 and enregistres == 5
    print("\nRESULTAT :", "aucun plantage, dessin utilisable" if ok else "ANOMALIE",
          flush=True)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
