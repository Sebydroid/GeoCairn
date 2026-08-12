"""Amorçage de l'application Qt."""

from __future__ import annotations

import sys

from PyQt6.QtWidgets import QApplication

from . import APP_NAME, APP_VERSION  # noqa: F401  (APP_VERSION sert à l'autotest)
from .ui.main_window import MainWindow


def create_app(argv: list[str] | None = None) -> QApplication:
    """Crée (ou réutilise) l'instance QApplication configurée.

    QtWebEngine (Chromium) exige un argv[0] non vide : sans lui, l'initialisation
    de la ligne de commande interne échoue et le processus meurt brutalement.
    """
    app = QApplication.instance()
    if app is None:
        args = list(argv) if argv else list(sys.argv)
        if not args:
            args = [APP_NAME]
        app = QApplication(args)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)
    app.setOrganizationName(APP_NAME)
    return app


def run(argv: list[str] | None = None) -> int:
    arguments = list(argv) if argv is not None else list(sys.argv)
    if "--autotest" in arguments:
        return selftest(arguments)

    app = create_app(argv)
    window = MainWindow()
    window.show()
    return app.exec()


def selftest(argv: list[str] | None = None) -> int:
    """Vérifie que l'application trouve tout ce dont elle a besoin.

    Destiné à la version compilée : lancer `Carto.exe --autotest` contrôle en
    quelques secondes que les ressources embarquées sont là, que la carte se
    charge et que la base s'ouvre au bon endroit, puis rend un compte rendu et
    un code de sortie. Sans cela, une livraison incomplète ne se découvrirait
    qu'au premier lancement chez l'utilisateur.
    """
    from PyQt6.QtCore import QEventLoop, QTimer

    from .config import db_path, install_dir, is_frozen, resource_path
    from .ui.main_window import MainWindow as Fenetre

    app = create_app(argv)
    constats: list[tuple[str, bool, str]] = []

    def constater(libelle: str, ok: bool, detail: str = "") -> None:
        constats.append((libelle, bool(ok), detail))

    carte = resource_path("map.html")
    constater("page de la carte", carte.is_file(), str(carte))
    leaflet = resource_path("leaflet", "leaflet.js")
    constater("Leaflet embarqué", leaflet.is_file(), str(leaflet))

    fenetre = Fenetre()
    fenetre.show()

    pret = {"carte": False}
    fenetre.map_view.map_ready.connect(lambda: pret.update(carte=True))

    boucle = QEventLoop()
    QTimer.singleShot(20000, boucle.quit)
    minuteur = QTimer()
    minuteur.timeout.connect(lambda: pret["carte"] and boucle.quit())
    minuteur.start(100)
    boucle.exec()
    minuteur.stop()

    constater("carte chargée", pret["carte"])

    # Une trace réellement dessinée : c'est le seul moyen de s'assurer que le
    # pont JavaScript et les modules du moteur de carte sont tous là, après
    # l'allègement de la livraison.
    if pret["carte"]:
        from .models import Point

        trace = fenetre.db.create_track(
            "Autotest",
            points=[Point(48.930, 1.440), Point(48.931, 1.442),
                    Point(48.932, 1.441)],
        )
        fenetre.display_track(trace)
        affichee = {"points": 0}

        def relever(valeur):
            affichee["points"] = valeur or 0

        attente = QEventLoop()
        QTimer.singleShot(4000, attente.quit)
        QTimer.singleShot(
            300,
            lambda: fenetre.map_view.page().runJavaScript(
                f"carto.shownCount({trace})",
                lambda v: (relever(v), attente.quit()),
            ),
        )
        attente.exec()
        constater(
            "trace affichée sur la carte",
            affichee["points"] == 3,
            f"{affichee['points']} points",
        )
        fenetre.db.delete_track(trace)

    constater("base de données", db_path().is_file(), str(db_path()))
    constater(
        "données hors du dossier d'installation",
        install_dir() not in db_path().resolve().parents,
        f"installation : {install_dir()}",
    )

    fenetre.close()

    print(f"Carto {APP_VERSION} — autotest ({'compilé' if is_frozen() else 'source'})")
    for libelle, ok, detail in constats:
        print(f"  [{'ok ' if ok else 'ECHEC'}] {libelle}" + (f"  {detail}" if detail else ""))

    echecs = sum(1 for _l, ok, _d in constats if not ok)
    print("RESULTAT :", "tout est en place" if not echecs else f"{echecs} anomalie(s)")
    return 0 if not echecs else 1
