"""Imprime une carte d'exemple en PDF, puis en tire une image pour contrôle.

    python tests/snapshot_impression.py [fichier.png] [échelle] [fond]

Importe un GPX d'exemple, ouvre la boîte d'impression, cadre la feuille sur la
trace, écrit le PDF, puis rend sa première page en PNG. Le PDF est gardé à
côté de l'image.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PyQt6.QtCore import QSize  # noqa: E402
from PyQt6.QtPdf import QPdfDocument  # noqa: E402
from PyQt6.QtWidgets import QMessageBox  # noqa: E402

from geocairn.app import create_app  # noqa: E402
from geocairn.database import Database  # noqa: E402
from geocairn.ui.main_window import MainWindow  # noqa: E402
from geocairn.ui.print_dialog import attendre  # noqa: E402

EXEMPLE = (
    Path(__file__).resolve().parent.parent
    / "GPX exemples"
    / "Parcours 15km Samedi Petits.gpx"
)


def main() -> int:
    destination = Path(sys.argv[1] if len(sys.argv) > 1 else "impression.png")
    echelle = int(sys.argv[2]) if len(sys.argv) > 2 else None
    fond = sys.argv[3] if len(sys.argv) > 3 else None

    app = create_app(["geocairn"])
    QMessageBox.warning = staticmethod(lambda *a, **k: None)
    QMessageBox.information = staticmethod(lambda *a, **k: None)

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as dossier:
        database = Database(Path(dossier) / "apercu.db")
        window = MainWindow(db=database)
        window.show()
        attendre(lambda: window.map_view.is_ready, 20000)
        if fond:
            window.fond_de_carte = fond
        window.import_gpx([str(EXEMPLE)])

        dialogue = window.ouvrir_impression()
        dialogue.cadrer_sur_les_traces()
        if echelle:
            dialogue.set_echelle(echelle)
        attendre(lambda: False, 1500)   # le centre remonte de la carte

        pdf = destination.with_suffix(".pdf")
        ecrit = dialogue.enregistrer_pdf(str(pdf))
        print(f"PDF écrit        : {ecrit}", flush=True)
        print(f"échelle          : {dialogue.choix_echelle.currentText()}", flush=True)
        print(f"emprise          : {dialogue.libelle_emprise.text()}", flush=True)
        print(f"tuiles complètes : {not dialogue._rendu.incomplet}", flush=True)

        document = QPdfDocument(None)
        document.load(str(pdf))
        taille = document.pagePointSize(0)
        image = document.render(
            0, QSize(round(taille.width() * 2), round(taille.height() * 2))
        )
        image.save(str(destination))
        print(f"page             : {taille.width():.0f} × {taille.height():.0f} pt", flush=True)
        print(f"image écrite     : {destination.resolve()}", flush=True)

        dialogue.close()
        window.close()
        database.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
