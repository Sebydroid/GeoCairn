# -*- mode: python ; coding: utf-8 -*-
"""Recette de construction de l'exécutable Windows.

    python build.py            (recommandé : PATH assaini et contrôle)
    pyinstaller carto.spec --noconfirm

Le mode « un dossier » est retenu plutôt que le fichier unique : QtWebEngine
embarque son propre processus de rendu et plusieurs centaines de mégaoctets de
ressources Chromium, que le mode fichier unique doit extraire dans un dossier
temporaire à chaque lancement — long au démarrage et source de pannes.

Le dossier produit, dist/Carto/, se remplace tel quel lors d'une mise à jour :
aucune donnée utilisateur ne s'y trouve, elles vivent dans AppData.

Les règles d'allègement sont dans outils/livraison.py, pour être vérifiables
par les tests.
"""

import os
import sys

from PyInstaller.utils.hooks import collect_data_files

sys.path.insert(0, os.path.join(SPECPATH, "outils"))
from livraison import est_etranger, module_inutile, ressource_retenue  # noqa: E402

# CARTO_CONSOLE=1 produit une variante qui garde une console : indispensable
# pour lire une erreur de démarrage, que la version fenêtrée avale.
CONSOLE = os.environ.get("CARTO_CONSOLE") == "1"

datas = [
    # Carte Leaflet, feuille de style et page : indispensables au démarrage.
    ("carto/resources", "carto/resources"),
]
datas += collect_data_files(
    "PyQt6",
    includes=["Qt6/resources/*", "Qt6/translations/qtwebengine_locales/*"],
)

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=[
        "PyQt6.QtWebEngineWidgets",
        "PyQt6.QtWebEngineCore",
        "PyQt6.QtWebChannel",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # Modules inutiles à l'application, qui alourdiraient la livraison.
    excludes=["tkinter", "unittest", "pytest", "pydoc_data"],
    noarchive=False,
)


def _poids(source) -> float:
    try:
        return os.path.getsize(source) / 1024 / 1024
    except OSError:
        return 0.0


def _alleger(donnees):
    """Retire les ressources que l'application n'ouvre jamais."""
    retenus = []
    retire = 0.0
    for entree in donnees:
        if ressource_retenue(entree[0]):
            retenus.append(entree)
        else:
            retire += _poids(entree[1])
    print(f"[carto.spec] ressources allégées : {retire:.0f} Mo écartés")
    return retenus


def _ecarter(binaires):
    """Retire les bibliothèques étrangères et les modules Qt inutilisés.

    Les premières viennent d'une autre distribution Python trouvée sur le
    PATH ; sur cette machine, les bibliothèques ICU d'Anaconda empêchaient Qt
    de démarrer. build.py assainit le PATH en amont, ce filtre reste en second
    rideau pour une construction lancée autrement.
    """
    retenus = []
    etrangers = []
    gagne = 0.0
    for entree in binaires:
        destination, source = entree[0], entree[1]
        if est_etranger(source) or est_etranger(destination):
            etrangers.append(entree)
            gagne += _poids(source)
        elif module_inutile(destination):
            gagne += _poids(source)
        else:
            retenus.append(entree)

    inutiles = len(binaires) - len(retenus) - len(etrangers)
    print(
        f"[carto.spec] bibliothèques écartées : {len(etrangers)} étrangères, "
        f"{inutiles} modules inutilisés ({gagne:.0f} Mo)"
    )
    for entree in etrangers:
        print(f"[carto.spec] étranger : {entree[0]}  <-  {entree[1]}")
    return retenus


a.binaries = _ecarter(a.binaries)
a.datas = _alleger(a.datas)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Carto",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=CONSOLE,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="Carto",
)
