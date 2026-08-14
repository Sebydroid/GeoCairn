"""Amorçage de l'application Qt."""

from __future__ import annotations

import sqlite3
import sys

from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication, QMessageBox

from . import APP_NAME, APP_SLUG, APP_VERSION  # noqa: F401  (APP_VERSION sert à l'autotest)
from . import mutex
from .config import db_path, resource_path
from .database import Database, FutureSchemaError
from .ui.main_window import MainWindow


def icone() -> QIcon:
    """Logo du programme, pour la fenêtre et la barre des tâches.

    Le même fichier sert à l'exécutable et aux raccourcis Windows : une seule
    source, donc aucun risque de voir deux logos différents cohabiter. Une
    icône absente ne doit pas empêcher le démarrage, d'où l'icône vide en
    repli.
    """
    chemin = resource_path("geocairn.ico")
    return QIcon(str(chemin)) if chemin.is_file() else QIcon()


def create_app(argv: list[str] | None = None) -> QApplication:
    """Crée (ou réutilise) l'instance QApplication configurée.

    QtWebEngine (Chromium) exige un argv[0] non vide : sans lui, l'initialisation
    de la ligne de commande interne échoue et le processus meurt brutalement.
    """
    app = QApplication.instance()
    if app is None:
        args = list(argv) if argv else list(sys.argv)
        if not args:
            args = [APP_SLUG]
        app = QApplication(args)
    # Qt bâtit ses propres chemins — le cache du moteur de carte, notamment —
    # à partir du nom de l'organisation et de celui de l'application. Tous deux
    # prennent donc l'identifiant technique : sans quoi Chromium écrirait dans
    # un « ...\GeoCairn\Géo Cairn\cache » accentué. Le nom affiché passe par
    # setApplicationDisplayName, prévu exactement pour cette distinction.
    app.setApplicationName(APP_SLUG)
    app.setApplicationDisplayName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)
    app.setOrganizationName(APP_SLUG)
    app.setWindowIcon(icone())
    return app


def run(argv: list[str] | None = None) -> int:
    arguments = list(argv) if argv is not None else list(sys.argv)
    if "--autotest" in arguments:
        return selftest(arguments)

    app = create_app(argv)

    # Signale à l'installeur que le programme tourne : sans cela, une mise à
    # jour lancée fenêtre ouverte remplacerait des fichiers que Windows retient.
    mutex.claim()

    # Une base illisible ou protégée en écriture (fichier abîmé, restauré d'une
    # sauvegarde, disque plein, dossier verrouillé) ne doit pas faire
    # disparaître le programme sans un mot : la version compilée n'a pas de
    # console où lire la moindre explication.
    try:
        db = Database()
    except FutureSchemaError as exc:
        QMessageBox.critical(
            None,
            f"{APP_NAME} — version trop ancienne",
            f"Vos traces ont été enregistrées par une version plus récente de "
            f"{APP_NAME} ({exc.trouvee} contre {exc.connue} ici).\n\n"
            "Réinstallez la dernière version pour les rouvrir : celle-ci "
            "risquerait de les abîmer.\n\n"
            f"Fichier concerné :\n{db_path()}",
        )
        return 1
    except (sqlite3.Error, OSError) as exc:
        QMessageBox.critical(
            None,
            f"{APP_NAME} — base de données inaccessible",
            f"Impossible d'ouvrir la bibliothèque de traces :\n{exc}\n\n"
            f"Fichier concerné :\n{db_path()}\n\n"
            "Vérifiez que ce fichier n'est pas en lecture seule et qu'aucun "
            "autre programme ne le retient.",
        )
        return 1

    window = MainWindow(db=db)
    window.show()
    return app.exec()


def selftest(argv: list[str] | None = None) -> int:
    """Vérifie que l'application trouve tout ce dont elle a besoin.

    Destiné à la version compilée : lancer `GeoCairn.exe --autotest` contrôle en
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
                f"geocairn.shownCount({trace})",
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

    print(f"{APP_NAME} {APP_VERSION} — autotest ({'compilé' if is_frozen() else 'source'})")
    for libelle, ok, detail in constats:
        print(f"  [{'ok ' if ok else 'ECHEC'}] {libelle}" + (f"  {detail}" if detail else ""))

    echecs = sum(1 for _l, ok, _d in constats if not ok)
    print("RESULTAT :", "tout est en place" if not echecs else f"{echecs} anomalie(s)")
    return 0 if not echecs else 1
