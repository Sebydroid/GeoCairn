"""Règles d'allègement de la livraison Windows.

Ces règles décident de ce que l'exécutable embarque. Une erreur de découpage y
avait fait disparaître l'anglais du moteur de carte : rien ne le signalait
avant que le programme, une fois lancé, ne se plaigne de ne pas trouver
`en-US.pak`. D'où ces tests.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "outils"))

from livraison import (  # noqa: E402
    LANGUES,
    MODULES_INUTILES,
    est_etranger,
    est_outil_de_developpement,
    est_traduction,
    langue_retenue,
    module_inutile,
    ressource_retenue,
)


# ------------------------------------------------------------- langues


@pytest.mark.parametrize(
    "nom",
    [
        "fr.pak",           # moteur de carte : la langue seule
        "en-US.pak",        # variante régionale
        "en-GB.pak",
        "qtbase_fr.qm",     # Qt : le module puis la langue
        "qtwebengine_en.qm",
        "qt_fr.qm",
    ],
)
def test_langues_conservees(nom):
    assert langue_retenue(nom) is True


@pytest.mark.parametrize(
    "nom",
    ["de.pak", "zh-CN.pak", "ru.pak", "qtbase_de.qm", "qtbase_zh_CN.qm",
     "pt-BR.pak", "ja.pak"],
)
def test_langues_ecartees(nom):
    assert langue_retenue(nom) is False


def test_l_anglais_regional_est_conserve():
    """Régression : « en-US » découpé au premier tiret devenait « US ».

    Le moteur de carte réclame en-US.pak au démarrage ; sans lui, il prévient
    que les traductions seront fausses.
    """
    assert langue_retenue("en-US.pak") is True
    assert "en" in LANGUES


# --------------------------------------------------------- ressources


def test_les_outils_de_developpement_sont_ecartes():
    assert est_outil_de_developpement("qtwebengine_devtools_resources.pak")
    assert est_outil_de_developpement("qtwebengine_devtools_resources.debug.pak")
    assert not est_outil_de_developpement("qtwebengine_resources.pak")


def test_les_ressources_du_moteur_sont_conservees():
    for nom in (
        "PyQt6/Qt6/resources/qtwebengine_resources.pak",
        "PyQt6/Qt6/resources/qtwebengine_resources_100p.pak",
        "PyQt6/Qt6/resources/icudtl.dat",
        "geocairn/resources/map.html",
        "geocairn/resources/leaflet/leaflet.js",
    ):
        assert ressource_retenue(nom) is True, nom


def test_les_traductions_inutiles_sont_ecartees():
    assert ressource_retenue(
        "PyQt6/Qt6/translations/qtwebengine_locales/de.pak"
    ) is False
    assert ressource_retenue(
        "PyQt6/Qt6/translations/qtwebengine_locales/en-US.pak"
    ) is True


def test_reconnaissance_des_traductions():
    assert est_traduction("PyQt6/Qt6/translations/qtbase_fr.qm") is True
    assert est_traduction(
        "PyQt6\\Qt6\\translations\\qtwebengine_locales\\fr.pak"
    ) is True
    assert est_traduction("geocairn/resources/map.html") is False


def test_une_ressource_de_geocairn_n_est_jamais_prise_pour_une_traduction():
    """Le mot « en » dans un nom de fichier ne doit rien déclencher."""
    assert ressource_retenue("geocairn/resources/leaflet/images/layers.png") is True


# ------------------------------------------------ modules et bibliothèques


def test_les_modules_du_moteur_de_carte_sont_conserves():
    """Sans eux, la carte ne s'affiche plus : ils ne doivent jamais partir."""
    for module in (
        "Qt6Core.dll", "Qt6Gui.dll", "Qt6Widgets.dll", "Qt6Network.dll",
        "Qt6Qml.dll", "Qt6Quick.dll", "Qt6QuickWidgets.dll",
        "Qt6WebChannel.dll", "Qt6WebEngineCore.dll",
        "Qt6WebEngineWidgets.dll", "Qt6Positioning.dll", "Qt6OpenGL.dll",
        "Qt6QmlModels.dll", "Qt6PrintSupport.dll",
    ):
        assert module_inutile(module) is False, module


def test_les_modules_sans_rapport_sont_ecartes():
    for module in (
        "Qt6Quick3D.dll", "Qt6QuickControls2.dll", "Qt6Multimedia.dll",
        "Qt6Pdf.dll", "Qt6Sensors.dll", "Qt6TextToSpeech.dll",
        "Qt6ShaderTools.dll",
    ):
        assert module_inutile(module) is True, module


def test_aucun_module_indispensable_dans_la_liste_a_ecarter():
    for indispensable in (
        "qt6core", "qt6gui", "qt6widgets", "qt6network", "qt6qml",
        "qt6webchannel", "qt6webengine", "qt6positioning", "qt6opengl",
    ):
        assert indispensable not in MODULES_INUTILES


def test_qt6quick_reste_malgre_les_familles_ecartees():
    """« Qt6Quick3D » part, « Qt6Quick » reste : le préfixe ne doit pas mordre."""
    assert module_inutile("Qt6Quick.dll") is False
    assert module_inutile("Qt6QuickWidgets.dll") is False
    assert module_inutile("Qt6Quick3D.dll") is True


def test_les_bibliotheques_etrangeres_sont_reconnues():
    assert est_etranger(r"C:\ProgramData\Anaconda3\Library\bin\icuuc.dll")
    assert est_etranger(r"C:\Users\x\miniconda3\Library\bin\libssl.dll")
    assert est_etranger("icudt58.dll")


def test_les_bibliotheques_du_projet_sont_conservees():
    for source in (
        r"C:\Claude\GeoCairn\venv\Lib\site-packages\PyQt6\Qt6\bin\Qt6Core.dll",
        r"C:\Python314\python314.dll",
        r"C:\Python314\DLLs\sqlite3.dll",
    ):
        assert est_etranger(source) is False, source


# ---------------------------------------------------- recette et outils


def test_la_recette_utilise_ces_regles():
    """La recette ne doit pas redéfinir sa propre version des règles."""
    spec = Path(__file__).resolve().parent.parent / "geocairn.spec"
    contenu = spec.read_text(encoding="utf-8")

    assert "from livraison import" in contenu
    assert "ressource_retenue" in contenu
    assert "module_inutile" in contenu


def test_le_script_de_construction_assainit_le_chemin():
    """La contamination se règle à la source, pas seulement par filtrage."""
    build = Path(__file__).resolve().parent.parent / "build.py"
    contenu = build.read_text(encoding="utf-8")

    assert "chemin_assaini" in contenu
    assert "PATH=chemin_assaini()" in contenu


def test_le_controle_repere_les_plaintes_du_programme():
    """Un avertissement au démarrage doit faire échouer la construction."""
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from build import reperer_plaintes

    sortie = (
        "GeoCairn 1.0.0 — autotest\n"
        "  [ok ] carte chargée\n"
        "but could not find the translation file for the current locale: "
        "en-US.pak\n"
        "Translations WILL NOT be correct.\n"
    )

    plaintes = reperer_plaintes(sortie)

    assert len(plaintes) == 2
    assert any("en-US.pak" in ligne for ligne in plaintes)
    assert reperer_plaintes("tout va bien\n  [ok ] carte chargée") == []
