"""Planche des icônes de la barre d'outils, agrandies pour examen.

    python tests/snapshot_icones.py [fichier.png]
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PyQt6.QtCore import QPointF, Qt  # noqa: E402
from PyQt6.QtGui import QColor, QPainter, QPixmap  # noqa: E402

from carto.app import create_app  # noqa: E402
from carto.ui.toolbar_icons import TAILLE, toolbar_icon  # noqa: E402

NOMS = [
    "import", "export", "creer", "modifier",
    "annuler", "boucle", "enregistrer", "effacer",
]
FACTEUR = 5


def main() -> int:
    destination = Path(sys.argv[1] if len(sys.argv) > 1 else "icones.png")
    app = create_app(["carto"])

    cote = TAILLE * FACTEUR
    marge = 14
    planche = QPixmap(
        len(NOMS) * (cote + marge) + marge, cote + marge * 3
    )
    planche.fill(QColor("#ffffff"))

    painter = QPainter(planche)
    for rang, nom in enumerate(NOMS):
        x = marge + rang * (cote + marge)
        image = toolbar_icon(nom).pixmap(TAILLE, TAILLE).toImage()
        agrandie = image.scaled(
            cote, cote,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        painter.drawImage(QPointF(x, marge), agrandie)
        painter.setPen(QColor("#333333"))
        painter.drawText(int(x), int(marge + cote + 16), nom)
    painter.end()

    planche.save(str(destination))
    print(f"planche écrite : {destination.resolve()}", flush=True)
    del app
    return 0


if __name__ == "__main__":
    sys.exit(main())
