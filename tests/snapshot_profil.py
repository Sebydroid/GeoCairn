"""Capture le profil avec plusieurs grandeurs superposées.

    python tests/snapshot_profil.py [fichier.png]

Utilise une trace d'exemple horodatée et interroge le service altimétrique IGN
pour disposer des trois grandeurs à la fois.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from carto.app import create_app  # noqa: E402
from carto.elevation import ElevationError, apply_elevations, fetch_elevations  # noqa: E402
from carto.geo import has_times  # noqa: E402
from carto.gpx import parse_gpx  # noqa: E402
from carto.ui.profile_panel import (  # noqa: E402
    SOURCE_ELE_FICHIER,
    SOURCE_ELE_SERVICE,
    SOURCE_VITESSE,
    ProfilePanel,
)

EXEMPLES = Path(__file__).resolve().parent.parent / "GPX exemples"


def main() -> int:
    destination = Path(sys.argv[1] if len(sys.argv) > 1 else "profil.png")
    app = create_app(["carto"])

    horodatee = None
    for fichier in sorted(EXEMPLES.glob("*.gpx")):
        for trace in parse_gpx(fichier):
            if has_times(trace.points) and len(trace.points) > 50:
                horodatee = trace
                break
        if horodatee:
            break

    if horodatee is None:
        print("aucune trace horodatée dans les exemples", flush=True)
        return 1

    points = horodatee.points
    print(f"trace : {horodatee.name} — {len(points)} points", flush=True)

    try:
        points = apply_elevations(points, fetch_elevations(points))
        print("altitude IGN obtenue", flush=True)
    except ElevationError as exc:
        print(f"altitude IGN indisponible : {exc}", flush=True)

    panel = ProfilePanel()
    panel.resize(1000, 200)
    panel.set_points(points, horodatee.name)
    panel.set_sources([SOURCE_ELE_FICHIER, SOURCE_ELE_SERVICE, SOURCE_VITESSE])
    panel.show()
    app.processEvents()

    panel.grab().save(str(destination))
    print(f"grandeurs tracées : {len(panel.view._series)}", flush=True)
    print(f"unités            : {panel.view.units}", flush=True)
    print(f"capture écrite    : {destination.resolve()}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
