"""Agrandit une zone d'une capture pour l'examiner de près.

    python tests/zoom_capture.py source.png x y largeur hauteur [facteur] [sortie]
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PyQt6.QtCore import QRect, Qt  # noqa: E402
from PyQt6.QtGui import QImage  # noqa: E402


def main() -> int:
    source = Path(sys.argv[1])
    x, y, largeur, hauteur = (int(v) for v in sys.argv[2:6])
    facteur = int(sys.argv[6]) if len(sys.argv) > 6 else 4
    sortie = Path(sys.argv[7]) if len(sys.argv) > 7 else source.with_name(
        source.stem + "-zoom.png"
    )

    image = QImage(str(source))
    if image.isNull():
        print(f"image illisible : {source}", flush=True)
        return 1

    morceau = image.copy(QRect(x, y, largeur, hauteur))
    agrandi = morceau.scaled(
        largeur * facteur,
        hauteur * facteur,
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.FastTransformation,
    )
    agrandi.save(str(sortie))
    print(f"zoom écrit : {sortie.resolve()}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
