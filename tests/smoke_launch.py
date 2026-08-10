"""Lancement réel de l'application pendant quelques secondes (fumée).

Contrairement aux tests pytest (qui tournent hors écran), ce script ouvre une
vraie fenêtre : il sert à vérifier manuellement que l'application démarre.

    python tests/smoke_launch.py [duree_en_secondes]
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PyQt6.QtCore import QTimer  # noqa: E402

from carto.app import create_app  # noqa: E402
from carto.ui.main_window import MainWindow  # noqa: E402


def main() -> int:
    duration_s = float(sys.argv[1]) if len(sys.argv) > 1 else 6.0

    app = create_app(["carto"])
    window = MainWindow()
    window.show()

    state = {"map_ready": False}
    window.map_view.map_ready.connect(lambda: state.update(map_ready=True))

    def report_and_quit() -> None:
        print(f"fenêtre visible : {window.isVisible()}", flush=True)
        print(f"carte prête     : {state['map_ready']}", flush=True)
        print(f"statut          : {window.status_label.text()}", flush=True)
        print(f"coordonnées     : {window.coord_label.text()}", flush=True)
        app.quit()

    QTimer.singleShot(int(duration_s * 1000), report_and_quit)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
