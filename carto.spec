# -*- mode: python ; coding: utf-8 -*-
"""Recette de construction de l'exécutable Windows.

    pyinstaller carto.spec --noconfirm

Le mode « un dossier » est retenu plutôt que le fichier unique : QtWebEngine
embarque son propre processus de rendu et plusieurs centaines de mégaoctets de
ressources Chromium, que le mode fichier unique doit extraire dans un dossier
temporaire à chaque lancement — long au démarrage et source de pannes.

Le dossier produit, dist/Carto/, se remplace tel quel lors d'une mise à jour :
aucune donnée utilisateur ne s'y trouve, elles vivent dans AppData.
"""

import os

from PyInstaller.utils.hooks import collect_data_files

# CARTO_CONSOLE=1 produit une variante qui garde une console : indispensable
# pour lire une erreur de démarrage, que la version fenêtrée avale.
CONSOLE = os.environ.get("CARTO_CONSOLE") == "1"

datas = [
    # Carte Leaflet, feuille de style et page : indispensables au démarrage.
    ("carto/resources", "carto/resources"),
]
datas += collect_data_files("PyQt6", includes=["Qt6/resources/*", "Qt6/translations/qtwebengine_locales/*"])

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

def _ecarter(binaires):
    """Retire les bibliothèques ramassées à côté, qui font tomber Qt.

    PyInstaller suit les dépendances en explorant le PATH. Sur une machine où
    Anaconda est installé, il embarque ses bibliothèques ICU sous les noms
    génériques `icuuc.dll` et `icudt58.dll`. Qt6Core, qui attend une version
    bien plus récente, les trouve alors dans le dossier de l'application et
    échoue au chargement avec « la procédure spécifiée est introuvable ».

    Rien de ce qui vient d'une autre distribution Python n'a sa place ici :
    l'application n'a besoin que de son interpréteur, de PyQt6 et de la
    bibliothèque standard.
    """
    ecartes = []
    retenus = []
    for entree in binaires:
        destination, source = entree[0], entree[1]
        nom = os.path.basename(destination).lower()
        chemin = str(source).lower()
        indesirable = (
            nom.startswith("icu")
            or "anaconda" in chemin
            or "miniconda" in chemin
        )
        (ecartes if indesirable else retenus).append(entree)

    for entree in ecartes:
        print(f"[carto.spec] écarté : {entree[0]}  <-  {entree[1]}")
    return retenus


a.binaries = _ecarter(a.binaries)

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
