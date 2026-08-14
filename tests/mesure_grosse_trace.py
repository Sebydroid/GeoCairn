"""Mesure le temps de reprise d'une trace très dense.

    python tests/mesure_grosse_trace.py

Sert à vérifier que l'édition point par point reste utilisable sur les traces
réelles les plus lourdes du projet (plusieurs milliers de points).
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PyQt6.QtCore import QEventLoop, QTimer  # noqa: E402

from geocairn.app import create_app  # noqa: E402
from geocairn.database import Database  # noqa: E402
from geocairn.gpx import parse_gpx  # noqa: E402
from geocairn.ui.main_window import MainWindow  # noqa: E402

EXEMPLES = Path(__file__).resolve().parent.parent / "GPX exemples"


def attendre(condition, timeout_ms=30000) -> bool:
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


def js(view, script, timeout_ms=30000):
    resultat = {}
    view.page().runJavaScript(script, lambda v: resultat.update(value=v))
    attendre(lambda: "value" in resultat, timeout_ms)
    return resultat.get("value")


def main() -> int:
    fichier = EXEMPLES / "Repérage week-end jeune.gpx"
    candidats = sorted(EXEMPLES.glob("*.gpx")) if EXEMPLES.is_dir() else []
    if not candidats:
        print("aucun fichier d'exemple", flush=True)
        return 0
    if not fichier.is_file():
        fichier = max(
            candidats,
            key=lambda f: sum(len(t.points) for t in parse_gpx(f)),
        )

    app = create_app(["geocairn"])
    base = Path("mesure-geocairn.db")
    for suffixe in ("", "-wal", "-shm"):
        Path(str(base) + suffixe).unlink(missing_ok=True)

    database = Database(base)
    window = MainWindow(db=database)
    window.show()
    attendre(lambda: window.map_view.is_ready)

    traces = parse_gpx(fichier)
    trace = max(traces, key=lambda t: len(t.points))
    track_id = database.create_track(trace.name, points=trace.points)
    window.tree_panel.refresh()
    print(f"fichier : {fichier.name}", flush=True)
    print(f"trace   : {trace.name} — {len(trace.points)} points", flush=True)

    debut = time.perf_counter()
    window.resume_track(track_id)
    attendre(lambda: js(window.map_view, "geocairn.draftCount()") == len(trace.points))
    print(f"reprise et affichage : {time.perf_counter() - debut:.2f} s", flush=True)
    print(f"poignées dessinées   : "
          f"{js(window.map_view, 'draft.vertices.getLayers().length')}", flush=True)

    debut = time.perf_counter()
    window.move_draft_point(10, 49.0, 1.4)
    attendre(lambda: js(window.map_view, "geocairn.draftCount()") == len(trace.points))
    print(f"déplacement d'un point : {time.perf_counter() - debut:.2f} s", flush=True)

    debut = time.perf_counter()
    window.points_panel.refresh(window.draft)
    print(f"rafraîchissement du panneau : "
          f"{time.perf_counter() - debut:.2f} s", flush=True)

    database.close()
    for suffixe in ("", "-wal", "-shm"):
        Path(str(base) + suffixe).unlink(missing_ok=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
