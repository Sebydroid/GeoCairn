"""Sécurité des données et livraison Windows (Jalon 7).

Ce que ces tests protègent : une mise à jour du logiciel remplace le dossier
d'installation. Si la moindre donnée utilisateur s'y trouvait, elle
disparaîtrait. Ils vérifient donc que rien d'écrit par l'application n'atterrit
là, y compris une fois le programme compilé, où les chemins changent.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest

from carto import config
from carto.database import Database
from carto.models import Point


@pytest.fixture
def faux_gel(monkeypatch, tmp_path):
    """Simule l'exécution depuis l'exécutable produit par PyInstaller."""
    installation = tmp_path / "Programmes" / "Carto"
    ressources = installation / "_internal" / "carto" / "resources"
    ressources.mkdir(parents=True)
    (ressources / "map.html").write_text("<html></html>", encoding="utf-8")

    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(installation / "Carto.exe"))
    monkeypatch.setattr(
        sys, "_MEIPASS", str(installation / "_internal"), raising=False
    )
    return installation


# ------------------------------------------------- emplacement des données


def test_les_donnees_ne_sont_pas_dans_le_dossier_du_logiciel(monkeypatch, tmp_path):
    monkeypatch.delenv(config.ENV_DATA_DIR, raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "AppData" / "Local"))

    installation = config.install_dir()
    donnees = config.data_dir().resolve()

    assert installation not in donnees.parents
    assert donnees != installation


def test_les_donnees_restent_dehors_une_fois_compile(
    faux_gel, monkeypatch, tmp_path
):
    """Le cas qui compte : l'exécutable livré, dans Program Files."""
    monkeypatch.delenv(config.ENV_DATA_DIR, raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "AppData" / "Local"))

    assert config.is_frozen() is True
    assert config.install_dir() == faux_gel

    base = config.db_path().resolve()
    assert faux_gel not in base.parents
    assert "AppData" in str(base)


def test_les_ressources_suivent_l_executable(faux_gel):
    """Compilée, l'application lit ses ressources à côté de l'exécutable."""
    page = config.resource_path("map.html")

    assert page.is_file()
    assert faux_gel in page.parents


def test_les_ressources_restent_lisibles_depuis_les_sources():
    """Sans compilation, elles sont dans l'arborescence du projet."""
    assert config.is_frozen() is False
    assert config.resource_path("map.html").is_file()
    assert config.resource_path("leaflet", "leaflet.js").is_file()


# ------------------------------------------------------ mise à jour


def test_une_mise_a_jour_ne_touche_pas_aux_traces(tmp_path, monkeypatch):
    """Remplacer le dossier du logiciel doit laisser les données intactes.

    On reproduit le geste d'une mise à jour : effacer le dossier d'installation
    et le remplacer par une nouvelle version.
    """
    installation = tmp_path / "Programmes" / "Carto"
    (installation / "_internal").mkdir(parents=True)
    (installation / "Carto.exe").write_text("version 1", encoding="utf-8")

    donnees = tmp_path / "AppData" / "Local" / "Carto"
    monkeypatch.setenv(config.ENV_DATA_DIR, str(donnees))

    with Database(config.db_path()) as db:
        dossier = db.create_folder("Rallye 2016")
        track_id = db.create_track(
            "Parcours 20 km",
            folder_id=dossier,
            points=[Point(48.93, 1.44, 70.0), Point(48.94, 1.45, 75.0)],
        )
        db.set_track_style(track_id, color="#e6194b", opacity=0.5)
        db.set_track_visible(track_id, True)

    # La mise à jour : l'ancien dossier disparaît, un neuf le remplace.
    shutil.rmtree(installation)
    (installation / "_internal").mkdir(parents=True)
    (installation / "Carto.exe").write_text("version 2", encoding="utf-8")

    with Database(config.db_path()) as relue:
        track = relue.get_track(track_id, with_points=True)
        assert track is not None
        assert track.name == "Parcours 20 km"
        assert track.color == "#e6194b"
        assert track.opacity == pytest.approx(0.5)
        assert track.visible is True
        assert len(track.points) == 2
        assert relue.get_folder(dossier).name == "Rallye 2016"


def test_une_ancienne_base_est_mise_a_niveau_par_la_nouvelle_version(
    tmp_path, monkeypatch
):
    """Le sens inverse : des données d'hier ouvertes par le logiciel du jour."""
    donnees = tmp_path / "donnees"
    monkeypatch.setenv(config.ENV_DATA_DIR, str(donnees))

    with Database(config.db_path()) as db:
        track_id = db.create_track(
            "Ancienne", points=[Point(48.93, 1.44), Point(48.94, 1.45)]
        )
        # On rabaisse le numéro de version, comme une base d'une livraison
        # antérieure.
        db.conn.execute("UPDATE meta SET value = '1' WHERE key = 'schema_version'")
        db.conn.commit()

    with Database(config.db_path()) as relue:
        assert relue.schema_version == 5
        assert relue.get_track(track_id).name == "Ancienne"


def test_le_repertoire_de_donnees_est_cree_au_besoin(tmp_path, monkeypatch):
    cible = tmp_path / "jamais" / "cree" / "encore"
    monkeypatch.setenv(config.ENV_DATA_DIR, str(cible))

    assert config.data_dir().is_dir()


# ------------------------------------------------ recette de construction


def test_la_recette_de_construction_existe():
    spec = Path(config.install_dir()) / "carto.spec"
    assert spec.is_file(), "carto.spec doit accompagner les sources"

    contenu = spec.read_text(encoding="utf-8")
    # Les ressources doivent être embarquées, sans quoi la carte serait vide.
    assert "carto/resources" in contenu
    # Le filtre qui écarte les bibliothèques étrangères doit rester en place.
    assert "icu" in contenu.lower()


def test_l_autotest_est_disponible():
    """`Carto.exe --autotest` doit exister pour contrôler une livraison."""
    from carto import app

    assert hasattr(app, "selftest")
    source = Path(app.__file__).read_text(encoding="utf-8")
    assert "--autotest" in source


def test_l_autotest_verifie_l_affichage_d_une_trace():
    """Après allègement, il faut s'assurer que la carte dessine encore."""
    from carto import app

    source = Path(app.__file__).read_text(encoding="utf-8")
    assert "trace affichée sur la carte" in source


# ------------------------------------------------------ allègement


def test_la_recette_ecarte_les_outils_de_developpement_web():
    """Les panneaux d'inspection de Chromium pèsent plus de 80 Mo."""
    contenu = (Path(config.install_dir()) / "carto.spec").read_text(encoding="utf-8")
    assert "qtwebengine_devtools_resources" in contenu


def test_la_recette_ne_garde_que_quelques_langues():
    contenu = (Path(config.install_dir()) / "carto.spec").read_text(encoding="utf-8")
    assert "LANGUES" in contenu
    assert "qtwebengine_locales" in contenu


def test_la_recette_conserve_les_modules_necessaires_a_la_carte():
    """Le moteur de carte s'appuie sur Qml, Quick et WebChannel."""
    from carto import __file__ as source_carto

    spec = Path(source_carto).resolve().parent.parent / "carto.spec"
    contenu = spec.read_text(encoding="utf-8")

    debut = contenu.index("MODULES_INUTILES")
    fin = contenu.index(")", debut)
    ecartes = contenu[debut:fin].lower()

    for indispensable in ("qt6qml\"", "qt6quick\"", "qt6webchannel\"",
                          "qt6webengine", "qt6core", "qt6gui", "qt6widgets",
                          "qt6network", "qt6positioning", "qt6opengl"):
        assert indispensable not in ecartes, (
            f"{indispensable} est nécessaire au moteur de carte"
        )


# --------------------------------------------------- installation


def test_les_scripts_d_installation_accompagnent_la_livraison():
    outils = Path(config.install_dir()) / "outils"

    for nom in ("installer.ps1", "Installer.bat", "Desinstaller.bat"):
        assert (outils / nom).is_file(), f"{nom} manque"


def test_l_installation_ne_touche_pas_aux_donnees():
    """Le script ne doit jamais effacer AppData sans le demander."""
    script = (Path(config.install_dir()) / "outils" / "installer.ps1").read_text(
        encoding="utf-8"
    )

    # La suppression des traces n'existe que derrière une question explicite.
    assert "Supprimer aussi vos traces" in script
    lignes = script.splitlines()
    for rang, ligne in enumerate(lignes):
        if "Remove-Item" in ligne and "DossierDonnees" in ligne:
            contexte = "\n".join(lignes[max(0, rang - 4):rang])
            assert "Read-Host" in contexte or "reponse" in contexte, (
                "les traces ne doivent être supprimées qu'après confirmation"
            )


def test_l_installation_se_fait_sans_droits_administrateur():
    script = (Path(config.install_dir()) / "outils" / "installer.ps1").read_text(
        encoding="utf-8"
    )
    assert "LOCALAPPDATA" in script

    iss = Path(config.install_dir()) / "installateur.iss"
    if iss.is_file():
        contenu = iss.read_text(encoding="utf-8")
        assert "PrivilegesRequired=lowest" in contenu
        assert "{localappdata}" in contenu


def test_l_installeur_ne_supprime_que_le_dossier_du_programme():
    iss = Path(config.install_dir()) / "installateur.iss"
    contenu = iss.read_text(encoding="utf-8")

    debut = contenu.index("[UninstallDelete]")
    # Les commentaires — qui rappellent justement la règle — ne sont pas des
    # instructions : seules les lignes effectives comptent.
    instructions = [
        ligne
        for ligne in contenu[debut:].splitlines()
        if ligne.strip() and not ligne.strip().startswith(";")
    ]
    section = "\n".join(instructions)

    assert "{app}" in section
    # Jamais le dossier des traces.
    assert "{localappdata}\\Carto" not in section
    assert "{userappdata}" not in section
