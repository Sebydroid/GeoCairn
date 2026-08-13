"""Règles d'allègement de la livraison Windows.

Ces règles décident de ce que l'exécutable embarque. Elles vivent ici, et non
dans `carto.spec`, pour être vérifiables par les tests : une erreur de
découpage y avait fait disparaître l'anglais du moteur de carte sans que rien
ne le signale avant l'exécution.
"""

from __future__ import annotations

import os

#: Langues conservées pour l'interface et le moteur de carte. Les cinquante
#: autres pèsent une cinquantaine de mégaoctets pour rien.
LANGUES = ("fr", "en")

#: Familles de modules Qt sans rapport avec l'application. Le moteur de carte
#: s'appuie sur Qml, Quick et WebChannel ; le reste de la galaxie Qt Quick —
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

#: Distributions Python étrangères au projet. PyInstaller suit les dépendances
#: en explorant le PATH ; ce qu'il y trouve n'a rien à faire dans la livraison.
DISTRIBUTIONS_ETRANGERES = ("anaconda", "miniconda")


def langue_retenue(nom: str) -> bool:
    """Vrai si ce fichier de traduction concerne une langue conservée.

    Les deux familles de noms ne se découpent pas de la même façon : le moteur
    de carte nomme ses fichiers d'après la seule langue (`fr.pak`, `en-US.pak`),
    Qt les préfixe du module (`qtbase_fr.qm`). On regarde donc chaque segment.
    Un découpage sur le premier séparateur transformait « en-US » en « US » et
    faisait disparaître l'anglais, que le moteur réclame au démarrage.
    """
    base = os.path.splitext(nom)[0].lower()
    segments = base.replace("-", "_").split("_")
    return any(segment in LANGUES for segment in segments)


def est_traduction(destination: str) -> bool:
    """Vrai si le fichier est une traduction, de Qt ou du moteur de carte."""
    chemin = destination.replace("\\", "/").lower()
    return "translations/" in chemin or "qtwebengine_locales/" in chemin


def est_outil_de_developpement(nom: str) -> bool:
    """Panneaux d'inspection de Chromium : plus de quatre-vingts mégaoctets."""
    return "qtwebengine_devtools_resources" in nom.lower()


def ressource_retenue(destination: str) -> bool:
    """Décide si une ressource mérite sa place dans la livraison."""
    nom = os.path.basename(destination)
    if est_outil_de_developpement(nom):
        return False
    if est_traduction(destination) and not langue_retenue(nom):
        return False
    return True


def est_etranger(source: str) -> bool:
    """Vrai si la bibliothèque provient d'une autre distribution Python."""
    chemin = str(source).lower()
    return (
        os.path.basename(chemin).startswith("icu")
        or any(marque in chemin for marque in DISTRIBUTIONS_ETRANGERES)
    )


def module_inutile(destination: str) -> bool:
    """Vrai si ce module Qt ne sert jamais à l'application."""
    return os.path.basename(destination).lower().startswith(MODULES_INUTILES)
