"""Capture l'interface dans un PNG pour un contrôle visuel rapide.

    python tests/snapshot_window.py [fichier.png]

Alimente l'application avec les GPX d'exemple du projet s'ils sont présents,
affiche plusieurs traces de couleurs différentes, puis capture la fenêtre.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PyQt6.QtCore import QEventLoop, QTimer  # noqa: E402
from PyQt6.QtWidgets import QMessageBox  # noqa: E402

from carto.app import create_app  # noqa: E402
from carto.database import Database  # noqa: E402
from carto.ui.main_window import MainWindow  # noqa: E402
from carto.ui.tree_panel import COULEURS, KIND_FOLDER, KIND_TRACK  # noqa: E402

EXEMPLES = Path(__file__).resolve().parent.parent / "GPX exemples"


def attendre(condition, timeout_ms=20000) -> bool:
    """Fait tourner la boucle Qt jusqu'à ce que `condition` soit vraie."""
    loop = QEventLoop()
    ecoule = {"ms": 0}

    def tick():
        ecoule["ms"] += 50
        if condition() or ecoule["ms"] >= timeout_ms:
            loop.quit()

    timer = QTimer()
    timer.timeout.connect(tick)
    timer.start(50)
    if not condition():
        loop.exec()
    timer.stop()
    return condition()


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
    # Sans cette attente, tout se jouerait avant le chargement de la carte et
    # les commandes envoyées au JavaScript seraient perdues.
    attendre(lambda: window.map_view.is_ready)

    panel = window.tree_panel
    dossier = database.create_folder("Rallye 2016")
    panel.refresh()
    panel.select_folder(dossier)

    fichiers = [str(f) for f in sorted(EXEMPLES.glob("Parcours*.gpx"))]
    importees = window.import_gpx(fichiers) if fichiers else []

    # Une couleur par trace, puis affichage de tout le dossier.
    for rang, track_id in enumerate(importees):
        panel.set_track_color(track_id, COULEURS[rang % len(COULEURS)][1])
    if importees:
        window.show_items(KIND_FOLDER, dossier)
        window.zoom_to_items(KIND_FOLDER, dossier)
        # Deux traces masquées : la capture montre les trois états d'ampoule
        # (allumée, éteinte, et dossier partiellement affiché).
        for track_id in importees[:2]:
            window.hide_track(track_id)
        # La sélection alimente la liste des points et le profil.
        choisie = importees[2] if len(importees) > 2 else importees[0]
        panel.select_track(choisie)
        window.zoom_to_items(KIND_TRACK, choisie)

    def capture() -> None:
        window.grab().save(str(destination))
        print(f"traces importées : {len(importees)}", flush=True)
        print(f"traces affichées : {len(window.visible_tracks)}", flush=True)
        print(f"statut           : {window.status_label.text()}", flush=True)
        print(f"capture écrite   : {destination.resolve()}", flush=True)
        app.quit()

    QTimer.singleShot(6000, capture)
    code = app.exec()
    database.close()
    for suffixe in ("", "-wal", "-shm"):
        Path(str(base) + suffixe).unlink(missing_ok=True)
    return code


if __name__ == "__main__":
    sys.exit(main())
