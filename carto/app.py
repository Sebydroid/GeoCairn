"""Amorçage de l'application Qt."""

from __future__ import annotations

import sys

from PyQt6.QtWidgets import QApplication

from . import APP_NAME, APP_VERSION
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
    app = create_app(argv)
    window = MainWindow()
    window.show()
    return app.exec()
