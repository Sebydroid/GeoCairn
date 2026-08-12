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

#: Familles de modules Qt sans rapport avec l'application. Le moteur de carte
#: a besoin de Qml, Quick et QuickWidgets ; le reste de la galaxie Qt Quick —
#: la 3D, les contrôles, les dialogues — ne sert jamais ici.
MODULES_INUTILES = (
    "qt6quick3d", "qt6quickcontrols2", "qt6quickdialogs", "qt6quicktimeline",
    "qt6quickparticles", "qt6quickeffects", "qt6quicktest",
    "qt6quickvectorimage", "qt6quicktemplates2", "qt6quickshapes",
    "qt6multimedia", "qt6spatialaudio", "qt6sensors", "qt6serialport",
    "qt6texttospeech", "qt6remoteobjects", "qt6statemachine", "qt6test",
    "qt6pdf", "qt6shadertools", "qt6websockets", "qt6charts", "qt6designer",
    "qt6help", "qt6bluetooth", "qt6nfc", "qt6svg", "qt6datavisualization",
)

#: Langues conservées pour l'interface et le moteur de carte. Les cinquante
#: autres pèsent une cinquantaine de mégaoctets pour rien.
LANGUES = ("fr", "en", "en-us", "en-gb")


def _langue_retenue(nom: str) -> bool:
    """Vrai si ce fichier de traduction concerne une langue conservée."""
    base = os.path.splitext(nom)[0].lower()
    for separateur in ("_", "-"):
        if separateur in base:
            base = base.split(separateur, 1)[1]
            break
    return base in LANGUES or base.split("-")[0] in ("fr", "en")


def _alleger(donnees):
    """Retire les ressources que l'application n'ouvre jamais.

    Les outils de développement web de Chromium représentent à eux seuls plus
    de quatre-vingts mégaoctets : ce sont les panneaux d'inspection du
    navigateur, auxquels Carto ne donne aucun accès.
    """
    retenus = []
    retire = 0.0
    for entree in donnees:
        destination, source = entree[0], entree[1]
        nom = os.path.basename(destination).lower()
        chemin = destination.replace("\\", "/").lower()

        indesirable = (
            "qtwebengine_devtools_resources" in nom
            or ("translations/" in chemin and not _langue_retenue(nom))
            or ("qtwebengine_locales/" in chemin and not _langue_retenue(nom))
        )
        if indesirable:
            try:
                retire += os.path.getsize(source) / 1024 / 1024
            except OSError:
                pass
            continue
        retenus.append(entree)

    print(f"[carto.spec] ressources allégées : {retire:.0f} Mo écartés")
    return retenus


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
    gagne = 0.0
    for entree in binaires:
        destination, source = entree[0], entree[1]
        nom = os.path.basename(destination).lower()
        chemin = str(source).lower()
        etranger = (
            nom.startswith("icu")
            or "anaconda" in chemin
            or "miniconda" in chemin
        )
        inutile = nom.startswith(MODULES_INUTILES)
        if etranger or inutile:
            ecartes.append((entree, "étranger" if etranger else "inutile"))
            try:
                gagne += os.path.getsize(source) / 1024 / 1024
            except OSError:
                pass
        else:
            retenus.append(entree)

    etrangers = sum(1 for _e, motif in ecartes if motif == "étranger")
    print(
        f"[carto.spec] bibliothèques écartées : {etrangers} étrangères, "
        f"{len(ecartes) - etrangers} modules inutilisés ({gagne:.0f} Mo)"
    )
    for entree, motif in ecartes:
        if motif == "étranger":
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
