"""Capture l'interface dans un PNG pour un contrôle visuel rapide.

    python tests/snapshot_window.py [fichier.png]

La zone carte apparaît vide sur la capture : son contenu est rendu par un
processus séparé (Chromium) que Qt ne restitue pas dans un grab().
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PyQt6.QtCore import QTimer  # noqa: E402

from carto.app import create_app  # noqa: E402
from carto.database import Database  # noqa: E402
from carto.ui.main_window import MainWindow  # noqa: E402


def main() -> int:
    destination = Path(sys.argv[1] if len(sys.argv) > 1 else "interface.png")

    app = create_app(["carto"])
    database = Database(Path(app.applicationName() + "-apercu.db"))
    window = MainWindow(db=database)
    window.resize(1100, 620)
    window.show()

    # Jeu de démonstration : deux dossiers, une trace, un brouillon en cours.
    panel = window.tree_panel
    alpes = database.create_folder("Randonnées")
    database.create_folder("2026", parent_id=alpes)
    database.create_track(
        "Boucle de Bueil",
        folder_id=alpes,
        points=[],
    )
    panel.refresh()
    panel.select_folder(alpes)

    window.set_edit_mode(True)
    for lat, lon in [(48.9394, 1.4392), (48.9388, 1.4370), (48.9379, 1.4373)]:
        window.add_draft_point(lat, lon)

    def capture() -> None:
        window.grab().save(str(destination))
        print(f"capture écrite : {destination.resolve()}", flush=True)
        app.quit()

    QTimer.singleShot(4000, capture)
    code = app.exec()
    database.close()
    Path(app.applicationName() + "-apercu.db").unlink(missing_ok=True)
    return code


if __name__ == "__main__":
    sys.exit(main())
