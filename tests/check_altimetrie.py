"""Vérifie le service altimétrique IGN sur une vraie trace du projet.

    python tests/check_altimetrie.py

Diagnostic réseau, hors pytest : il dépend d'Internet et de la disponibilité
de la Géoplateforme.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from geocairn.elevation import ElevationError, fetch_elevations  # noqa: E402
from geocairn.geo import format_length, total_length  # noqa: E402
from geocairn.gpx import parse_gpx  # noqa: E402
from geocairn.models import Point  # noqa: E402

EXEMPLES = Path(__file__).resolve().parent.parent / "GPX exemples"


def denivele(altitudes) -> tuple[float, float]:
    montee = descente = 0.0
    connues = [a for a in altitudes if a is not None]
    for avant, apres in zip(connues, connues[1:]):
        ecart = apres - avant
        if ecart > 0:
            montee += ecart
        else:
            descente -= ecart
    return (montee, descente)


def main() -> int:
    # 1. Un point connu : la vallée de l'Eure, aux environs de 60 m.
    essai = fetch_elevations([Point(48.9315, 1.4402)])
    print(f"point de reference : {essai[0]} m", flush=True)

    # 2. Un point hors couverture (milieu de l'Atlantique).
    hors = fetch_elevations([Point(30.0, -40.0)])
    print(f"hors couverture    : {hors[0]}", flush=True)

    # 3. Une vraie trace du projet.
    fichiers = sorted(EXEMPLES.glob("Parcours*.gpx")) if EXEMPLES.is_dir() else []
    if not fichiers:
        print("aucun fichier d'exemple", flush=True)
        return 0

    trace = parse_gpx(fichiers[0])[0]
    points = trace.points[:400]
    print(f"\ntrace   : {trace.name}", flush=True)
    print(f"points  : {len(points)}  ({format_length(total_length(points))})",
          flush=True)

    faits = {"n": 0}

    def progression(n, total):
        faits["n"] = n
        return True

    debut = time.perf_counter()
    try:
        altitudes = fetch_elevations(points, on_progress=progression)
    except ElevationError as exc:
        print(f"ECHEC : {exc}", flush=True)
        return 1
    duree = time.perf_counter() - debut

    connues = [a for a in altitudes if a is not None]
    montee, descente = denivele(altitudes)
    print(f"duree   : {duree:.1f} s pour {len(points)} points", flush=True)
    print(f"obtenus : {len(connues)}/{len(points)}", flush=True)
    if connues:
        print(f"altitude: {min(connues):.0f} m à {max(connues):.0f} m", flush=True)
        print(f"denivele: +{montee:.0f} m / -{descente:.0f} m", flush=True)

    # Comparaison avec l'altitude du fichier, quand elle existe.
    du_fichier = [p.ele for p in points if p.ele is not None]
    if du_fichier and connues:
        ecarts = [
            abs(p.ele - a)
            for p, a in zip(points, altitudes)
            if p.ele is not None and a is not None
        ]
        if ecarts:
            print(f"ecart moyen avec le fichier : "
                  f"{sum(ecarts) / len(ecarts):.1f} m", flush=True)
    return 0 if connues else 1


if __name__ == "__main__":
    sys.exit(main())
