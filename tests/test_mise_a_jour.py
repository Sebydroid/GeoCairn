"""Fiabilité de la mise à jour d'une installation existante.

Ce que ces tests protègent : le geste le plus courant après la première
livraison — relancer l'installeur par-dessus une version déjà en place. Trois
choses peuvent alors mal tourner, et aucune ne se voit sur la machine de
développement :

  - le programme est ouvert : Windows retient ses fichiers, la copie s'arrête
    à mi-chemin et laisse un mélange de deux versions ;
  - une bibliothèque de l'ancienne version subsiste et est chargée à la place
    de la nouvelle ;
  - l'utilisateur revient en arrière, et un code d'hier ouvre une base
    d'aujourd'hui.

Les données utilisateur, elles, sont couvertes par tests/test_deploiement.py.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from carto import config, mutex
from carto.database import Database, FutureSchemaError, SCHEMA_VERSION
from carto.models import Point

RACINE = Path(config.install_dir())
ISS = (RACINE / "installateur.iss").read_text(encoding="utf-8")
PS1 = (RACINE / "outils" / "installer.ps1").read_text(encoding="utf-8")


def instructions(section: str, source: str = ISS) -> str:
    """Lignes effectives d'une section de l'installeur, commentaires exclus.

    Les commentaires rappellent souvent la règle que le test cherche : les
    confondre avec des instructions rendrait le contrôle sans valeur.
    """
    debut = source.index(f"[{section}]") + len(section) + 2
    reste = source[debut:]
    fin = reste.find("\n[")
    corps = reste if fin == -1 else reste[:fin]
    return "\n".join(
        ligne for ligne in corps.splitlines()
        if ligne.strip() and not ligne.strip().startswith(";")
    )


# ------------------------------------------- programme ouvert pendant la MAJ


def test_l_installeur_reconnait_le_programme_ouvert():
    """La marque posée par le programme et celle attendue par l'installeur.

    Deux fichiers, une seule chaîne : si l'une dérive, l'installeur croira
    Carto fermé et écrasera des fichiers verrouillés.
    """
    assert f"AppMutex={mutex.MUTEX_NAME}" in instructions("Setup")


def test_l_installeur_propose_de_fermer_l_application():
    reglages = instructions("Setup")
    assert "CloseApplications=yes" in reglages
    # La page finale propose déjà de relancer Carto : un redémarrage
    # automatique en ouvrirait un second.
    assert "RestartApplications=no" in reglages


def test_le_programme_pose_sa_marque_de_presence():
    """Sans cet appel au démarrage, la directive AppMutex ne sert à rien."""
    source = (RACINE / "carto" / "app.py").read_text(encoding="utf-8")
    assert "mutex.claim()" in source


@pytest.mark.skipif(os.name != "nt", reason="mutex propre à Windows")
def test_la_marque_de_presence_est_posee_sous_windows():
    assert mutex.claim() is True
    # Un second appel ne pose pas de seconde marque et ne se plaint pas :
    # l'autotest et l'application peuvent tourner dans le même processus.
    assert mutex.claim() is True


def test_le_script_powershell_refuse_d_installer_par_dessus_un_programme_ouvert():
    """La voie ZIP a la même contrainte que l'installeur .exe."""
    assert "function Verifier-Ferme" in PS1
    assert 'Verifier-Ferme "l\'installation"' in PS1
    assert 'Verifier-Ferme "la desinstallation"' in PS1
    # Le refus doit précéder toute suppression, sinon le dossier est déjà
    # amputé quand l'erreur survient.
    assert PS1.index('Verifier-Ferme "l\'installation"') < PS1.index("Remove-Item")


# ---------------------------------------------- restes de l'ancienne version


def test_l_installeur_vide_les_bibliotheques_avant_la_copie():
    """« ignoreversion » écrase les homonymes, il n'efface pas les autres."""
    section = instructions("InstallDelete")
    assert "{app}\\_internal" in section


def test_le_nettoyage_epargne_le_desinstalleur_et_les_traces():
    section = instructions("InstallDelete")

    # {app} tout entier emporterait unins000.exe : la désinstallation
    # deviendrait impossible.
    for ligne in section.splitlines():
        cible = ligne.split("Name:", 1)[1].strip().strip('"')
        assert cible != "{app}"
        assert "{localappdata}\\Carto" not in cible
        assert "{userappdata}" not in cible


def test_le_dossier_nettoye_est_bien_celui_que_produit_pyinstaller():
    """_internal est le nom donné par PyInstaller 6 ; s'il change, le
    nettoyage viserait le vide sans que rien ne le signale."""
    livraison = RACINE / "dist" / "Carto"
    if not livraison.is_dir():
        pytest.skip("aucune livraison construite")
    assert (livraison / "_internal").is_dir()


# --------------------------------------------------- retour à une version antérieure


def test_une_base_plus_recente_est_refusee(tmp_path, monkeypatch):
    """Le cas du retour en arrière : version d'hier, données d'aujourd'hui."""
    monkeypatch.setenv(config.ENV_DATA_DIR, str(tmp_path / "donnees"))
    chemin = config.db_path()

    with Database(chemin) as db:
        db.create_track("Parcours", points=[Point(48.93, 1.44), Point(48.94, 1.45)])
        db.conn.execute(
            "UPDATE meta SET value = ? WHERE key = 'schema_version'",
            (str(SCHEMA_VERSION + 1),),
        )
        db.conn.commit()

    with pytest.raises(FutureSchemaError) as refus:
        Database(chemin)

    assert refus.value.trouvee == SCHEMA_VERSION + 1
    assert refus.value.connue == SCHEMA_VERSION


def test_le_refus_ne_retient_pas_le_fichier(tmp_path, monkeypatch):
    """Une base refusée doit rester déplaçable, restaurable, sauvegardable.

    Sous Windows, un fichier qu'un processus garde ouvert ne peut être ni
    renommé ni supprimé : l'utilisateur serait coincé jusqu'à fermer Carto.
    """
    monkeypatch.setenv(config.ENV_DATA_DIR, str(tmp_path / "donnees"))
    chemin = config.db_path()

    with Database(chemin) as db:
        db.conn.execute(
            "UPDATE meta SET value = ? WHERE key = 'schema_version'",
            (str(SCHEMA_VERSION + 1),),
        )
        db.conn.commit()

    with pytest.raises(FutureSchemaError):
        Database(chemin)

    chemin.rename(chemin.with_suffix(".db.sauvegarde"))


def test_le_message_explique_quoi_faire():
    """L'utilisateur n'a pas de console : le seul recours est la boîte."""
    source = (RACINE / "carto" / "app.py").read_text(encoding="utf-8")
    assert "FutureSchemaError" in source
    assert "Réinstallez la dernière version" in source


def test_une_base_a_jour_s_ouvre_sans_histoire(tmp_path, monkeypatch):
    """Le garde-fou ne doit gêner personne dans le cas courant."""
    monkeypatch.setenv(config.ENV_DATA_DIR, str(tmp_path / "donnees"))

    with Database(config.db_path()) as db:
        piste = db.create_track("Parcours", points=[Point(48.93, 1.44)])

    with Database(config.db_path()) as relue:
        assert relue.schema_version == SCHEMA_VERSION
        assert relue.get_track(piste).name == "Parcours"
