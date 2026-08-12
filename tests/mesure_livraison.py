"""Mesure la taille de la livraison, par poste.

    python tests/mesure_livraison.py [dist/Carto]

Sert à décider ce qu'il est utile d'écarter, et à vérifier l'effet d'un
allègement.
"""

from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

MO = 1024 * 1024


def taille(chemins) -> float:
    return sum(f.stat().st_size for f in chemins if f.is_file()) / MO


def main() -> int:
    racine = Path(sys.argv[1] if len(sys.argv) > 1 else "dist/Carto").resolve()
    if not racine.is_dir():
        print(f"livraison introuvable : {racine}", flush=True)
        return 1

    fichiers = [f for f in racine.rglob("*") if f.is_file()]
    total = taille(fichiers)
    print(f"livraison : {racine}")
    print(f"total     : {total:.0f} Mo  ({len(fichiers)} fichiers)\n")

    print("— les dix plus gros fichiers —")
    for f in sorted(fichiers, key=lambda f: -f.stat().st_size)[:10]:
        print(f"{f.stat().st_size / MO:8.1f} Mo  {f.relative_to(racine)}")

    print("\n— par famille de modules Qt —")
    familles = defaultdict(list)
    for f in fichiers:
        nom = f.name
        if not nom.startswith("Qt6") or not nom.endswith(".dll"):
            continue
        court = nom[3:-4]
        for prefixe in (
            "WebEngine", "Quick3D", "QuickControls2", "QuickDialogs",
            "Quick", "Qml", "Multimedia", "Sensors", "RemoteObjects",
            "StateMachine", "Pdf", "Positioning", "WebChannel",
        ):
            if court.startswith(prefixe):
                familles[prefixe].append(f)
                break
        else:
            familles[court].append(f)

    for nom, membres in sorted(familles.items(), key=lambda kv: -taille(kv[1])):
        poids = taille(membres)
        if poids >= 0.5:
            print(f"{poids:8.1f} Mo  {nom}  ({len(membres)} fichier(s))")

    print("\n— par dossier —")
    for sous in ("PyQt6/Qt6/bin", "PyQt6/Qt6/resources", "PyQt6/Qt6/translations",
                 "PyQt6/Qt6/qml", "PyQt6/Qt6/plugins"):
        dossier = racine / "_internal" / sous
        if dossier.is_dir():
            print(f"{taille(dossier.rglob('*')):8.1f} Mo  {sous}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
