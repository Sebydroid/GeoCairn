"""Capture l'interface dans un PNG pour un contrôle visuel rapide.

    python tests/snapshot_window.py [fichier.png]

Alimente l'application avec les GPX d'exemple du projet s'ils sont présents,
reprend la première trace en édition, puis capture la fenêtre.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PyQt6.QtCore import QTimer  # noqa: E402
from PyQt6.QtWidgets import QMessageBox  # noqa: E402

from carto.app import create_app  # noqa: E402
from carto.database import Database  # noqa: E402
from carto.ui.main_window import MainWindow  # noqa: E402

EXEMPLES = Path(__file__).resolve().parent.parent / "GPX exemples"


def main() -> int:
    destination = Path(sys.argv[1] if len(sys.argv) > 1 else "interface.png")
    base = Path("apercu-carto.db")
    for suffixe in ("", "-wal", "-shm"):
        Path(str(base) + suffixe).unlink(missing_ok=True)

    app = create_app(["carto"])
    # Aucune boîte de dialogue ne doit interrompre la capture.
    QMessageBox.warning = staticmethod(lambda *a, **k: None)
    QMessageBox.information = staticmethod(lambda *a, **k: None)

    database = Database(base)
    window = MainWindow(db=database)
    window.resize(1180, 680)
    window.show()

    panel = window.tree_panel
    dossier = database.create_folder("Rallye 2016")
    panel.refresh()
    panel.select_folder(dossier)

    fichiers = [str(f) for f in sorted(EXEMPLES.glob("Parcours*.gpx"))]
    importees = window.import_gpx(fichiers) if fichiers else []
    if importees:
        window.resume_track(importees[0])
        window.points_panel.select_index(12)

    def capture() -> None:
        window.grab().save(str(destination))
        print(f"traces importées : {len(importees)}", flush=True)
        print(f"points listés    : {window.points_panel.list.count()}", flush=True)
        print(f"statut           : {window.status_label.text()}", flush=True)
        print(f"capture écrite   : {destination.resolve()}", flush=True)
        app.quit()

    QTimer.singleShot(5000, capture)
    code = app.exec()
    database.close()
    for suffixe in ("", "-wal", "-shm"):
        Path(str(base) + suffixe).unlink(missing_ok=True)
    return code


if __name__ == "__main__":
    sys.exit(main())
